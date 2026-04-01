import { storeToRefs } from 'pinia'
import type { Ref } from 'vue'
import { usePluginStore } from '@/stores/plugin'
import type { Plugin, PluginRunMode } from '@/features/plugin/types'
import type {
  LifecycleTask,
  MobilePublishState,
  RunLifecycleOperationOptions,
  WebPublishState,
} from '@/features/plugin/store/types'

export interface DevWorkbenchFacade {
  activeApp: Ref<Plugin | null>
  activeMode: Ref<PluginRunMode>
  installedApps: Ref<Plugin[]>
  activeLifecycleTask: Ref<LifecycleTask | null>
  loadApps: (silent?: boolean) => Promise<void>
  updateAppDisplayName: (pluginId: string, name: string) => Promise<Plugin | null>
  openApp: (app: Plugin, mode: PluginRunMode) => void
  closeApp: () => void
  stopPreview: (pluginId: string) => Promise<boolean>
  refreshPreviewStatus: (pluginId: string) => Promise<void>
  retryPreviewInstall: (pluginId: string) => Promise<boolean>
  runLifecycleOperation: (options: RunLifecycleOperationOptions) => Promise<LifecycleTask>
  rememberBuildHubRecentSession: (pluginId: string) => void
  getPublishState: (pluginId: string) => WebPublishState
  getMobilePublishState: (pluginId: string) => MobilePublishState
  loadPublishStatus: (pluginId: string, accessToken?: string) => Promise<WebPublishState>
  loadMobilePublishStatus: (pluginId: string) => Promise<MobilePublishState>
  publishWebApp: ReturnType<typeof usePluginStore>['publishWebApp']
  publishMobileApp: ReturnType<typeof usePluginStore>['publishMobileApp']
  refreshMobileSharePayload: ReturnType<typeof usePluginStore>['refreshMobileSharePayload']
}

export const useDevWorkbenchFacade = (): DevWorkbenchFacade => {
  const pluginStore = usePluginStore()
  const { activeApp, activeMode, installedApps, activeLifecycleTask } = storeToRefs(pluginStore)

  return {
    activeApp,
    activeMode,
    installedApps,
    activeLifecycleTask,
    loadApps: pluginStore.loadApps,
    updateAppDisplayName: pluginStore.updateAppDisplayName,
    openApp: pluginStore.openApp,
    closeApp: pluginStore.closeApp,
    stopPreview: pluginStore.stopPreview,
    refreshPreviewStatus: pluginStore.refreshPreviewStatus,
    retryPreviewInstall: pluginStore.retryPreviewInstall,
    runLifecycleOperation: pluginStore.runLifecycleOperation,
    rememberBuildHubRecentSession: pluginStore.rememberBuildHubRecentSession,
    getPublishState: pluginStore.getPublishState,
    getMobilePublishState: pluginStore.getMobilePublishState,
    loadPublishStatus: pluginStore.loadPublishStatus,
    loadMobilePublishStatus: pluginStore.loadMobilePublishStatus,
    publishWebApp: pluginStore.publishWebApp,
    publishMobileApp: pluginStore.publishMobileApp,
    refreshMobileSharePayload: pluginStore.refreshMobileSharePayload,
  }
}
