export function createInspectorRuntimeScript(currentPluginId, webRootDir) {
  const escapedPluginId = JSON.stringify(currentPluginId)
  const escapedWebRootDir = JSON.stringify(webRootDir)
  return `
(() => {
  if (window.__DAWNCHAT_INSPECTOR_BRIDGE__) {
    return;
  }
  window.__DAWNCHAT_INSPECTOR_BRIDGE__ = true;

  const PLUGIN_ID = ${escapedPluginId};
  const WEB_ROOT_DIR = ${escapedWebRootDir};
  const MESSAGE_PREFIX = 'DAWNCHAT_INSPECTOR_';
  const RUNTIME_VERSION = '1';
  let enabled = false;
  let overlay = null;
  let rafToken = null;
  let pendingHoverTarget = null;

  const post = (type, payload = {}) => {
    if (window.parent === window) {
      return;
    }
    window.parent.postMessage({
      type,
      pluginId: PLUGIN_ID,
      version: RUNTIME_VERSION,
      ts: Date.now(),
      ...payload
    }, '*');
  };

  const ensureOverlay = () => {
    if (overlay) return overlay;
    const node = document.createElement('div');
    node.style.position = 'fixed';
    node.style.pointerEvents = 'none';
    node.style.zIndex = '2147483647';
    node.style.border = '2px solid #3b82f6';
    node.style.background = 'rgba(59,130,246,0.12)';
    node.style.borderRadius = '4px';
    node.style.display = 'none';
    document.documentElement.appendChild(node);
    overlay = node;
    return overlay;
  };

  const hideOverlay = () => {
    if (!overlay) return;
    overlay.style.display = 'none';
  };

  const normalizePath = (value) => String(value || '').replace(/\\\\+/g, '/');

  const toFileSystemPathFromFileUrl = (fileUrl) => {
    if (!fileUrl || typeof fileUrl !== 'string') return '';
    try {
      const parsed = new URL(fileUrl);
      if (parsed.protocol !== 'file:') return '';
      let pathname = decodeURIComponent(parsed.pathname || '');
      if (/^\\/[A-Za-z]:\\//.test(pathname)) {
        pathname = pathname.slice(1);
      }
      return normalizePath(pathname);
    } catch {
      return '';
    }
  };

  const joinPath = (base, relative) => {
    const safeBase = normalizePath(base).replace(/\\/+$/, '');
    const safeRelative = normalizePath(relative).replace(/^\\/+/, '');
    if (!safeBase) return safeRelative;
    if (!safeRelative) return safeBase;
    return safeBase + '/' + safeRelative;
  };

  const resolveInspectorFile = (rawFile) => {
    if (!rawFile || typeof rawFile !== 'string') return '';
    const trimmed = rawFile.trim();
    if (!trimmed) return '';

    const fileUrlResolved = toFileSystemPathFromFileUrl(trimmed);
    if (fileUrlResolved) {
      return fileUrlResolved;
    }

    const normalized = normalizePath(trimmed);
    if (normalized.startsWith('/@fs/')) {
      return normalized.slice('/@fs'.length);
    }
    if (/^[A-Za-z]:\\//.test(normalized)) {
      return normalized;
    }
    if (normalized.startsWith('/') && !normalized.startsWith('/src/')) {
      return normalized;
    }

    const withoutAlias = normalized.startsWith('@/') ? ('src/' + normalized.slice(2)) : normalized;
    const relative = withoutAlias.replace(/^\\.?\\//, '').replace(/^\\/+/, '');
    if (!relative) return normalized;
    return joinPath(WEB_ROOT_DIR, relative);
  };

  const toRelativeFromWebRoot = (absoluteFile) => {
    const file = normalizePath(absoluteFile);
    const root = normalizePath(WEB_ROOT_DIR).replace(/\\/+$/, '');
    if (!file || !root) return '';
    const prefix = root + '/';
    if (file.startsWith(prefix)) {
      return file.slice(prefix.length);
    }
    return '';
  };

  const parseInspectorMeta = (raw) => {
    if (!raw || typeof raw !== 'string') return null;
    const match = raw.match(/^(.*?):(\\d+):(\\d+)(?::(\\d+):(\\d+))?$/);
    if (!match) return null;
    const resolvedFile = resolveInspectorFile(match[1]);
    return {
      file: resolvedFile || match[1],
      fileRelative: toRelativeFromWebRoot(resolvedFile),
      range: {
        start: {
          line: Number(match[2]),
          column: Number(match[3])
        },
        end: match[4] && match[5]
          ? {
              line: Number(match[4]),
              column: Number(match[5])
            }
          : undefined
      }
    };
  };

  const resolveVNodeInspectorRaw = (node) => {
    if (!(node instanceof Element)) return '';
    const direct = node?.__vnode?.props?.__v_inspector;
    if (typeof direct === 'string' && direct) return direct;
    const ctxVNode = node?.__vnode?.ctx?.vnode?.props?.__v_inspector;
    if (typeof ctxVNode === 'string' && ctxVNode) return ctxVNode;
    return '';
  };

  const hasInspectorHints = (node) => {
    if (!(node instanceof Element)) return false;
    if (resolveVNodeInspectorRaw(node)) return true;
    const attrs = Array.from(node.attributes || []);
    return attrs.some((attr) => {
      const name = String(attr.name || '').toLowerCase();
      return (
        name.includes('inspector') ||
        name.includes('source-location') ||
        name === 'data-v-inspector-file' ||
        name === 'data-v-inspector-line' ||
        name === 'data-v-inspector-column'
      );
    });
  };

  const buildRawFromSplitAttrs = (node) => {
    if (!(node instanceof Element)) return '';
    const file = node.getAttribute('data-v-inspector-file');
    const line = node.getAttribute('data-v-inspector-line');
    const column = node.getAttribute('data-v-inspector-column');
    if (!file || !line || !column) return '';
    return file + ':' + line + ':' + column;
  };

  const normalizeSnippet = (value, maxLen = 180) => {
    if (!value) return '';
    const text = String(value).replace(/\\s+/g, ' ').trim();
    if (text.length <= maxLen) return text;
    return text.slice(0, maxLen) + '...';
  };

  const toSelector = (node) => {
    if (!node || !(node instanceof Element)) return '';
    if (node.id) return '#' + node.id;
    const className = Array.from(node.classList || []).slice(0, 3).join('.');
    const tag = node.tagName.toLowerCase();
    return className ? tag + '.' + className : tag;
  };

  const findInspectorNode = (target) => {
    if (!(target instanceof Element)) return null;
    const directMatch = (
      target.closest('[data-v-inspector]') ||
      target.closest('[data-inspector]') ||
      target.closest('[data-source-location]')
    );
    if (directMatch) return directMatch;
    let current = target;
    while (current) {
      if (hasInspectorHints(current)) {
        return current;
      }
      current = current.parentElement;
    }
    return null;
  };

  const findHoverNode = (target) => {
    if (!(target instanceof Element)) return null;
    return findInspectorNode(target) || target;
  };

  const resolveInspectorRaw = (targetNode) => {
    if (!(targetNode instanceof Element)) return '';
    const vnodeRaw = resolveVNodeInspectorRaw(targetNode);
    if (vnodeRaw) return vnodeRaw;
    const directRaw = (
      targetNode.getAttribute('data-v-inspector') ||
      targetNode.getAttribute('data-inspector') ||
      targetNode.getAttribute('data-source-location') ||
      ''
    );
    if (directRaw) return directRaw;
    return buildRawFromSplitAttrs(targetNode);
  };

  const collectNodeDebug = (node) => {
    if (!(node instanceof Element)) {
      return { targetType: typeof node };
    }
    const attrs = Array.from(node.attributes || []).map((attr) => attr.name);
    const hintAttrs = attrs.filter((name) => /inspector|source-location/i.test(name));
    return {
      tag: String(node.tagName || '').toLowerCase(),
      id: node.id || '',
      className: normalizeSnippet(node.className || '', 120),
      vnodeInspector: normalizeSnippet(resolveVNodeInspectorRaw(node), 220),
      hintAttrs,
      attrCount: attrs.length,
    };
  };

  const collectInspectorStats = () => {
    try {
      const allNodes = document.querySelectorAll('*');
      const scanLimit = Math.min(allNodes.length, 600);
      let vnodeInspectorSampleCount = 0;
      for (let index = 0; index < scanLimit; index += 1) {
        const node = allNodes[index];
        if (resolveVNodeInspectorRaw(node)) {
          vnodeInspectorSampleCount += 1;
          if (vnodeInspectorSampleCount >= 5) {
            break;
          }
        }
      }
      return {
        dataVInspector: document.querySelectorAll('[data-v-inspector]').length,
        dataInspector: document.querySelectorAll('[data-inspector]').length,
        dataSourceLocation: document.querySelectorAll('[data-source-location]').length,
        dataVInspectorFile: document.querySelectorAll('[data-v-inspector-file]').length,
        vnodeInspectorDetected: vnodeInspectorSampleCount > 0,
        vnodeInspectorSampleCount,
      };
    } catch {
      return {
        dataVInspector: -1,
        dataInspector: -1,
        dataSourceLocation: -1,
        dataVInspectorFile: -1,
        vnodeInspectorDetected: false,
        vnodeInspectorSampleCount: -1,
      };
    }
  };

  const paintOverlay = (targetNode) => {
    if (!targetNode || !enabled) {
      hideOverlay();
      return;
    }
    const layer = ensureOverlay();
    const rect = targetNode.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      hideOverlay();
      return;
    }
    layer.style.display = 'block';
    layer.style.left = rect.left + 'px';
    layer.style.top = rect.top + 'px';
    layer.style.width = rect.width + 'px';
    layer.style.height = rect.height + 'px';
  };

  const flushHoverFrame = () => {
    rafToken = null;
    paintOverlay(pendingHoverTarget);
  };

  const queueHoverPaint = (node) => {
    pendingHoverTarget = node;
    if (rafToken != null) return;
    rafToken = requestAnimationFrame(flushHoverFrame);
  };

  const onMouseMove = (event) => {
    if (!enabled) return;
    queueHoverPaint(findHoverNode(event.target));
  };

  const onClickCapture = (event) => {
    if (!enabled) return;
    const rawTarget = event.target;
    const targetNode = findInspectorNode(rawTarget);
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    if (!targetNode) {
      post(MESSAGE_PREFIX + 'ERROR', {
        message: 'Element not mappable',
        reason: 'no_inspector_node',
        stats: collectInspectorStats(),
        target: collectNodeDebug(rawTarget),
      });
      return;
    }
    const raw = resolveInspectorRaw(targetNode);
    const parsed = parseInspectorMeta(raw);
    if (!parsed) {
      post(MESSAGE_PREFIX + 'ERROR', {
        message: 'Inspector metadata missing',
        reason: 'invalid_or_missing_metadata',
        metadata: normalizeSnippet(raw, 220),
        stats: collectInspectorStats(),
        target: collectNodeDebug(targetNode),
      });
      return;
    }
    post(MESSAGE_PREFIX + 'SELECT', {
      file: parsed.file,
      fileRelative: parsed.fileRelative,
      range: parsed.range,
      selector: toSelector(targetNode),
      textSnippet: normalizeSnippet(targetNode.textContent || ''),
      htmlSnippet: normalizeSnippet(targetNode.outerHTML || '', 260)
    });
  };

  const setEnabled = (nextEnabled) => {
    enabled = Boolean(nextEnabled);
    if (!enabled) {
      hideOverlay();
      return;
    }
    const stats = collectInspectorStats();
    const domInspectorTotal = (
      stats.dataVInspector +
      stats.dataInspector +
      stats.dataSourceLocation +
      stats.dataVInspectorFile
    );
    if (domInspectorTotal <= 0 && !stats.vnodeInspectorDetected) {
      post(MESSAGE_PREFIX + 'ERROR', {
        message: 'Inspector attributes not found in DOM',
        reason: 'inspector_attrs_absent',
        stats,
      });
    }
  };

  const onHostMessage = (event) => {
    const data = event?.data;
    if (!data || typeof data !== 'object') return;
    if (data.pluginId && data.pluginId !== PLUGIN_ID) return;
    const type = String(data.type || '');
    if (!type.startsWith(MESSAGE_PREFIX)) return;
    if (type === MESSAGE_PREFIX + 'PING') {
      post(MESSAGE_PREFIX + 'READY');
      return;
    }
    if (type === MESSAGE_PREFIX + 'ENABLE') {
      setEnabled(true);
      return;
    }
    if (type === MESSAGE_PREFIX + 'DISABLE') {
      setEnabled(false);
    }
  };

  window.addEventListener('message', onHostMessage);
  window.addEventListener('mousemove', onMouseMove, { passive: true });
  window.addEventListener('click', onClickCapture, true);
  window.addEventListener('beforeunload', () => {
    if (rafToken != null) {
      cancelAnimationFrame(rafToken);
      rafToken = null;
    }
  });

  post(MESSAGE_PREFIX + 'READY');
})();
`
}
