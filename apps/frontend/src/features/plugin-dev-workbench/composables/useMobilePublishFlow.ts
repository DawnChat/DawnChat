import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { buildBackendUrl } from '@/utils/backendUrl'
import { logger } from '@/utils/logger'
import type { Plugin } from '@/features/plugin/types'
import type { DevWorkbenchFacade } from '@/features/plugin-dev-workbench/services/devWorkbenchFacade'

interface SessionLike {
  access_token?: string
}

interface UseMobilePublishFlowOptions {
  pluginId: ComputedRef<string>
  activeApp: Ref<Plugin | null>
  facade: DevWorkbenchFacade
  getSession: () => Promise<SessionLike | null>
  t: Ref<Record<string, any>>
  showToast: (message: string, kind: 'success' | 'error') => void
}

export const useMobilePublishFlow = (options: UseMobilePublishFlowOptions) => {
  const mobileQrDialogVisible = ref(false)
  const mobileOfflineDialogVisible = ref(false)
  const mobileShareUrl = ref('')
  const mobileLanIp = ref('')
  const mobileQrLoading = ref(false)
  const mobileQrError = ref<string | null>(null)
  const mobilePublishState = computed(() => options.facade.getMobilePublishState(options.pluginId.value))

  const openMobilePreviewQr = async () => {
    mobileQrDialogVisible.value = true
    mobileQrLoading.value = true
    mobileQrError.value = null
    mobileShareUrl.value = ''
    mobileLanIp.value = ''
    try {
      const response = await fetch(
        buildBackendUrl(`/api/plugins/${encodeURIComponent(options.pluginId.value)}/preview/mobile-share-url`)
      )
      if (!response.ok) {
        const detail = await response.text().catch(() => '')
        throw new Error(detail || `Failed to load mobile share url: ${response.status}`)
      }
      const payload = await response.json()
      mobileShareUrl.value = String(payload?.share_url || '')
      mobileLanIp.value = String(payload?.lan_ip || '')
      if (!mobileShareUrl.value) {
        throw new Error('Mobile share URL is empty')
      }
    } catch (error) {
      mobileQrError.value = error instanceof Error ? error.message : String(error || options.t.value.common.unknown)
      logger.error('mobile_preview_share_url_failed', {
        pluginId: options.pluginId.value,
        error,
        message: mobileQrError.value
      })
    } finally {
      mobileQrLoading.value = false
    }
  }

  const openMobileOfflinePlaceholder = () => {
    mobileOfflineDialogVisible.value = true
    void options.facade.loadMobilePublishStatus(options.pluginId.value)
  }

  const closeMobileQr = () => {
    mobileQrDialogVisible.value = false
  }

  const closeMobileOffline = () => {
    mobileOfflineDialogVisible.value = false
  }

  const handleMobilePublish = async (payload: { version: string }) => {
    const session = await options.getSession()
    if (!session?.access_token) {
      mobileQrError.value = options.t.value.apps.publishMissingSession
      return
    }
    try {
      await options.facade.publishMobileApp(options.pluginId.value, {
        supabase_access_token: session.access_token,
        version: payload.version || undefined,
      })
      options.showToast(options.t.value.apps.publishSuccess.replace('{url}', options.pluginId.value), 'success')
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error || options.t.value.common.unknown)
      options.showToast(options.t.value.apps.publishFailed.replace('{error}', message), 'error')
    }
  }

  const handleMobileRefreshShare = async () => {
    const session = await options.getSession()
    if (!session?.access_token) {
      return
    }
    try {
      await options.facade.refreshMobileSharePayload(options.pluginId.value, session.access_token)
    } catch (error) {
      logger.error('mobile_publish_refresh_failed', {
        pluginId: options.pluginId.value,
        error,
      })
    }
  }

  return {
    mobileQrDialogVisible,
    mobileOfflineDialogVisible,
    mobileShareUrl,
    mobileLanIp,
    mobileQrLoading,
    mobileQrError,
    mobilePublishState,
    openMobilePreviewQr,
    openMobileOfflinePlaceholder,
    closeMobileQr,
    closeMobileOffline,
    handleMobilePublish,
    handleMobileRefreshShare,
  }
}
