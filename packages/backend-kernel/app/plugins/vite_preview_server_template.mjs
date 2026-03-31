import { createServer, loadConfigFromFile, mergeConfig } from 'vite'
import path from 'node:path'
import fs from 'node:fs'
import crypto from 'node:crypto'
import { createInspectorRuntimeScript } from './preview_runtime/inspector_runtime_template.mjs'
import { createHostStyleRuntimeScript } from './preview_runtime/host_style_runtime_template.mjs'
import { createUiAgentRuntimeScript } from './preview_runtime/ui_agent_runtime_template.mjs'

const root = process.argv[2]
const host = process.argv[3]
const frontendPort = Number(process.argv[4])
const backendPort = Number(process.argv[5])
const pluginId = process.argv[6] || 'unknown-plugin'
const previewDir = path.join(root, '.dawnchat-preview')
const previewCacheDir = path.join(previewDir, '.vite-cache')
const appVuePath = path.join(root, 'src', 'App.vue')

function describeFile(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8')
    const hasTemplate = content.includes('<template')
    const hasScript = content.includes('<script')
    const hash = crypto.createHash('sha256').update(content).digest('hex').slice(0, 16)
    console.log(
      `[dawnchat-preview] sfc_snapshot file=${filePath} bytes=${Buffer.byteLength(content)} hasTemplate=${hasTemplate} hasScript=${hasScript} sha16=${hash}`
    )
  } catch (err) {
    console.warn(`[dawnchat-preview] sfc_snapshot_failed file=${filePath} err=${String(err?.message || err)}`)
  }
}

try {
  fs.rmSync(previewCacheDir, { recursive: true, force: true })
} catch (err) {
  console.warn(`[dawnchat-preview] cache_cleanup_failed err=${String(err?.message || err)}`)
}
describeFile(appVuePath)

const backendProxy =
  Number.isFinite(backendPort) && backendPort > 0
    ? {
        '/api': `http://${host}:${backendPort}`,
      }
    : {}

const loaded = await loadConfigFromFile(
  { command: 'serve', mode: 'development' },
  undefined,
  root
)
const userConfig = loaded?.config ?? {}
let inspectorFactory = null
let inspectorPluginLoadError = ''
try {
  const inspectorModule = await import('vite-plugin-vue-inspector')
  inspectorFactory =
    inspectorModule?.default || inspectorModule?.viteInspector || inspectorModule?.createInspector
} catch (err) {
  inspectorPluginLoadError = String(err?.message || err || '')
  console.warn(`[dawnchat-preview] inspector_plugin_unavailable plugin=${pluginId} err=${inspectorPluginLoadError}`)
}
const inspectorPlugin =
  typeof inspectorFactory === 'function'
    ? inspectorFactory({
        toggleButtonVisibility: 'never',
        cleanHtml: false,
      })
    : null
const inspectorBridgePlugin = {
  name: 'dawnchat-preview-inspector-bridge',
  transformIndexHtml() {
    return [
      {
        tag: 'script',
        attrs: { type: 'module' },
        children: createInspectorRuntimeScript(pluginId, root),
        injectTo: 'head-prepend',
      },
      {
        tag: 'script',
        attrs: { type: 'module' },
        children: createUiAgentRuntimeScript(pluginId),
        injectTo: 'head-prepend',
      },
      {
        tag: 'script',
        attrs: { type: 'module' },
        children: createHostStyleRuntimeScript(pluginId),
        injectTo: 'head-prepend',
      },
    ]
  },
}
const inspectorAvailabilityPlugin = {
  name: 'dawnchat-preview-inspector-availability',
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      const pathname = (req.url || '').split('?')[0]
      if (pathname !== '/__dawnchat/inspector-status') {
        next()
        return
      }
      const payload = {
        pluginId,
        enabled: Boolean(inspectorPlugin),
        reason: inspectorPlugin ? '' : inspectorPluginLoadError || 'vite-plugin-vue-inspector not found',
      }
      res.statusCode = 200
      res.setHeader('Content-Type', 'application/json; charset=utf-8')
      res.end(JSON.stringify(payload))
    })
  },
}
const sfcDebugPlugin = {
  name: 'dawnchat-preview-debug-vue-sfc',
  enforce: 'pre',
  transform(code, id) {
    if (typeof id === 'string' && id.includes('/src/') && id.endsWith('.vue')) {
      const hasTemplate = code.includes('<template')
      const hasScript = code.includes('<script')
      const hash = crypto.createHash('sha256').update(code).digest('hex').slice(0, 16)
      console.log(
        `[dawnchat-preview] sfc_transform id=${id} bytes=${Buffer.byteLength(code)} hasTemplate=${hasTemplate} hasScript=${hasScript} sha16=${hash}`
      )
    }
    return null
  },
}

const merged = mergeConfig(userConfig, {
  root,
  clearScreen: false,
  cacheDir: previewCacheDir,
  plugins: [sfcDebugPlugin, inspectorPlugin, inspectorBridgePlugin, inspectorAvailabilityPlugin].filter(Boolean),
  server: {
    host,
    port: frontendPort,
    strictPort: true,
    watch: {
      // Prevent transient parse failures when editors save files atomically.
      awaitWriteFinish: {
        stabilityThreshold: 200,
        pollInterval: 50,
      },
    },
    proxy: backendProxy,
  },
})

// Avoid Vite loading config file again in createServer().
const server = await createServer({
  ...merged,
  configFile: false,
})
const pluginNames = (server.config?.plugins || []).map((plugin) => plugin?.name || '(anonymous)')
const vuePluginCount = pluginNames.filter((name) => name === 'vite:vue').length
console.log(
  `[dawnchat-preview] vite_plugins total=${pluginNames.length} vue=${vuePluginCount} names=${pluginNames.join(',')}`
)
await server.listen()
console.log(`[dawnchat-preview] vite ready: http://${host}:${frontendPort}`)
