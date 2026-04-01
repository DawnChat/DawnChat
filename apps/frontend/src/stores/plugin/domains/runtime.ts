import { API_BASE } from '@/stores/plugin/api/client'
import { logger } from '@/utils/logger'
import { useEnvironmentStore } from '@/features/environment/store'
import type { Plugin, PluginRunMode } from '@/types'
import type { PluginStoreContext } from '@/stores/plugin/context'

export function createRuntimeActions(ctx: PluginStoreContext) {
  const upsertInstalledApp = (plugin: Plugin) => {
    const index = ctx.state.installedApps.value.findIndex((item) => item.id === plugin.id)
    if (index >= 0) {
      ctx.state.installedApps.value[index] = plugin
    } else {
      ctx.state.installedApps.value.push(plugin)
    }
  }

  const fetchInstalledApp = async (appId: string): Promise<Plugin | null> => {
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}`)
      if (!res.ok) return null
      const data = await res.json()
      if (data.status === 'success' && data.plugin) {
        return data.plugin as Plugin
      }
      return null
    } catch (err) {
      logger.error('Failed to fetch plugin detail:', err)
      return null
    }
  }

  const refreshInstalledApp = async (appId: string) => {
    const plugin = await fetchInstalledApp(appId)
    if (plugin) {
      upsertInstalledApp(plugin)
      if (ctx.state.activeApp.value?.id === appId) {
        ctx.state.activeApp.value = plugin
      }
      ctx.marketActions.patchMarketApp(appId, {
        installed: true,
        installed_version: plugin.version,
        state: plugin.state,
      })
    }
  }

  const loadApps = async (isBackground = false) => {
    if (!isBackground) {
      ctx.state.loading.value = true
    } else {
      ctx.state.refreshing.value = true
    }
    try {
      const res = await fetch(`${API_BASE()}/api/plugins`)
      const data = await res.json()
      if (data.status === 'success') {
        ctx.state.installedApps.value = data.plugins
        if (ctx.state.activeApp.value) {
          const updated = ctx.state.installedApps.value.find((a: Plugin) => a.id === ctx.state.activeApp.value?.id)
          if (updated && JSON.stringify(ctx.state.activeApp.value) !== JSON.stringify(updated)) {
            ctx.state.activeApp.value = updated
          }
        }
      }
    } catch (err: unknown) {
      logger.error('Failed to load apps:', err)
      ctx.state.error.value = err instanceof Error ? err.message : 'Failed to load apps'
    } finally {
      if (!isBackground) {
        ctx.state.loading.value = false
      } else {
        ctx.state.refreshing.value = false
      }
    }
  }

  const startApp = async (appId: string) => {
    logger.info('Starting app:', appId)
    const app = ctx.state.installedApps.value.find((a) => a.id === appId)
    if (app) app.state = 'starting'
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}/start`, { method: 'POST' })
      const data = await res.json()
      if (data.status === 'success') {
        await refreshInstalledApp(appId)
        const startedApp = ctx.state.installedApps.value.find((a) => a.id === appId)
        if (startedApp && startedApp.state === 'running') {
          openApp(startedApp)
        }
      } else {
        logger.error('Failed to start app:', data)
        await refreshInstalledApp(appId)
      }
    } catch (err) {
      logger.error('Request failed for starting app:', err)
      await refreshInstalledApp(appId)
    }
  }

  const stopApp = async (appId: string) => {
    logger.info('Stopping app:', appId)
    const app = ctx.state.installedApps.value.find((a) => a.id === appId)
    if (app) app.state = 'stopping'
    if (ctx.state.activeApp.value?.id === appId) {
      ctx.state.activeApp.value = null
    }
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}/stop`, { method: 'POST' })
      const data = await res.json()
      if (data.status !== 'success') {
        logger.error('Failed to stop app:', data)
      }
      await refreshInstalledApp(appId)
    } catch (err) {
      logger.error('Request failed for stopping app:', err)
      await refreshInstalledApp(appId)
    }
  }

  const openApp = (app: Plugin, mode: PluginRunMode = 'normal') => {
    ctx.state.activeApp.value = app
    ctx.state.activeMode.value = mode
  }

  const closeApp = () => {
    ctx.state.activeApp.value = null
    ctx.state.activeMode.value = 'normal'
  }

  const checkEnvironmentRequirements = (app: Plugin) => {
    const environmentStore = useEnvironmentStore()
    const requirements = ctx.parseEnvironmentRequirements(app)
    return environmentStore.checkPluginRequirements(requirements)
  }

  const startAppWithCheck = async (appId: string): Promise<boolean> => {
    const app = ctx.state.installedApps.value.find((a) => a.id === appId)
    if (!app) {
      logger.error('App not found:', appId)
      return false
    }
    const checkResult = checkEnvironmentRequirements(app)
    if (!checkResult.satisfied) {
      const environmentStore = useEnvironmentStore()
      let targetCategory: 'llm' | 'tts' | 'asr' | 'ffmpeg' | 'cloud' = 'llm'
      if (checkResult.missing.includes('llm')) targetCategory = 'llm'
      else if (checkResult.missing.includes('cloud')) targetCategory = 'cloud'
      else if (checkResult.missing.includes('tts')) targetCategory = 'tts'
      else if (checkResult.missing.includes('asr')) targetCategory = 'asr'
      else if (checkResult.missing.includes('ffmpeg')) targetCategory = 'ffmpeg'
      environmentStore.openEnvironmentManager(targetCategory)
      return false
    }
    await startApp(appId)
    return true
  }

  const startAppWithMode = async (appId: string, mode: PluginRunMode): Promise<boolean> => {
    if (mode === 'preview') {
      return await ctx.previewActions.startPreview(appId)
    }
    return await startAppWithCheck(appId)
  }

  const updateAppDisplayName = async (appId: string, name: string): Promise<Plugin | null> => {
    const normalizedName = name.trim()
    if (!normalizedName) {
      throw new Error('Plugin name cannot be empty')
    }
    const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(appId)}/display-name`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: normalizedName }),
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      throw new Error(detail || `update plugin display name failed: ${res.status}`)
    }
    await refreshInstalledApp(appId)
    return ctx.state.installedApps.value.find((item) => item.id === appId) || null
  }

  return {
    upsertInstalledApp,
    fetchInstalledApp,
    refreshInstalledApp,
    loadApps,
    startApp,
    stopApp,
    openApp,
    closeApp,
    checkEnvironmentRequirements,
    startAppWithCheck,
    startAppWithMode,
    updateAppDisplayName,
  }
}
