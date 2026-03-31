import { computed, ref, type ComputedRef } from 'vue'
import { logger } from '@/utils/logger'
import {
  useDevWorkbenchFacade,
  type DevWorkbenchFacade,
} from '@/features/plugin-dev-workbench/services/devWorkbenchFacade'

interface UsePreviewSessionGuardOptions {
  pluginId: ComputedRef<string>
  redirectToAppsInstalled: () => void
}

export const usePreviewSessionGuard = (
  options: UsePreviewSessionGuardOptions,
  injectedFacade?: DevWorkbenchFacade
) => {
  const facade = injectedFacade || useDevWorkbenchFacade()
  const previewReady = ref(false)
  const previewLoadingText = ref('')
  const previewPaneKey = ref(0)
  let previewStatusPoller: ReturnType<typeof setInterval> | null = null

  const previewLifecycleTask = computed(() => {
    const task = facade.activeLifecycleTask.value
    if (!task) return null
    if (task.plugin_id !== options.pluginId.value) return null
    if (!['create_dev_session', 'start_dev_session', 'restart_dev_session'].includes(task.operation_type)) {
      return null
    }
    return task
  })

  const previewLifecycleBusy = computed(() => {
    const task = previewLifecycleTask.value
    return Boolean(task && ['pending', 'running'].includes(task.status))
  })

  const previewInstallStatus = computed<'idle' | 'running' | 'success' | 'failed'>(() => {
    const raw = String(facade.activeApp.value?.preview?.install_status || 'idle')
    if (raw === 'running' || raw === 'success' || raw === 'failed') {
      return raw
    }
    return 'idle'
  })

  const previewInstallErrorMessage = computed(() =>
    String(facade.activeApp.value?.preview?.install_error_message || '')
  )

  const previewChatBlocked = computed(() => {
    return String(facade.activeApp.value?.preview?.frontend_mode || 'dev') === 'dist'
      && previewInstallStatus.value === 'running'
  })

  const shouldPollPreviewStatus = computed(() => {
    const app = facade.activeApp.value
    if (!app || app.id !== options.pluginId.value) return false
    return String(app.preview?.frontend_mode || 'dev') === 'dist'
      || previewInstallStatus.value === 'running'
  })

  const stopPreviewStatusPolling = () => {
    if (previewStatusPoller) {
      clearInterval(previewStatusPoller)
      previewStatusPoller = null
    }
  }

  const pollPreviewStatusOnce = async () => {
    const id = options.pluginId.value
    if (!id) return
    await facade.refreshPreviewStatus(id)
  }

  const startPreviewStatusPolling = () => {
    if (previewStatusPoller) return
    void pollPreviewStatusOnce()
    previewStatusPoller = setInterval(() => {
      void pollPreviewStatusOnce()
    }, 1500)
  }

  const syncActiveApp = () => {
    const id = options.pluginId.value
    if (!id) return
    const matched = facade.installedApps.value.find((item) => item.id === id)
    if (!matched) return
    facade.openApp(matched, 'preview')
    if (matched.preview?.state === 'running' && matched.preview?.url) {
      previewReady.value = true
    }
  }

  const ensurePreviewRunning = async () => {
    const id = options.pluginId.value
    if (!id) {
      options.redirectToAppsInstalled()
      return
    }
    previewReady.value = false
    previewLoadingText.value = '正在准备开发预览...'
    await facade.loadApps()
    const app = facade.installedApps.value.find((item) => item.id === id)
    if (!app) {
      logger.warn('插件未安装，无法进入开发工作台', { pluginId: id })
      options.redirectToAppsInstalled()
      return
    }
    facade.openApp(app, 'preview')
    if (app.preview?.state !== 'running' || !app.preview?.url) {
      previewLoadingText.value = '正在启动预览服务...'
      try {
        await facade.runLifecycleOperation({
          operationType: 'start_dev_session',
          payload: { plugin_id: id },
          navigationIntent: 'none',
          uiMode: 'inline',
          completionMessage: '预览已就绪'
        })
      } catch (err) {
        logger.error('预览启动失败', { pluginId: id, err })
        options.redirectToAppsInstalled()
        return
      }
    }
    await facade.loadApps(true)
    const refreshed = facade.installedApps.value.find(item => item.id === id)
    if (refreshed) {
      facade.openApp(refreshed, 'preview')
    }
    previewPaneKey.value += 1
    previewReady.value = true
  }

  const restartPreview = async (appId: string) => {
    previewLoadingText.value = '正在重启预览服务...'
    previewReady.value = false
    try {
      await facade.runLifecycleOperation({
        operationType: 'restart_dev_session',
        payload: { plugin_id: appId },
        navigationIntent: 'none',
        uiMode: 'inline',
        completionMessage: '重启完成，正在刷新预览...'
      })
      await facade.loadApps(true)
      const refreshed = facade.installedApps.value.find(item => item.id === appId)
      if (refreshed) {
        facade.openApp(refreshed, 'preview')
      }
      previewPaneKey.value += 1
      previewReady.value = true
    } catch (err) {
      logger.error('预览重启失败', { pluginId: appId, err })
      await ensurePreviewRunning()
    }
  }

  const retryInstall = async () => {
    const id = options.pluginId.value
    if (!id) return
    const ok = await facade.retryPreviewInstall(id)
    if (!ok) return
    await facade.loadApps(true)
  }

  const stopAndExit = async (appId: string) => {
    await facade.stopPreview(appId)
    facade.closeApp()
    options.redirectToAppsInstalled()
  }

  return {
    activeApp: facade.activeApp,
    activeMode: facade.activeMode,
    installedApps: facade.installedApps,
    previewReady,
    previewLoadingText,
    previewPaneKey,
    previewLifecycleTask,
    previewLifecycleBusy,
    previewInstallStatus,
    previewInstallErrorMessage,
    previewChatBlocked,
    shouldPollPreviewStatus,
    ensurePreviewRunning,
    syncActiveApp,
    startPreviewStatusPolling,
    stopPreviewStatusPolling,
    restartPreview,
    retryInstall,
    stopAndExit,
  }
}
