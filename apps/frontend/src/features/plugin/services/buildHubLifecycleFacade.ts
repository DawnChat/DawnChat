import { usePluginStore } from '@/features/plugin/store'
import { APPS_HUB_PATH } from '@/app/router/paths'
import type { CreatePluginPayload, LifecycleTask } from '@/features/plugin/store'

export interface BuildHubLifecycleFacade {
  createDevSession: (payload: CreatePluginPayload) => Promise<LifecycleTask>
  startDevSession: (pluginId: string) => Promise<LifecycleTask>
}

const BASE_LIFECYCLE_OPTIONS = {
  navigationIntent: 'workbench' as const,
  from: APPS_HUB_PATH,
  uiMode: 'modal' as const,
  completionMessage: '启动完成，打开中...',
}

export const useBuildHubLifecycleFacade = (): BuildHubLifecycleFacade => {
  const pluginStore = usePluginStore()

  const createDevSession = async (payload: CreatePluginPayload) => {
    return pluginStore.runLifecycleOperation({
      operationType: 'create_dev_session',
      payload: { ...payload },
      ...BASE_LIFECYCLE_OPTIONS,
    })
  }

  const startDevSession = async (pluginId: string) => {
    return pluginStore.runLifecycleOperation({
      operationType: 'start_dev_session',
      payload: { plugin_id: pluginId },
      ...BASE_LIFECYCLE_OPTIONS,
    })
  }

  return {
    createDevSession,
    startDevSession,
  }
}
