import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { logger } from '@/utils/logger'
import type { Plugin } from '@/features/plugin/types'
import type { DevWorkbenchFacade } from '@/features/plugin-dev-workbench/services/devWorkbenchFacade'

interface WebPublishPayload {
  slug: string
  title: string
  version: string
  description: string
  initial_visibility: 'private' | 'public' | 'unlisted'
}

interface SessionLike {
  access_token?: string
  user?: { id?: string | null } | null
}

interface UseWebPublishFlowOptions {
  pluginId: ComputedRef<string>
  activeApp: Ref<Plugin | null>
  facade: DevWorkbenchFacade
  getSession: () => Promise<SessionLike | null>
  t: Ref<Record<string, any>>
  showToast: (message: string, kind: 'success' | 'error') => void
}

export const useWebPublishFlow = (options: UseWebPublishFlowOptions) => {
  const publishDialogVisible = ref(false)
  const publishState = computed(() => options.facade.getPublishState(options.pluginId.value))

  const closePublishDialog = () => {
    publishDialogVisible.value = false
  }

  const openPublishDialog = async () => {
    publishDialogVisible.value = true
    logger.info('web_publish_dialog_opened', {
      pluginId: options.pluginId.value,
      pluginName: options.activeApp.value?.name || options.pluginId.value,
    })
    const session = await options.getSession()
    await options.facade.loadPublishStatus(options.pluginId.value, session?.access_token)
  }

  const handlePublish = async (payload: WebPublishPayload) => {
    const context = {
      pluginId: options.pluginId.value,
      pluginName: options.activeApp.value?.name || options.pluginId.value,
      slug: payload.slug,
      version: payload.version,
    }
    try {
      logger.info('web_plugin_publish_submit_clicked', context)
      const session = await options.getSession()
      if (!session?.access_token) {
        throw new Error(options.t.value.apps.publishMissingSession)
      }
      logger.info('web_plugin_publish_session_ready', {
        ...context,
        userId: session.user?.id || null,
      })
      const result = await options.facade.publishWebApp(options.pluginId.value, {
        supabase_access_token: session.access_token,
        slug: payload.slug,
        title: payload.title,
        initial_visibility: payload.initial_visibility,
        version: payload.version,
        description: payload.description,
      })
      logger.info('web_plugin_publish_succeeded', {
        ...context,
        releaseId: result.release?.id || null,
        runtimeUrl: result.runtime_url || null,
        artifactCount: result.artifact_count || 0,
      })
      options.showToast(
        options.t.value.apps.publishSuccess.replace('{url}', String(result.runtime_url || payload.slug || '')),
        'success'
      )
    } catch (error) {
      const message =
        publishState.value?.error ||
        (error instanceof Error ? error.message : String(error || options.t.value.common.unknown))
      logger.error('web_plugin_publish_failed', {
        ...context,
        errorMessage: message,
        error,
        publishStateError: publishState.value?.error || null,
      })
      options.showToast(options.t.value.apps.publishFailed.replace('{error}', message), 'error')
    }
  }

  return {
    publishDialogVisible,
    publishState,
    openPublishDialog,
    closePublishDialog,
    handlePublish,
  }
}
