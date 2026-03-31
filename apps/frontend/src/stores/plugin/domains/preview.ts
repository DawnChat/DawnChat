import { API_BASE } from '@/stores/plugin/api/client'
import { logger } from '@/utils/logger'
import type { Plugin } from '@/types'
import type { PluginStoreContext } from '@/stores/plugin/context'

export function createPreviewActions(ctx: PluginStoreContext) {
  const refreshPreviewStatus = async (appId: string) => {
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}/preview/status`)
      if (!res.ok) return
      const data = await res.json()
      if (data.status !== 'success') return
      const preview = data.preview
      const app = ctx.state.installedApps.value.find((item: Plugin) => item.id === appId)
      if (app) {
        app.preview = {
          ...preview,
          workbench_layout: preview?.workbench_layout || app.preview?.workbench_layout || 'default',
        }
        if (ctx.state.activeApp.value?.id === appId) {
          ctx.state.activeApp.value = { ...app }
        }
      }
    } catch (err) {
      logger.error('Failed to refresh preview status:', err)
    }
  }

  const startPreview = async (appId: string): Promise<boolean> => {
    if (ctx.state.previewStartingMap.value.get(appId)) return false
    ctx.state.previewStartingMap.value.set(appId, true)
    const app = ctx.state.installedApps.value.find((item: Plugin) => item.id === appId)
    if (app) {
      app.preview = {
        state: 'starting',
        url: app.preview?.url ?? null,
        backend_port: app.preview?.backend_port ?? null,
        frontend_port: app.preview?.frontend_port ?? null,
        log_session_id: app.preview?.log_session_id ?? null,
        error_message: null,
        frontend_mode: app.preview?.frontend_mode ?? 'dev',
        deps_ready: app.preview?.deps_ready ?? true,
        install_status: app.preview?.install_status ?? 'idle',
        install_error_message: app.preview?.install_error_message ?? null,
        workbench_layout: app.preview?.workbench_layout ?? 'default',
      }
    }
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}/preview/start`, { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        await ctx.runtimeActions.refreshInstalledApp(appId)
        await refreshPreviewStatus(appId)
        return true
      }
      await refreshPreviewStatus(appId)
      return false
    } catch (err) {
      logger.error('Failed to start app preview:', err)
      await refreshPreviewStatus(appId)
      return false
    } finally {
      ctx.state.previewStartingMap.value.delete(appId)
    }
  }

  const startPreviewAndWaitReady = async (
    appId: string,
    options: { timeoutMs?: number; pollIntervalMs?: number } = {},
  ): Promise<boolean> => {
    const timeoutMs = options.timeoutMs ?? 45000
    const pollIntervalMs = options.pollIntervalMs ?? 1200
    const started = await startPreview(appId)
    if (!started) return false
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      await refreshPreviewStatus(appId)
      const app = ctx.state.installedApps.value.find((item: Plugin) => item.id === appId)
      const previewState = app?.preview?.state
      if (previewState === 'running' && app?.preview?.url) return true
      if (previewState === 'error') return false
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs))
    }
    return false
  }

  const stopPreview = async (appId: string): Promise<boolean> => {
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}/preview/stop`, { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        await refreshPreviewStatus(appId)
        return true
      }
      return false
    } catch (err) {
      logger.error('Failed to stop app preview:', err)
      return false
    }
  }

  const retryPreviewInstall = async (appId: string): Promise<boolean> => {
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}/preview/retry-install`, { method: 'POST' })
      if (!res.ok) {
        const detail = await res.text().catch(() => '')
        throw new Error(detail || `retry preview install failed: ${res.status}`)
      }
      await refreshPreviewStatus(appId)
      return true
    } catch (err) {
      logger.error('Failed to retry app preview install:', err)
      return false
    }
  }

  const isPreviewStarting = (appId: string) => {
    return Boolean(ctx.state.previewStartingMap.value.get(appId))
  }

  return {
    refreshPreviewStatus,
    startPreview,
    startPreviewAndWaitReady,
    retryPreviewInstall,
    stopPreview,
    isPreviewStarting,
  }
}
