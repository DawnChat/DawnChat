import { API_BASE } from '@/stores/plugin/api/client'
import { logger } from '@/utils/logger'
import type { PluginStoreContext } from '@/stores/plugin/context'

export function createInstallActions(ctx: PluginStoreContext) {
  const getInstallProgress = (appId: string) => {
    return ctx.state.installProgressMap.value.get(appId) || null
  }

  const stopInstallPolling = (appId: string) => {
    ctx.state.installPollers.clear(appId)
  }

  const pollInstallProgress = async (appId: string) => {
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}/install/progress`)
      const data = await res.json()
      if (data.status === 'success' && data.progress) {
        ctx.state.installProgressMap.value.set(appId, data.progress)
        const status = String(data.progress.status || '')
        if (['ready', 'failed'].includes(status)) {
          stopInstallPolling(appId)
          if (status === 'ready') {
            await ctx.runtimeActions.refreshInstalledApp(appId)
            ctx.marketActions.patchMarketApp(appId, {
              installed: true,
              installed_version: data.progress.version || ctx.state.marketApps.value.find((item) => item.id === appId)?.version,
            })
          } else {
            ctx.marketActions.patchMarketApp(appId, { installed: false })
          }
        }
      }
    } catch (err) {
      logger.error('Failed to poll install progress:', err)
    }
  }

  const startInstallPolling = (appId: string) => {
    stopInstallPolling(appId)
    void pollInstallProgress(appId)
    const timer = setInterval(() => {
      void pollInstallProgress(appId)
    }, 1500)
    ctx.state.installPollers.set(appId, timer)
  }

  const installApp = async (appId: string) => {
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      const data = await res.json()
      if (data.status === 'accepted') {
        startInstallPolling(appId)
      }
    } catch (err) {
      logger.error('Failed to install app:', err)
    }
  }

  const updateApp = async (appId: string) => {
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}/update`, { method: 'POST' })
      const data = await res.json()
      if (data.status === 'accepted') {
        startInstallPolling(appId)
      }
    } catch (err) {
      logger.error('Failed to update app:', err)
    }
  }

  const uninstallApp = async (appId: string) => {
    try {
      await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}`, { method: 'DELETE' })
      ctx.state.installedApps.value = ctx.state.installedApps.value.filter((item) => item.id !== appId)
      if (ctx.state.activeApp.value?.id === appId) {
        ctx.state.activeApp.value = null
      }
      ctx.marketActions.patchMarketApp(appId, {
        installed: false,
        installed_version: null,
      })
    } catch (err) {
      logger.error('Failed to uninstall app:', err)
    }
  }

  return {
    getInstallProgress,
    stopInstallPolling,
    pollInstallProgress,
    startInstallPolling,
    installApp,
    updateApp,
    uninstallApp,
  }
}
