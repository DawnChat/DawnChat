import type { Router } from 'vue-router'
import type { Plugin, PluginRunMode } from '@/features/plugin/types'
import type { EnvironmentRequirements } from '@/types/environment'
import type { PluginStoreState } from '@/stores/plugin/state'
import type { MarketPlugin } from '@/stores/plugin/types'

type MaybePromise<T> = T | Promise<T>

export interface MarketActionsContract {
  patchMarketApp(appId: string, patch: Partial<MarketPlugin>): void
  loadMarketApps(forceRefresh?: boolean): Promise<void>
}

export interface RuntimeActionsContract {
  refreshInstalledApp(appId: string): Promise<void>
  loadApps(isBackground?: boolean): Promise<void>
  updateAppDisplayName(appId: string, name: string): Promise<Plugin | null>
}

export interface PreviewActionsContract {
  startPreview(appId: string): Promise<boolean>
}

type AnyAsync = (...args: any[]) => Promise<any>
type AnySync = (...args: any[]) => any

export interface InstallActionsContract {
  getInstallProgress: AnySync
  stopInstallPolling: AnySync
  pollInstallProgress: AnyAsync
  startInstallPolling: AnySync
  installApp: AnyAsync
  updateApp: AnyAsync
  uninstallApp: AnyAsync
}

export interface PublishWebActionsContract {
  getPublishState: AnySync
  loadPublishStatus: AnyAsync
  publishWebApp: AnyAsync
}

export interface PublishMobileActionsContract {
  getMobilePublishState: AnySync
  loadMobilePublishStatus: AnyAsync
  publishMobileApp: AnyAsync
  refreshMobileSharePayload: AnyAsync
}

export interface LifecycleActionsContract {
  submitLifecycleOperation: AnyAsync
  runLifecycleOperation: AnyAsync
  pollLifecycleTask: AnyAsync
  waitForLifecycleTask: AnyAsync
  cancelLifecycleTask: AnyAsync
  retryLifecycleTask: AnyAsync
  handleLifecycleCompletion: AnyAsync
  finalizeLifecycleSession: AnySync
  closeLifecycleModal: AnySync
  openLifecycleModal: AnySync
  clearLifecycleTask: AnySync
  resetLifecycleHandledState: AnySync
}

export interface PluginStoreContext {
  state: PluginStoreState
  router: Router
  openPluginDevWorkbench: (router: Router, pluginId: string, from?: string) => MaybePromise<void>
  openPluginFullscreen: (router: Router, pluginId: string, from?: string, mode?: PluginRunMode) => MaybePromise<void>
  parseEnvironmentRequirements: (app: Plugin) => EnvironmentRequirements
  marketActions: MarketActionsContract
  runtimeActions: RuntimeActionsContract
  previewActions: PreviewActionsContract
  installActions: InstallActionsContract
  publishWebActions: PublishWebActionsContract
  publishMobileActions: PublishMobileActionsContract
  lifecycleActions: LifecycleActionsContract
}

interface PluginStoreContextDeps {
  router: Router
  openPluginDevWorkbench: PluginStoreContext['openPluginDevWorkbench']
  openPluginFullscreen: PluginStoreContext['openPluginFullscreen']
  parseEnvironmentRequirements: PluginStoreContext['parseEnvironmentRequirements']
}

function createNotReadyError(name: string): never {
  throw new Error(`[plugin-store] ${name} is not initialized`)
}

export function createPluginStoreContext(state: PluginStoreState, deps: PluginStoreContextDeps): PluginStoreContext {
  return {
    state,
    ...deps,
    marketActions: {
      patchMarketApp: () => createNotReadyError('marketActions.patchMarketApp'),
      loadMarketApps: async () => createNotReadyError('marketActions.loadMarketApps'),
    },
    runtimeActions: {
      refreshInstalledApp: async () => createNotReadyError('runtimeActions.refreshInstalledApp'),
      loadApps: async () => createNotReadyError('runtimeActions.loadApps'),
      updateAppDisplayName: async () => createNotReadyError('runtimeActions.updateAppDisplayName'),
    },
    previewActions: {
      startPreview: async () => createNotReadyError('previewActions.startPreview'),
    },
    installActions: {
      getInstallProgress: () => createNotReadyError('installActions.getInstallProgress'),
      stopInstallPolling: () => createNotReadyError('installActions.stopInstallPolling'),
      pollInstallProgress: async () => createNotReadyError('installActions.pollInstallProgress'),
      startInstallPolling: () => createNotReadyError('installActions.startInstallPolling'),
      installApp: async () => createNotReadyError('installActions.installApp'),
      updateApp: async () => createNotReadyError('installActions.updateApp'),
      uninstallApp: async () => createNotReadyError('installActions.uninstallApp'),
    },
    publishWebActions: {
      getPublishState: () => createNotReadyError('publishWebActions.getPublishState'),
      loadPublishStatus: async () => createNotReadyError('publishWebActions.loadPublishStatus'),
      publishWebApp: async () => createNotReadyError('publishWebActions.publishWebApp'),
    },
    publishMobileActions: {
      getMobilePublishState: () => createNotReadyError('publishMobileActions.getMobilePublishState'),
      loadMobilePublishStatus: async () => createNotReadyError('publishMobileActions.loadMobilePublishStatus'),
      publishMobileApp: async () => createNotReadyError('publishMobileActions.publishMobileApp'),
      refreshMobileSharePayload: async () => createNotReadyError('publishMobileActions.refreshMobileSharePayload'),
    },
    lifecycleActions: {
      submitLifecycleOperation: async () => createNotReadyError('lifecycleActions.submitLifecycleOperation'),
      runLifecycleOperation: async () => createNotReadyError('lifecycleActions.runLifecycleOperation'),
      pollLifecycleTask: async () => createNotReadyError('lifecycleActions.pollLifecycleTask'),
      waitForLifecycleTask: async () => createNotReadyError('lifecycleActions.waitForLifecycleTask'),
      cancelLifecycleTask: async () => createNotReadyError('lifecycleActions.cancelLifecycleTask'),
      retryLifecycleTask: async () => createNotReadyError('lifecycleActions.retryLifecycleTask'),
      handleLifecycleCompletion: async () => createNotReadyError('lifecycleActions.handleLifecycleCompletion'),
      finalizeLifecycleSession: () => createNotReadyError('lifecycleActions.finalizeLifecycleSession'),
      closeLifecycleModal: () => createNotReadyError('lifecycleActions.closeLifecycleModal'),
      openLifecycleModal: () => createNotReadyError('lifecycleActions.openLifecycleModal'),
      clearLifecycleTask: () => createNotReadyError('lifecycleActions.clearLifecycleTask'),
      resetLifecycleHandledState: () => createNotReadyError('lifecycleActions.resetLifecycleHandledState'),
    },
  }
}
