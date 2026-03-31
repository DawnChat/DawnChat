import { computed, ref } from 'vue'
import { isTauri } from '@/adapters/env'
import { logger } from '@/utils/logger'
import { checkForAppUpdate } from '@/features/update/services/updateService'

type DialogMode = 'recommended' | 'forced'

export function useAppUpdate() {
  const checked = ref(false)
  const visible = ref(false)
  const mode = ref<DialogMode | null>(null)
  const latestVersion = ref<string | null>(null)
  const downloadUrl = ref<string | null>(null)
  const detail = ref('')

  const shouldShowDialog = computed(() => visible.value && mode.value !== null)

  const checkOnColdStart = async () => {
    if (checked.value || !isTauri()) return
    checked.value = true
    try {
      const result = await checkForAppUpdate()
      if (result.mode === 'none') return
      mode.value = result.mode
      latestVersion.value = result.latestVersion
      downloadUrl.value = result.downloadUrl
      detail.value = result.releaseNotes
      visible.value = true
    } catch (error) {
      logger.warn('[update] cold start check failed', error)
    }
  }

  const openDownload = async () => {
    const url = String(downloadUrl.value || '').trim()
    if (!url) return
    try {
      if (isTauri()) {
        const { openUrl } = await import('@tauri-apps/plugin-opener')
        await openUrl(url)
        return
      }
      window.open(url, '_blank')
    } catch (error) {
      logger.error('[update] open download url failed', error)
    }
  }

  const dismiss = () => {
    if (mode.value === 'forced') {
      visible.value = true
      return
    }
    visible.value = false
  }

  const handleVisibleChange = (next: boolean) => {
    if (!next && mode.value === 'forced') {
      visible.value = true
      return
    }
    visible.value = next
  }

  return {
    shouldShowDialog,
    mode,
    latestVersion,
    detail,
    checkOnColdStart,
    openDownload,
    dismiss,
    handleVisibleChange
  }
}
