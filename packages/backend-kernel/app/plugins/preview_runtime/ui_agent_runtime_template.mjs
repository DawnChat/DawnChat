export function createUiAgentRuntimeScript(currentPluginId) {
  const escapedPluginId = JSON.stringify(currentPluginId)
  return `
(() => {
  if (window.__DAWNCHAT_UI_AGENT_RUNTIME__) return;
  window.__DAWNCHAT_UI_AGENT_RUNTIME__ = true;

  const PLUGIN_ID = ${escapedPluginId};
  const PREFIX = 'DAWNCHAT_UI_AGENT_';
  const HOST_INVOKE_REQUEST = 'DAWNCHAT_HOST_INVOKE_REQUEST';
  const HOST_INVOKE_RESULT = 'DAWNCHAT_HOST_INVOKE_RESULT';
  const HOST_INVOKE_TIMEOUT_MS = 180000;
  const PLUGIN_LOG_BATCH = 'DAWNCHAT_PLUGIN_LOG_BATCH';
  const LOG_BATCH_DELAY_MS = 400;
  const LOG_BATCH_MAX = 20;
  const MAX_LOG_MESSAGE_LEN = 2000;
  const NOISY_PATTERNS = [
    '[vite]',
    '[hmr]',
    'download the vue devtools extension',
  ];
  const MAX_DEFAULT_NODES = 200;
  const STABLE_SCAN_LIMIT = 500;
  const ACTION_ALIASES = {
    type_text: 'type',
    clear_and_type: 'clear_type',
  };

  const post = (type, requestId, result) => {
    if (window.parent === window) return;
    window.parent.postMessage({
      type,
      pluginId: PLUGIN_ID,
      requestId,
      result,
      ts: Date.now(),
    }, '*');
  };

  const toLogValue = (value) => {
    if (value instanceof Error) {
      return {
        name: value.name || 'Error',
        message: value.message || '',
        stack: value.stack || '',
      };
    }
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      return value;
    }
    if (value == null) return value;
    try {
      return JSON.parse(JSON.stringify(value));
    } catch {
      return String(value);
    }
  };

  let logQueue = [];
  let logTimer = null;
  const flushLogs = () => {
    if (!logQueue.length) return;
    const batch = logQueue.splice(0, LOG_BATCH_MAX);
    if (window.parent !== window) {
      window.parent.postMessage(
        {
          type: PLUGIN_LOG_BATCH,
          pluginId: PLUGIN_ID,
          logs: batch,
          ts: Date.now(),
        },
        '*'
      );
    }
    if (logQueue.length) {
      logTimer = window.setTimeout(flushLogs, 0);
    } else {
      logTimer = null;
    }
  };

  const isNoisyMessage = (message) => {
    const text = String(message || '').toLowerCase();
    if (!text) return false;
    return NOISY_PATTERNS.some((item) => text.includes(item));
  };

  const enqueueLog = (level, args) => {
    const normalized = Array.isArray(args) ? args : [args];
    const message = normalized
      .map((item) => {
        if (typeof item === 'string') return item;
        try {
          return JSON.stringify(item);
        } catch {
          return String(item);
        }
      })
      .join(' ')
      .trim()
      .slice(0, MAX_LOG_MESSAGE_LEN);
    if (!message) return;
    if (isNoisyMessage(message)) return;
    logQueue.push({
      level,
      message,
      data: normalized.map(toLogValue),
      timestamp: new Date().toISOString(),
    });
    if (logQueue.length >= LOG_BATCH_MAX) {
      if (logTimer !== null) {
        window.clearTimeout(logTimer);
        logTimer = null;
      }
      flushLogs();
      return;
    }
    if (logTimer === null) {
      logTimer = window.setTimeout(flushLogs, LOG_BATCH_DELAY_MS);
    }
  };

  const installLogCapture = () => {
    const originalWarn = console.warn?.bind(console);
    const originalError = console.error?.bind(console);
    const originalDebug = console.debug?.bind(console);
    const originalInfo = console.info?.bind(console);
    const originalLog = console.log?.bind(console);
    if (originalWarn) {
      console.warn = (...args) => {
        try {
          enqueueLog('WARN', args);
        } catch {
        }
        return originalWarn(...args);
      };
    }
    if (originalError) {
      console.error = (...args) => {
        try {
          enqueueLog('ERROR', args);
        } catch {
        }
        return originalError(...args);
      };
    }
    if (originalDebug) {
      console.debug = (...args) => {
        try {
          enqueueLog('DEBUG', args);
        } catch {
        }
        return originalDebug(...args);
      };
    }
    if (originalInfo) {
      console.info = (...args) => {
        try {
          enqueueLog('INFO', args);
        } catch {
        }
        return originalInfo(...args);
      };
    }
    if (originalLog) {
      console.log = (...args) => {
        try {
          enqueueLog('INFO', args);
        } catch {
        }
        return originalLog(...args);
      };
    }
    window.addEventListener('error', (event) => {
      enqueueLog('ERROR', [
        'window.error',
        {
          message: String(event?.message || ''),
          filename: String(event?.filename || ''),
          lineno: Number(event?.lineno || 0),
          colno: Number(event?.colno || 0),
          error: toLogValue(event?.error),
        },
      ]);
    });
    window.addEventListener('unhandledrejection', (event) => {
      enqueueLog('ERROR', [
        'unhandledrejection',
        {
          reason: toLogValue(event?.reason),
        },
      ]);
    });
  };

  const isVisible = (el) => {
    if (!(el instanceof Element)) return false;
    const rect = el.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
    const style = window.getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
  };

  const isFullyInViewport = (el) => {
    if (!(el instanceof Element)) return false;
    const rect = el.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
    const viewportWidth = Math.max(window.innerWidth || 0, document.documentElement.clientWidth || 0);
    const viewportHeight = Math.max(window.innerHeight || 0, document.documentElement.clientHeight || 0);
    if (viewportWidth <= 0 || viewportHeight <= 0) return false;
    return rect.top >= 0 && rect.left >= 0 && rect.bottom <= viewportHeight && rect.right <= viewportWidth;
  };

  const safeText = (value, max = 120) => {
    const text = String(value || '').replace(/\\s+/g, ' ').trim();
    if (text.length <= max) return text;
    return text.slice(0, max) + '...';
  };

  const buildPathIndex = (el) => {
    if (!(el instanceof Element)) return '';
    const path = [];
    let current = el;
    while (current && current !== document.body && path.length < 8) {
      const parent = current.parentElement;
      if (!parent) break;
      const siblings = Array.from(parent.children).filter((node) => node.tagName === current.tagName);
      const index = siblings.indexOf(current) + 1;
      path.unshift(current.tagName.toLowerCase() + ':nth-of-type(' + index + ')');
      current = parent;
    }
    return 'body>' + path.join('>');
  };

  const elementRole = (el) => {
    return (
      el.getAttribute('role') ||
      (el.tagName || '').toLowerCase()
    );
  };

  const elementName = (el) => {
    return (
      el.getAttribute('aria-label') ||
      el.getAttribute('name') ||
      safeText(el.textContent || '', 80)
    );
  };

  const normalizeSelector = (el) => {
    if (!(el instanceof Element)) return '';
    if (el.id) return '#' + el.id;
    const testId = el.getAttribute('data-testid');
    if (testId) return '[data-testid="' + testId + '"]';
    const name = el.getAttribute('name');
    if (name) return '[name="' + name + '"]';
    return (el.tagName || '').toLowerCase();
  };

  const buildNode = (el, idx) => {
    const rect = el.getBoundingClientRect();
    return {
      nodeId: 'n_' + idx,
      tag: (el.tagName || '').toLowerCase(),
      role: elementRole(el),
      name: elementName(el),
      text: safeText(el.textContent || ''),
      bounds: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
      locatorHints: {
        selector: normalizeSelector(el),
      },
      pathIndex: buildPathIndex(el),
    };
  };

  const normalizeDescribeScope = (scopeValue) => {
    const raw = String(scopeValue || '').trim().toLowerCase();
    if (raw === 'all' || raw === 'visible' || raw === 'viewport') return raw;
    return 'all';
  };

  const scanElements = (maxNodes, scope = 'visible') => {
    const rows = [];
    const elements = Array.from(document.querySelectorAll('body *'));
    const limit = Math.max(1, Math.min(Number(maxNodes || MAX_DEFAULT_NODES), 500));
    const normalizedScope =
      scope === 'all' || scope === 'visible' || scope === 'viewport' ? scope : normalizeDescribeScope(scope);
    for (let i = 0; i < elements.length; i += 1) {
      const el = elements[i];
      if (normalizedScope === 'visible' && !isVisible(el)) continue;
      if (normalizedScope === 'viewport' && (!isVisible(el) || !isFullyInViewport(el))) continue;
      rows.push({ id: 'n_' + rows.length, el, node: buildNode(el, rows.length) });
      if (rows.length >= limit) break;
    }
    return rows;
  };

  const scanDescribeElements = (maxNodes, scopeValue) => {
    const scope = normalizeDescribeScope(scopeValue);
    return { rows: scanElements(maxNodes, scope), scope };
  };

  const normalizeBounds = (rawBounds) => {
    if (!rawBounds || typeof rawBounds !== 'object') return null;
    const x = Number(rawBounds.x);
    const y = Number(rawBounds.y);
    const width = Number(rawBounds.width);
    const height = Number(rawBounds.height);
    if (![x, y, width, height].every(Number.isFinite)) return null;
    if (width <= 0 || height <= 0) return null;
    return { x, y, width, height };
  };

  const normalizeCanonicalTarget = (target) => {
    if (!target || typeof target !== 'object') return {};
    const normalized = {};
    if (typeof target.nodeId === 'string' && target.nodeId.trim()) normalized.nodeId = target.nodeId.trim();
    if (typeof target.pathIndex === 'string' && target.pathIndex.trim()) normalized.pathIndex = target.pathIndex.trim();
    if (typeof target.selector === 'string' && target.selector.trim()) normalized.selector = target.selector.trim();
    if (typeof target.textContains === 'string' && target.textContains.trim()) normalized.textContains = target.textContains.trim();

    const indexValue = target.index;
    if (typeof indexValue === 'number' && Number.isFinite(indexValue)) {
      const parsed = Math.floor(indexValue);
      if (parsed >= 0) normalized.index = parsed;
    }
    const bounds = normalizeBounds(target.bounds);
    if (bounds) normalized.bounds = bounds;
    return normalized;
  };

  const overlapArea = (a, b) => {
    const left = Math.max(a.x, b.x);
    const top = Math.max(a.y, b.y);
    const right = Math.min(a.x + a.width, b.x + b.width);
    const bottom = Math.min(a.y + a.height, b.y + b.height);
    const width = Math.max(0, right - left);
    const height = Math.max(0, bottom - top);
    return width * height;
  };

  const locateTarget = (target, scanRows) => {
    const normalized = normalizeCanonicalTarget(target);
    const nodeId = String(normalized.nodeId || '').trim();
    if (nodeId) {
      const found = scanRows.find((item) => item.id === nodeId);
      if (found) return { el: found.el, strategy: 'nodeId', normalized };
    }

    const pathIndex = String(normalized.pathIndex || '').trim();
    if (pathIndex) {
      try {
        const byPath = document.querySelector(pathIndex);
        if (byPath && isVisible(byPath)) return { el: byPath, strategy: 'pathIndex', normalized };
      } catch {
      }
    }

    const selector = String(normalized.selector || '').trim();
    if (selector) {
      try {
        const matched = Array.from(document.querySelectorAll(selector)).filter(isVisible);
        const index = Number.isInteger(normalized.index) ? normalized.index : 0;
        if (matched.length > 0) {
          return { el: matched[index] || matched[0], strategy: 'selector', normalized };
        }
      } catch {
      }
    }

    if (normalized.bounds) {
      const box = normalized.bounds;
      let best = null;
      let bestOverlap = 0;
      for (const row of scanRows) {
        const candidateOverlap = overlapArea(row.node.bounds, box);
        if (candidateOverlap > bestOverlap) {
          best = row;
          bestOverlap = candidateOverlap;
        }
      }
      if (best && bestOverlap > 0) return { el: best.el, strategy: 'bounds_overlap', normalized };
      const centerX = box.x + box.width / 2;
      const centerY = box.y + box.height / 2;
      const byPoint = document.elementFromPoint(centerX, centerY);
      if (byPoint && isVisible(byPoint)) return { el: byPoint, strategy: 'bounds_center', normalized };
    }

    const textContains = String(normalized.textContains || '').trim();
    if (textContains) {
      const byText = scanRows.find((item) => safeText(item.el.textContent || '', 240).includes(textContains));
      if (byText) return { el: byText.el, strategy: 'text_contains', normalized };
    }
    return { el: null, strategy: '', normalized };
  };

  const dispatchInputEvents = (node) => {
    node.dispatchEvent(new Event('input', { bubbles: true }));
    node.dispatchEvent(new Event('change', { bubbles: true }));
  };

  const hasValueField = (node) => {
    if (!node || typeof node !== 'object') return false;
    try {
      return typeof node.value !== 'undefined';
    } catch {
      return false;
    }
  };

  const isContentEditableNode = (node) => {
    return Boolean(node && node instanceof HTMLElement && node.isContentEditable);
  };

  const setNodeTextValue = (node, value, mode = 'set') => {
    const nextValue = String(value ?? '');
    if (hasValueField(node)) {
      if (typeof node.focus === 'function') node.focus();
      if (mode === 'append') {
        node.value = String(node.value || '') + nextValue;
      } else {
        node.value = nextValue;
      }
      dispatchInputEvents(node);
      return { ok: true, value: node.value };
    }
    if (isContentEditableNode(node)) {
      if (typeof node.focus === 'function') node.focus();
      if (mode === 'append') {
        node.textContent = String(node.textContent || '') + nextValue;
      } else {
        node.textContent = nextValue;
      }
      dispatchInputEvents(node);
      return { ok: true, value: String(node.textContent || '') };
    }
    return { ok: false };
  };

  const getNodeDebug = (node) => {
    if (!(node instanceof Element)) {
      return { node_type: String(typeof node) };
    }
    return {
      tag: String(node.tagName || '').toLowerCase(),
      role: String(node.getAttribute('role') || ''),
      has_value_field: hasValueField(node),
      is_content_editable: isContentEditableNode(node),
    };
  };

  const captureScreenshot = async () => {
    try {
      const width = Math.max(
        document.documentElement.clientWidth || 0,
        window.innerWidth || 0,
        1
      );
      const height = Math.max(
        document.documentElement.clientHeight || 0,
        window.innerHeight || 0,
        1
      );
      const clone = document.documentElement.cloneNode(true);
      const serializer = new XMLSerializer();
      const xhtml = serializer.serializeToString(clone);
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '">'
        + '<foreignObject width="100%" height="100%">' + xhtml + '</foreignObject></svg>';
      const dataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      const image = new Image();
      image.decoding = 'async';
      const loaded = new Promise((resolve, reject) => {
        image.onload = () => resolve(true);
        image.onerror = (err) => reject(err || new Error('screenshot_image_load_failed'));
      });
      image.src = dataUrl;
      await loaded;
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        return { ok: false, error: 'canvas_context_unavailable' };
      }
      ctx.drawImage(image, 0, 0, width, height);
      const pngUrl = canvas.toDataURL('image/png');
      const base64 = String(pngUrl.split(',')[1] || '');
      if (!base64) {
        return { ok: false, error: 'empty_screenshot_payload' };
      }
      return { ok: true, mime: 'image/png', base64 };
    } catch (error) {
      return { ok: false, error: String(error && error.message ? error.message : error) };
    }
  };

  const maybeAttachScreenshot = async (container, includeScreenshot) => {
    if (!includeScreenshot) return;
    const snap = await captureScreenshot();
    if (snap.ok) {
      container.screenshot = { mime: snap.mime, base64: snap.base64 };
      return;
    }
    container.screenshot_error = snap.error || 'capture_failed';
  };

  const resolveScrollTarget = (target, scanRows) => {
    if (target && typeof target === 'object' && Object.keys(target).length > 0) {
      const found = locateTarget(target, scanRows);
      if (!found.el) {
        return {
          ok: false,
          error_code: 'target_not_found',
          message: 'target not found',
          details: {
            normalized_target: found.normalized,
            available_nodes: scanRows.length,
          },
        };
      }
      return { ok: true, element: found.el, strategy: found.strategy };
    }
    const root = document.scrollingElement || document.documentElement || document.body;
    return { ok: true, element: root, strategy: 'viewport' };
  };

  const getScrollMetrics = (element) => {
    const root = document.scrollingElement || document.documentElement || document.body;
    const isViewport = element === document.body || element === document.documentElement || element === root;
    if (isViewport) {
      const maxY = Math.max(0, (root.scrollHeight || 0) - (window.innerHeight || 0));
      const maxX = Math.max(0, (root.scrollWidth || 0) - (window.innerWidth || 0));
      return {
        isViewport: true,
        top: Number(root.scrollTop || window.scrollY || 0),
        left: Number(root.scrollLeft || window.scrollX || 0),
        maxY,
        maxX,
        viewportHeight: Math.max(1, Number(window.innerHeight || document.documentElement.clientHeight || 1)),
      };
    }
    const maxY = Math.max(0, Number(element.scrollHeight || 0) - Number(element.clientHeight || 0));
    const maxX = Math.max(0, Number(element.scrollWidth || 0) - Number(element.clientWidth || 0));
    return {
      isViewport: false,
      top: Number(element.scrollTop || 0),
      left: Number(element.scrollLeft || 0),
      maxY,
      maxX,
      viewportHeight: Math.max(1, Number(element.clientHeight || 1)),
    };
  };

  const setScrollPosition = (element, top, left, isViewport) => {
    if (isViewport) {
      window.scrollTo({ top, left, behavior: 'auto' });
      return;
    }
    if (typeof element.scrollTo === 'function') {
      element.scrollTo({ top, left, behavior: 'auto' });
      return;
    }
    element.scrollTop = top;
    element.scrollLeft = left;
  };

  const runScroll = async (payload) => {
    const scanRows = scanElements(STABLE_SCAN_LIMIT, 'visible');
    const targetResolution = resolveScrollTarget(payload.target || null, scanRows);
    if (!targetResolution.ok) return targetResolution;

    const element = targetResolution.element;
    const before = getScrollMetrics(element);

    const hasY = typeof payload.y === 'number' && Number.isFinite(payload.y);
    const hasX = typeof payload.x === 'number' && Number.isFinite(payload.x);
    const direction = String(payload.direction || '').trim().toLowerCase();
    const distanceValue = Number(payload.distance);
    const hasDistance = Number.isFinite(distanceValue) && distanceValue > 0;
    const distance = hasDistance ? distanceValue : Math.round(before.viewportHeight * 0.8);

    let nextTop = before.top;
    let nextLeft = before.left;
    let mode = '';

    if (hasY || hasX) {
      mode = 'absolute';
      if (hasY) nextTop = Math.max(0, Number(payload.y));
      if (hasX) nextLeft = Math.max(0, Number(payload.x));
    } else if (direction) {
      mode = 'direction';
      if (direction === 'top') {
        nextTop = 0;
      } else if (direction === 'bottom') {
        nextTop = before.maxY;
      } else if (direction === 'down') {
        nextTop = before.top + distance;
      } else if (direction === 'up') {
        nextTop = before.top - distance;
      } else {
        return {
          ok: false,
          error_code: 'invalid_direction',
          message: 'direction must be one of: up/down/top/bottom',
        };
      }
    } else {
      return {
        ok: false,
        error_code: 'invalid_scroll_input',
        message: 'scroll requires y/x or direction',
      };
    }

    const clampedTop = Math.max(0, Math.min(nextTop, before.maxY));
    const clampedLeft = Math.max(0, Math.min(nextLeft, before.maxX));
    setScrollPosition(element, clampedTop, clampedLeft, before.isViewport);

    const after = getScrollMetrics(element);
    return {
      ok: true,
      data: {
        x: Math.round(after.left),
        y: Math.round(after.top),
        max_x: Math.round(after.maxX),
        max_y: Math.round(after.maxY),
        target_strategy: targetResolution.strategy,
        mode,
      },
    };
  };

  const runAction = async (action, target, args, options) => {
    const scanRows = scanElements(STABLE_SCAN_LIMIT, 'visible');
    const found = locateTarget(target, scanRows);
    const node = found.el;
    if (!node) {
      return {
        ok: false,
        error_code: 'target_not_found',
        message: 'target not found',
        details: {
          normalized_target: found.normalized,
          available_nodes: scanRows.length,
        },
      };
    }
    const rawAction = String(action || '').trim();
    const actionName = ACTION_ALIASES[rawAction] || rawAction;
    if (!actionName) {
      return { ok: false, error_code: 'missing_action', message: 'action is required' };
    }
    if (actionName === 'click') {
      node.click();
      return { ok: true, data: { action: actionName, target_strategy: found.strategy } };
    }
    if (actionName === 'type' || actionName === 'clear_type') {
      const value = String((args || {}).text || (args || {}).value || '');
      if (actionName === 'clear_type') {
        const cleared = setNodeTextValue(node, '', 'set');
        if (!cleared.ok) {
          return {
            ok: false,
            error_code: 'unsupported_target',
            message: 'target has no value field',
            details: { target_strategy: found.strategy, ...getNodeDebug(node) },
          };
        }
      }
      const typed = setNodeTextValue(node, value, 'append');
      if (typed.ok) {
        return { ok: true, data: { action: actionName, value: typed.value, target_strategy: found.strategy } };
      }
      return {
        ok: false,
        error_code: 'unsupported_target',
        message: 'target has no value field',
        details: { target_strategy: found.strategy, ...getNodeDebug(node) },
      };
    }
    if (actionName === 'set_value') {
      const value = (args || {}).value;
      const set = setNodeTextValue(node, value, 'set');
      if (set.ok) {
        return { ok: true, data: { action: actionName, value: set.value, target_strategy: found.strategy } };
      }
      return {
        ok: false,
        error_code: 'unsupported_target',
        message: 'target has no value field',
        details: { target_strategy: found.strategy, ...getNodeDebug(node) },
      };
    }
    if (actionName === 'focus') {
      if (typeof node.focus === 'function') {
        node.focus();
        return { ok: true, data: { action: actionName, target_strategy: found.strategy } };
      }
      return { ok: false, error_code: 'unsupported_target', message: 'target cannot focus' };
    }
    if (actionName === 'press_key') {
      const key = String((args || {}).key || 'Enter');
      node.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      node.dispatchEvent(new KeyboardEvent('keyup', { key, bubbles: true }));
      return { ok: true, data: { action: actionName, key, target_strategy: found.strategy } };
    }
    return { ok: false, error_code: 'unsupported_action', message: 'unsupported action: ' + actionName };
  };

  const capabilityStore = (() => {
    const win = window;
    const key = '__DAWNCHAT_UI_CAPABILITIES__';
    const existing = win[key];
    if (existing && existing instanceof Map) {
      return existing;
    }
    const created = new Map();
    win[key] = created;
    return created;
  })();

  const registerCapability = (definition, handler) => {
    const name = String((definition || {}).name || '').trim();
    if (!name || typeof handler !== 'function') return false;
    capabilityStore.set(name, {
      name,
      description: String((definition || {}).description || '').trim(),
      input_schema:
        definition && typeof definition.input_schema === 'object' && definition.input_schema
          ? definition.input_schema
          : { type: 'object', properties: {} },
      handler,
    });
    return true;
  };

  const unregisterCapability = (name) => {
    const key = String(name || '').trim();
    if (!key) return false;
    return capabilityStore.delete(key);
  };

  const listCapabilities = () => {
    const items = [];
    for (const [name, item] of capabilityStore.entries()) {
      items.push({
        name,
        description: String(item.description || ''),
        input_schema:
          item && typeof item.input_schema === 'object' && item.input_schema
            ? item.input_schema
            : { type: 'object', properties: {} },
      });
    }
    return items.sort((a, b) => a.name.localeCompare(b.name));
  };

  const invokeCapability = async (name, payload, options) => {
    const key = String(name || '').trim();
    if (!key) {
      return { ok: false, error_code: 'missing_function', message: 'function is required' };
    }
    const item = capabilityStore.get(key);
    if (!item || typeof item.handler !== 'function') {
      return {
        ok: false,
        error_code: 'capability_not_found',
        message: 'capability not found: ' + key,
      };
    }
    try {
      const result = await item.handler(payload || {}, options || {});
      if (result && typeof result === 'object' && Object.prototype.hasOwnProperty.call(result, 'ok')) {
        return result;
      }
      return { ok: true, data: result };
    } catch (error) {
      return {
        ok: false,
        error_code: 'capability_runtime_error',
        message: String((error && error.message) || error || 'capability invoke failed'),
      };
    }
  };

  const hostInvokePending = new Map();
  let hostInvokeSeq = 0;
  const callHost = (functionName, payload = {}, options = {}) => {
    const normalizedFunction = String(functionName || '').trim();
    if (!normalizedFunction) {
      return Promise.resolve({
        ok: false,
        error_code: 'missing_function',
        message: 'function is required',
      });
    }
    const requestId = 'host_' + Date.now() + '_' + hostInvokeSeq;
    hostInvokeSeq += 1;
    return new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        hostInvokePending.delete(requestId);
        resolve({
          ok: false,
          error_code: 'host_invoke_timeout',
          message: 'host invoke timeout',
        });
      }, HOST_INVOKE_TIMEOUT_MS);
      hostInvokePending.set(requestId, { resolve, timer });
      if (window.parent !== window) {
        window.parent.postMessage(
          {
            type: HOST_INVOKE_REQUEST,
            pluginId: PLUGIN_ID,
            requestId,
            payload: {
              function: normalizedFunction,
              payload: payload && typeof payload === 'object' ? payload : {},
              options: options && typeof options === 'object' ? options : {},
            },
            ts: Date.now(),
          },
          '*'
        );
      } else {
        window.clearTimeout(timer);
        hostInvokePending.delete(requestId);
        resolve({
          ok: false,
          error_code: 'host_unavailable',
          message: 'host bridge unavailable',
        });
      }
    });
  };

  window.__DAWNCHAT_UI_REGISTER_CAPABILITY__ = registerCapability;
  window.__DAWNCHAT_UI_UNREGISTER_CAPABILITY__ = unregisterCapability;
  window.__DAWNCHAT_UI_LIST_CAPABILITIES__ = listCapabilities;
  window.__DAWNCHAT_HOST_INVOKE__ = callHost;
  window.__DAWNCHAT_HOST_VOICE__ = {
    speak: async (payload = {}) => await callHost('dawnchat.host.voice.speak', payload, {}),
    stop: async (payload = {}) => await callHost('dawnchat.host.voice.stop', payload, {}),
    status: async (payload = {}) => await callHost('dawnchat.host.voice.status', payload, {}),
  };

  const onMessage = async (event) => {
    const data = event && event.data;
    if (!data || typeof data !== 'object') return;
    if (data.pluginId && data.pluginId !== PLUGIN_ID) return;
    const type = String(data.type || '');
    const requestId = String(data.requestId || '');
    if (type === HOST_INVOKE_RESULT) {
      const pending = hostInvokePending.get(requestId);
      if (!pending) return;
      window.clearTimeout(pending.timer);
      hostInvokePending.delete(requestId);
      const result = data.result && typeof data.result === 'object' ? data.result : {
        ok: false,
        error_code: 'invalid_host_result',
        message: 'invalid host invoke result',
      };
      pending.resolve(result);
      return;
    }
    if (type === PREFIX + 'PING') {
      post(PREFIX + 'READY', requestId, { ok: true });
      return;
    }
    if (type === PREFIX + 'SNAPSHOT_REQUEST') {
      const payload = data.payload || {};
      const scanned = scanDescribeElements(payload.max_nodes || MAX_DEFAULT_NODES, payload.scope);
      const response = {
        ok: true,
        data: {
          scope: scanned.scope,
          nodes: scanned.rows.map((item) => item.node),
        },
      };
      await maybeAttachScreenshot(response.data, Boolean(payload.include_screenshot));
      post(PREFIX + 'SNAPSHOT_RESPONSE', requestId, response);
      return;
    }
    if (type === PREFIX + 'QUERY_REQUEST') {
      const payload = data.payload || {};
      const locator = payload.locator || {};
      const selector = String(locator.selector || '').trim();
      const scannedRows = scanElements(STABLE_SCAN_LIMIT);
      let matchedRows = [];
      if (selector) {
        try {
          matchedRows = scannedRows.filter((item) => item.el.matches(selector)).slice(0, 100);
        } catch {
          matchedRows = [];
        }
      } else {
        matchedRows = scannedRows.slice(0, 100);
      }
      const response = {
        ok: true,
        data: {
          nodes: matchedRows.map((item) => item.node),
        },
      };
      await maybeAttachScreenshot(response.data, Boolean(payload.include_screenshot));
      post(PREFIX + 'QUERY_RESPONSE', requestId, response);
      return;
    }
    if (type === PREFIX + 'CAPABILITIES_LIST_REQUEST') {
      post(PREFIX + 'CAPABILITIES_LIST_RESPONSE', requestId, {
        ok: true,
        data: {
          functions: listCapabilities(),
        },
      });
      return;
    }
    if (type === PREFIX + 'CAPABILITY_INVOKE_REQUEST') {
      const payload = data.payload || {};
      const result = await invokeCapability(payload.function, payload.payload || {}, payload.options || {});
      post(PREFIX + 'CAPABILITY_INVOKE_RESULT', requestId, result);
      return;
    }
    if (type === PREFIX + 'RUNTIME_REFRESH_REQUEST') {
      post(PREFIX + 'RUNTIME_REFRESH_RESULT', requestId, {
        ok: true,
        data: {
          accepted: true,
        },
      });
      setTimeout(() => {
        window.location.reload();
      }, 40);
      return;
    }
    if (type === PREFIX + 'ACTION_REQUEST') {
      const payload = data.payload || {};
      const result = await runAction(payload.action, payload.target || {}, payload.args || {}, payload.options || {});
      if (result && result.ok && payload.options && payload.options.capture_after) {
        result.data = result.data || {};
        await maybeAttachScreenshot(result.data, true);
      }
      post(PREFIX + 'ACTION_RESULT', requestId, result);
      return;
    }
    if (type === PREFIX + 'SCROLL_REQUEST') {
      const payload = data.payload || {};
      const result = await runScroll(payload);
      if (result && result.ok && payload.options && payload.options.capture_after) {
        result.data = result.data || {};
        await maybeAttachScreenshot(result.data, true);
      }
      post(PREFIX + 'SCROLL_RESULT', requestId, result);
    }
  };

  installLogCapture();
  window.addEventListener('message', onMessage);
  post(PREFIX + 'READY', '', { ok: true });
})();
`
}
