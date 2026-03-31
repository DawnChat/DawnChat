export function createHostStyleRuntimeScript(currentPluginId) {
  const escapedPluginId = JSON.stringify(currentPluginId)
  return `
(() => {
  if (window.__DAWNCHAT_HOST_STYLE_RUNTIME__) return;
  window.__DAWNCHAT_HOST_STYLE_RUNTIME__ = true;

  const PLUGIN_ID = ${escapedPluginId};
  const PREFIX = 'DAWNCHAT_HOST_STYLE_';
  const STYLE_ID = 'dawnchat-host-style-runtime';
  const ROOT = document.documentElement;

  const post = (type, payload = {}) => {
    if (window.parent === window) return;
    window.parent.postMessage(
      {
        type,
        pluginId: PLUGIN_ID,
        ts: Date.now(),
        ...payload,
      },
      '*'
    );
  };

  const ensureStyleElement = () => {
    let style = document.getElementById(STYLE_ID);
    if (style instanceof HTMLStyleElement) return style;
    style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = \`
html {
  scrollbar-color: var(--color-scrollbar-thumb) var(--color-scrollbar-track);
}
* {
  scrollbar-width: thin;
  scrollbar-color: var(--color-scrollbar-thumb) var(--color-scrollbar-track);
}
*::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
*::-webkit-scrollbar-track {
  background: var(--color-scrollbar-track);
  border-radius: 999px;
}
*::-webkit-scrollbar-thumb {
  background: var(--color-scrollbar-thumb);
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--color-scrollbar-track) 40%, transparent);
}
*::-webkit-scrollbar-thumb:hover {
  background: var(--color-scrollbar-thumb-hover);
}
\`;
    document.head.appendChild(style);
    return style;
  };

  const applyTokens = (tokens) => {
    if (!tokens || typeof tokens !== 'object') return;
    Object.entries(tokens).forEach(([key, value]) => {
      if (typeof key !== 'string' || !key.startsWith('--')) return;
      if (typeof value !== 'string' || !value) return;
      ROOT.style.setProperty(key, value);
    });
  };

  const onHostMessage = (event) => {
    const data = event?.data;
    if (!data || typeof data !== 'object') return;
    if (data.pluginId && data.pluginId !== PLUGIN_ID) return;
    const type = String(data.type || '');
    if (!type.startsWith(PREFIX)) return;
    if (type === PREFIX + 'SYNC') {
      ensureStyleElement();
      applyTokens(data.tokens);
      return;
    }
    if (type === PREFIX + 'PING') {
      post(PREFIX + 'READY');
    }
  };

  window.addEventListener('message', onHostMessage);
  ensureStyleElement();
  post(PREFIX + 'READY');
})();
`
}
