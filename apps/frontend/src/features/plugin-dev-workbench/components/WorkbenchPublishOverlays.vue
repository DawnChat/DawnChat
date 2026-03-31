<template>
  <WebPublishDialog
    :visible="publishDialogVisible"
    :plugin-name="pluginName"
    :plugin-version="pluginVersion"
    :plugin-description="pluginDescription"
    :loading="publishState.loading"
    :error="publishState.error"
    :status="publishState.last_status"
    :task="publishState.active_task"
    :result="publishState.last_result"
    @close="emit('closeWebPublish')"
    @submit="(payload) => emit('submitWebPublish', payload)"
  />
  <MobilePreviewQrDialog
    :visible="mobileQrDialogVisible"
    :share-url="mobileShareUrl"
    :lan-ip="mobileLanIp"
    :loading="mobileQrLoading"
    :error="mobileQrError"
    @close="emit('closeMobileQr')"
  />
  <MobileOfflinePublishPlaceholderDialog
    :visible="mobileOfflineDialogVisible"
    :loading="mobilePublishState.loading"
    :error="mobilePublishState.error"
    :default-version="mobileDefaultVersion"
    :task="mobilePublishState.active_task"
    :result="mobilePublishState.last_result"
    @submit="(payload) => emit('submitMobilePublish', payload)"
    @refresh="emit('refreshMobileShare')"
    @close="emit('closeMobileOffline')"
  />
  <div v-if="publishToast.visible" class="publish-toast" :class="publishToast.kind">
    {{ publishToast.message }}
  </div>
</template>

<script setup lang="ts">
import WebPublishDialog from '@/features/plugin/components/WebPublishDialog.vue'
import MobilePreviewQrDialog from '@/features/plugin/components/MobilePreviewQrDialog.vue'
import MobileOfflinePublishPlaceholderDialog from '@/features/plugin/components/MobileOfflinePublishPlaceholderDialog.vue'
import type { MobilePublishState, WebPublishState } from '@/features/plugin/store'

defineProps<{
  publishDialogVisible: boolean
  pluginName: string
  pluginVersion: string
  pluginDescription: string
  publishState: WebPublishState
  mobileQrDialogVisible: boolean
  mobileShareUrl: string
  mobileLanIp: string
  mobileQrLoading: boolean
  mobileQrError: string | null
  mobileOfflineDialogVisible: boolean
  mobilePublishState: MobilePublishState
  mobileDefaultVersion: string
  publishToast: { visible: boolean; message: string; kind: 'success' | 'error' }
}>()

const emit = defineEmits<{
  closeWebPublish: []
  closeMobileQr: []
  closeMobileOffline: []
  submitWebPublish: [payload: {
    slug: string
    title: string
    version: string
    description: string
    initial_visibility: 'private' | 'public' | 'unlisted'
  }]
  submitMobilePublish: [payload: { version: string }]
  refreshMobileShare: []
}>()
</script>

<style scoped>
.publish-toast {
  position: fixed;
  right: 1rem;
  bottom: 1rem;
  z-index: 1100;
  max-width: min(420px, calc(100vw - 2rem));
  padding: 0.8rem 1rem;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.24);
  color: #fff;
}

.publish-toast.success {
  background: rgba(5, 150, 105, 0.96);
}

.publish-toast.error {
  background: rgba(220, 38, 38, 0.96);
}
</style>
