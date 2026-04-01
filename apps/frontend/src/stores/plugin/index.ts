import { defineStore } from 'pinia'
import { logger } from '@/utils/logger'
import { API_BASE } from '@/stores/plugin/api/client'
import { createPluginStoreContext } from '@/stores/plugin/context'
import { createBuildHubActions } from '@/stores/plugin/domains/buildHub'
import { parseEnvironmentRequirements } from '@/stores/plugin/domains/environment'
import { createInstallActions } from '@/stores/plugin/domains/install'
import { createLifecycleActions } from '@/stores/plugin/domains/lifecycle'
import { createMarketActions } from '@/stores/plugin/domains/market'
import { createPreviewActions } from '@/stores/plugin/domains/preview'
import { createPublishMobileActions } from '@/stores/plugin/domains/publishMobile'
import { createPublishWebActions } from '@/stores/plugin/domains/publishWeb'
import { createRuntimeActions } from '@/stores/plugin/domains/runtime'
import { createPluginStoreState } from '@/stores/plugin/state'
import type { CreatePluginPayload } from '@/stores/plugin/types'
import { router } from '@/app/router'
import { openPluginDevWorkbench, openPluginFullscreen } from '@/app/router/navigation'

export function createPluginStoreActions(state: ReturnType<typeof createPluginStoreState>) {
  const ctx = createPluginStoreContext(state, {
    router,
    openPluginDevWorkbench,
    openPluginFullscreen,
    parseEnvironmentRequirements,
  })

  const marketActions = createMarketActions(ctx)
  ctx.marketActions = marketActions
  const runtimeActions = createRuntimeActions(ctx)
  ctx.runtimeActions = runtimeActions
  const previewActions = createPreviewActions(ctx)
  ctx.previewActions = previewActions
  const installActions = createInstallActions(ctx)
  ctx.installActions = installActions
  const publishWebActions = createPublishWebActions(ctx)
  ctx.publishWebActions = publishWebActions
  const publishMobileActions = createPublishMobileActions(ctx)
  ctx.publishMobileActions = publishMobileActions
  const lifecycleActions = createLifecycleActions(ctx)
  ctx.lifecycleActions = lifecycleActions
  const buildHubActions = createBuildHubActions(state)

  const ensureTemplateCache = async (templateId = 'com.dawnchat.hello-world', forceRefresh = true) => {
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/template/ensure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_id: templateId,
          force_refresh: forceRefresh,
        }),
      })
      if (!res.ok) {
        return null
      }
      const data = await res.json()
      if (data.status === 'success' && data.data) {
        state.templateCacheInfo.value = data.data
        return state.templateCacheInfo.value
      }
      return null
    } catch (err) {
      logger.error('Failed to ensure template cache:', err)
      return null
    }
  }

  const createPluginFromTemplate = async (payload: CreatePluginPayload): Promise<string | null> => {
    state.creatingPlugin.value = true
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/create-from-template`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const detail = await res.text().catch(() => '')
        throw new Error(detail || `create plugin failed: ${res.status}`)
      }
      const data = await res.json()
      if (data.status !== 'success') {
        return null
      }
      const pluginId = String(data.data?.plugin_id || '')
      await Promise.all([runtimeActions.loadApps(), marketActions.loadMarketApps(true)])
      return pluginId || null
    } catch (err) {
      logger.error('Failed to create plugin from template:', err)
      throw err
    } finally {
      state.creatingPlugin.value = false
    }
  }

  const openCreateWizard = () => {
    state.createWizardVisible.value = true
  }

  const closeCreateWizard = () => {
    state.createWizardVisible.value = false
  }

  const startStatusPolling = () => {
    if (state.pollInterval.value) return
    state.pollInterval.value = setInterval(async () => {
      if (state.hasStartingApp.value) {
        const transitionalIds = state.installedApps.value
          .filter((app) => app.state === 'starting' || app.state === 'stopping')
          .map((app) => app.id)
        await Promise.all(transitionalIds.map((appId) => runtimeActions.refreshInstalledApp(appId)))
      }
      const previewIds = state.installedApps.value
        .filter((app) => {
          const previewState = app.preview?.state || ''
          const installStatus = app.preview?.install_status || ''
          return ['starting', 'reloading'].includes(previewState) || installStatus === 'running'
        })
        .map((app) => app.id)
      if (previewIds.length > 0) {
        await Promise.all(previewIds.map((appId) => previewActions.refreshPreviewStatus(appId)))
      }
    }, 2000)
  }

  const stopStatusPolling = () => {
    if (state.pollInterval.value) {
      clearInterval(state.pollInterval.value)
      state.pollInterval.value = null
    }
  }

  const stopTaskPolling = () => {
    state.installPollers.clearAll()
    state.publishPollers.clearAll()
    state.mobilePublishPollers.clearAll()
    state.lifecyclePollers.clearAll()
  }

  const stopAllPolling = () => {
    stopStatusPolling()
    stopTaskPolling()
  }

  const startPolling = () => {
    startStatusPolling()
  }

  const stopPolling = () => {
    stopStatusPolling()
  }

  return {
    setMarketQuery: marketActions.setMarketQuery,
    loadMarketApps: marketActions.loadMarketApps,
    loadApps: runtimeActions.loadApps,
    updateAppDisplayName: runtimeActions.updateAppDisplayName,
    startApp: runtimeActions.startApp,
    stopApp: runtimeActions.stopApp,
    openApp: runtimeActions.openApp,
    closeApp: runtimeActions.closeApp,
    checkEnvironmentRequirements: runtimeActions.checkEnvironmentRequirements,
    startAppWithCheck: runtimeActions.startAppWithCheck,
    startAppWithMode: runtimeActions.startAppWithMode,
    startPreview: previewActions.startPreview,
    startPreviewAndWaitReady: previewActions.startPreviewAndWaitReady,
    refreshPreviewStatus: previewActions.refreshPreviewStatus,
    retryPreviewInstall: previewActions.retryPreviewInstall,
    stopPreview: previewActions.stopPreview,
    isPreviewStarting: previewActions.isPreviewStarting,
    getInstallProgress: installActions.getInstallProgress,
    installApp: installActions.installApp,
    updateApp: installActions.updateApp,
    uninstallApp: installActions.uninstallApp,
    getPublishState: publishWebActions.getPublishState,
    loadPublishStatus: publishWebActions.loadPublishStatus,
    publishWebApp: publishWebActions.publishWebApp,
    getMobilePublishState: publishMobileActions.getMobilePublishState,
    loadMobilePublishStatus: publishMobileActions.loadMobilePublishStatus,
    publishMobileApp: publishMobileActions.publishMobileApp,
    refreshMobileSharePayload: publishMobileActions.refreshMobileSharePayload,
    runLifecycleOperation: lifecycleActions.runLifecycleOperation,
    cancelLifecycleTask: lifecycleActions.cancelLifecycleTask,
    retryLifecycleTaskAndHandle: lifecycleActions.retryLifecycleTaskAndHandle,
    finalizeActiveLifecycleTask: lifecycleActions.finalizeActiveLifecycleTask,
    closeLifecycleModal: lifecycleActions.closeLifecycleModal,
    openLifecycleModal: lifecycleActions.openLifecycleModal,
    clearLifecycleTask: lifecycleActions.clearLifecycleTask,
    resetLifecycleHandledState: lifecycleActions.resetLifecycleHandledState,
    setBuildHubFilter: buildHubActions.setBuildHubFilter,
    setBuildHubPromptDraft: buildHubActions.setBuildHubPromptDraft,
    hydrateBuildHubRecentSession: buildHubActions.hydrateBuildHubRecentSession,
    rememberBuildHubRecentSession: buildHubActions.rememberBuildHubRecentSession,
    ensureTemplateCache,
    createPluginFromTemplate,
    openCreateWizard,
    closeCreateWizard,
    startStatusPolling,
    stopStatusPolling,
    stopTaskPolling,
    stopAllPolling,
    startPolling,
    stopPolling,
    parseEnvironmentRequirements,
  }
}

export const usePluginStore = defineStore('plugin', () => {
  const state = createPluginStoreState()
  const actions = createPluginStoreActions(state)

  return {
    installedApps: state.installedApps,
    activeApp: state.activeApp,
    activeMode: state.activeMode,
    loading: state.loading,
    refreshing: state.refreshing,
    error: state.error,
    marketApps: state.marketApps,
    marketLoading: state.marketLoading,
    marketError: state.marketError,
    marketQuery: state.marketQuery,
    filteredMarketApps: state.filteredMarketApps,
    previewStartingMap: state.previewStartingMap,
    createWizardVisible: state.createWizardVisible,
    creatingPlugin: state.creatingPlugin,
    templateCacheInfo: state.templateCacheInfo,
    publishStateMap: state.publishStateMap,
    mobilePublishStateMap: state.mobilePublishStateMap,
    activeLifecycleTask: state.activeLifecycleTask,
    lifecycleModalVisible: state.lifecycleModalVisible,
    lifecycleCompletionMessage: state.lifecycleCompletionMessage,
    buildHubFilter: state.buildHubFilter,
    buildHubPromptDraft: state.buildHubPromptDraft,
    buildHubRecentPluginId: state.buildHubRecentPluginId,
    buildHubRecentVisitedAt: state.buildHubRecentVisitedAt,
    ...actions,
  }
})
