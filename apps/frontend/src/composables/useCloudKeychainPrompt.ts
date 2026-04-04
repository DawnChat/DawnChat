import { ref } from 'vue'

import { useI18n } from '@/composables/useI18n'

export function useCloudKeychainPrompt() {
  const { t } = useI18n()
  const hasShownMacOsKeychainHint = ref(false)
  const dialogVisible = ref(false)
  const dialogTitle = ref('')
  const dialogMessage = ref('')
  const dialogConfirmText = ref('')
  const dialogCancelText = ref('')
  let pendingResolver: ((accepted: boolean) => void) | null = null

  const shouldShowMacOsKeychainHint = (): boolean => {
    if (hasShownMacOsKeychainHint.value) {
      return false
    }
    return typeof navigator !== 'undefined' && /mac/i.test(navigator.platform || '')
  }

  const closeDialog = (accepted: boolean) => {
    dialogVisible.value = false
    const resolver = pendingResolver
    pendingResolver = null
    if (resolver) {
      resolver(accepted)
    }
  }

  const openMacOsKeychainHintDialog = (): Promise<boolean> => {
    dialogTitle.value = t.value.settings.cloudModels.keychainPermissionTitle
    dialogMessage.value = t.value.settings.cloudModels.keychainPermissionHint
    dialogConfirmText.value = t.value.settings.cloudModels.keychainPermissionConfirm
    dialogCancelText.value = t.value.common.cancel
    dialogVisible.value = true
    return new Promise<boolean>((resolve) => {
      pendingResolver = resolve
    })
  }

  const confirmMacOsKeychainHint = async (): Promise<boolean> => {
    const confirmed = await openMacOsKeychainHintDialog()
    if (confirmed) {
      hasShownMacOsKeychainHint.value = true
    }
    return confirmed
  }

  const handleDialogConfirm = () => {
    closeDialog(true)
  }

  const handleDialogCancel = () => {
    closeDialog(false)
  }

  return {
    dialogVisible,
    dialogTitle,
    dialogMessage,
    dialogConfirmText,
    dialogCancelText,
    shouldShowMacOsKeychainHint,
    confirmMacOsKeychainHint,
    handleDialogConfirm,
    handleDialogCancel,
  }
}
