import type { Router } from 'vue-router'
import { isTauri } from '@/adapters/env'
import { logger } from '@/utils/logger'
import { APPS_HUB_PATH } from '@/app/router/paths'

export type PluginRuntimeSurfaceMode = 'embedded' | 'windowed'

const RUNTIME_SURFACE_MODE_STORAGE_KEY = 'dawnchat.plugin.runtime.surface.mode'
const RUNTIME_WINDOW_LABEL_PREFIX = 'plugin_runtime__'
const DEFAULT_RUNTIME_WINDOW_WIDTH = 1280
const DEFAULT_RUNTIME_WINDOW_HEIGHT = 860

const buildEmbeddedRuntimeRoute = (
  pluginId: string,
  from = APPS_HUB_PATH,
  mode: 'normal' | 'preview' = 'normal',
) => ({
  name: 'plugin-fullscreen' as const,
  params: { pluginId },
  query: { from, mode },
})

const normalizeWindowLabelSegment = (pluginId: string): string => {
  const normalized = String(pluginId || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return normalized.slice(0, 48) || 'plugin'
}

const buildRuntimeWindowLabel = (pluginId: string): string => {
  return `${RUNTIME_WINDOW_LABEL_PREFIX}${normalizeWindowLabelSegment(pluginId)}`
}

const resolveConfiguredRuntimeSurfaceMode = (): PluginRuntimeSurfaceMode => {
  const envMode = String(import.meta.env.VITE_PLUGIN_RUNTIME_SURFACE_MODE || '').trim().toLowerCase()
  if (envMode === 'embedded' || envMode === 'windowed') {
    return envMode
  }
  try {
    const storedMode = String(localStorage.getItem(RUNTIME_SURFACE_MODE_STORAGE_KEY) || '').trim().toLowerCase()
    if (storedMode === 'embedded' || storedMode === 'windowed') {
      return storedMode
    }
  } catch {
  }
  return 'embedded'
}

export const resolvePluginRuntimeSurfaceMode = (): PluginRuntimeSurfaceMode => {
  if (!isTauri()) {
    return 'embedded'
  }
  return resolveConfiguredRuntimeSurfaceMode()
}

const buildRuntimeWindowUrl = (
  pluginId: string,
  from = APPS_HUB_PATH,
  mode: 'normal' | 'preview' = 'normal',
): string => {
  const params = new URLSearchParams()
  params.set('from', from)
  params.set('mode', mode)
  return `/#/fullscreen/plugin/${encodeURIComponent(pluginId)}?${params.toString()}`
}

const focusRuntimeWindow = async (
  windowRef: { show?: () => Promise<void>; setFocus?: () => Promise<void> }
): Promise<void> => {
  if (typeof windowRef.show === 'function') {
    await windowRef.show().catch(() => {})
  }
  if (typeof windowRef.setFocus === 'function') {
    await windowRef.setFocus().catch(() => {})
  }
}

const openPluginRuntimeWindow = async (
  pluginId: string,
  from = APPS_HUB_PATH,
  mode: 'normal' | 'preview' = 'normal',
): Promise<boolean> => {
  if (!isTauri()) {
    return false
  }
  try {
    const { WebviewWindow } = await import('@tauri-apps/api/webviewWindow')
    const label = buildRuntimeWindowLabel(pluginId)
    const existingWindow = await WebviewWindow.getByLabel(label)
    if (existingWindow) {
      await focusRuntimeWindow(existingWindow)
      return true
    }
    const url = buildRuntimeWindowUrl(pluginId, from, mode)
    const runtimeWindow = new WebviewWindow(label, {
      title: `DawnChat · ${pluginId}`,
      url,
      width: DEFAULT_RUNTIME_WINDOW_WIDTH,
      height: DEFAULT_RUNTIME_WINDOW_HEIGHT,
      center: true,
      resizable: true,
    })
    runtimeWindow.once('tauri://error', (event) => {
      logger.warn('plugin_runtime_window_create_failed', {
        pluginId,
        error: String(event.payload || ''),
      })
    })
    await focusRuntimeWindow(runtimeWindow)
    return true
  } catch (error) {
    logger.warn('plugin_runtime_window_open_failed', {
      pluginId,
      error: String(error),
    })
    return false
  }
}

export const openPluginRuntimeSurface = async (
  router: Router,
  pluginId: string,
  from = APPS_HUB_PATH,
  mode: 'normal' | 'preview' = 'normal',
): Promise<void> => {
  const surfaceMode = resolvePluginRuntimeSurfaceMode()
  if (surfaceMode === 'windowed') {
    const opened = await openPluginRuntimeWindow(pluginId, from, mode)
    if (opened) {
      return
    }
  }
  await router.push(buildEmbeddedRuntimeRoute(pluginId, from, mode))
}
