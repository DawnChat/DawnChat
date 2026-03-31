import { computed, type ComputedRef } from 'vue'
import { logger } from '@/utils/logger'
import { useRuntimeFacade, type RuntimeFacade } from '@/features/plugin-runtime/services/runtimeFacade'

interface UseRuntimeSessionGuardOptions {
  pluginId: ComputedRef<string>
  runMode: ComputedRef<'preview' | 'normal'>
  redirectToAppsInstalled: () => void
}

export const useRuntimeSessionGuard = (
  options: UseRuntimeSessionGuardOptions,
  injectedFacade?: RuntimeFacade
) => {
  const facade = injectedFacade || useRuntimeFacade()
  const isPreviewMode = computed(() => options.runMode.value === 'preview')

  const ensurePluginRunning = async () => {
    const id = options.pluginId.value
    if (!id) {
      options.redirectToAppsInstalled()
      return
    }

    await facade.loadApps()
    const app = facade.installedApps.value.find((item) => item.id === id)

    if (!app) {
      logger.warn('插件未安装，无法进入全屏运行态', { pluginId: id })
      options.redirectToAppsInstalled()
      return
    }

    facade.openApp(app, options.runMode.value)

    if (isPreviewMode.value) {
      if (app.preview?.state !== 'running') {
        const started = await facade.startPreview(id)
        if (!started) {
          options.redirectToAppsInstalled()
        }
      }
      return
    }

    if (app.state !== 'running') {
      const started = await facade.startAppWithMode(id, 'normal')
      if (!started) {
        options.redirectToAppsInstalled()
      }
    }
  }

  const syncActiveApp = () => {
    const id = options.pluginId.value
    if (!id) return
    const matched = facade.installedApps.value.find((item) => item.id === id)
    if (matched) {
      facade.openApp(matched, options.runMode.value)
    }
  }

  const stopAndExit = async (appId: string) => {
    if (isPreviewMode.value) {
      await facade.stopPreview(appId)
    } else {
      await facade.stopApp(appId)
    }
    facade.closeApp()
    logger.info('plugin_fullscreen_stop', { pluginId: appId })
    options.redirectToAppsInstalled()
  }

  return {
    activeApp: facade.activeApp,
    activeMode: facade.activeMode,
    installedApps: facade.installedApps,
    ensurePluginRunning,
    syncActiveApp,
    stopAndExit,
    closeApp: facade.closeApp,
  }
}
