<template>
  <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
    <div class="modal-panel">
      <div class="modal-header">
        <h3>{{ t.apps.mobileOfflinePlaceholderTitle }}</h3>
        <button class="icon-btn" @click="$emit('close')">×</button>
      </div>
      <div class="modal-body">
        <div v-if="progressSummary" class="progress-card">
          <div class="progress-header">
            <span>{{ t.apps.publishProgressStage }}: {{ progressSummary.stageLabel }}</span>
            <span>{{ progressSummary.progress }}%</span>
          </div>
          <div class="progress-bar-track">
            <div class="progress-bar-fill" :style="{ width: `${progressSummary.progress}%` }"></div>
          </div>
          <div class="progress-message">{{ progressSummary.message }}</div>
        </div>

        <p class="desc">{{ t.apps.mobileOfflinePlaceholderDesc }}</p>
        <label class="label">{{ t.apps.publishVersion }}</label>
        <input v-model.trim="versionInput" class="input" :placeholder="defaultVersion || '0.1.0'" />

        <div v-if="result?.payload_text" class="payload-panel">
          <img :src="qrImageUrl" :alt="t.apps.mobilePreviewQrAlt" class="qr-image" />
          <p class="meta">
            {{ t.apps.mobilePublishExpireAt }}: {{ result.expires_at || t.common.noData }}
          </p>
          <textarea class="payload-text" readonly :value="result.payload_text"></textarea>
        </div>
        <div v-if="error" class="error">{{ error }}</div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary ui-btn ui-btn--neutral" :disabled="loading || !result?.payload_text" @click="$emit('refresh')">
          {{ t.apps.mobilePublishRefreshQr }}
        </button>
        <button class="btn-primary ui-btn ui-btn--emphasis" :disabled="loading" @click="submitPublish">
          {{ loading ? t.apps.mobilePublishing : t.apps.mobilePublishStart }}
        </button>
        <button class="btn-secondary ui-btn ui-btn--neutral" @click="$emit('close')">{{ t.common.close }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/composables/useI18n'
import type { MobilePublishResult, MobilePublishTask } from '@/services/plugins/mobilePublishApi'

const emit = defineEmits<{
  close: []
  submit: [payload: { version: string }]
  refresh: []
}>()
const { t } = useI18n()
const versionInput = ref('')

const props = defineProps<{
  visible: boolean
  loading?: boolean
  error?: string | null
  defaultVersion?: string
  task?: MobilePublishTask | null
  result?: MobilePublishResult | null
}>()

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      versionInput.value = String(props.defaultVersion || '').trim()
    }
  },
  { immediate: true }
)

const progressStageLabelMap = computed<Record<string, string>>(() => ({
  queued: t.value.apps.publishStageQueued,
  validating: t.value.apps.publishStageValidating,
  syncing_version: t.value.apps.publishStageSyncingVersion,
  building: t.value.apps.publishStageBuilding,
  zipping: t.value.apps.mobilePublishStageZipping,
  preparing_upload: t.value.apps.publishStagePreparingUpload,
  uploading: t.value.apps.publishStageUploading,
  finalizing: t.value.apps.publishStageFinalizing,
  completed: t.value.apps.publishStageCompleted,
  failed: t.value.apps.publishStageFailed,
}))

const progressSummary = computed(() => {
  const task = props.task
  if (!task || !['pending', 'running'].includes(task.status)) return null
  return {
    progress: Math.max(0, Math.min(100, Number(task.progress || 0))),
    message: String(task.message || ''),
    stageLabel: progressStageLabelMap.value[task.stage] || task.stage,
  }
})

const qrImageUrl = computed(() => {
  const payloadText = String(props.result?.payload_text || '')
  if (!payloadText) return ''
  const encoded = encodeURIComponent(payloadText)
  return `https://api.qrserver.com/v1/create-qr-code/?size=280x280&margin=12&data=${encoded}`
})

const submitPublish = () => {
  emit('submit', { version: String(versionInput.value || '').trim() })
}
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-panel {
  width: 520px;
  max-width: calc(100vw - 2rem);
  background: var(--color-surface-1);
  border: 1px solid var(--color-border);
  border-radius: 12px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--color-border);
}

.icon-btn {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 1.25rem;
  cursor: pointer;
}

.modal-body {
  padding: 1rem 1.25rem;
}

.desc {
  margin: 0 0 0.7rem;
  color: var(--color-text-secondary);
  line-height: 1.55;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.6rem;
  padding: 0.9rem 1.25rem 1.1rem;
  border-top: 1px solid var(--color-border);
}

.btn-secondary {
  border: 1px solid var(--color-button-neutral-border);
  border-radius: 8px;
  padding: 0.55rem 1rem;
}

.btn-primary {
  border: none;
  border-radius: 8px;
  padding: 0.55rem 1rem;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.label {
  display: block;
  margin-bottom: 0.25rem;
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}

.input {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 0.55rem 0.65rem;
  background: var(--color-surface-2);
  color: var(--color-text);
}

.payload-panel {
  margin-top: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  align-items: center;
}

.qr-image {
  width: 280px;
  height: 280px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: #fff;
}

.meta {
  width: 100%;
  margin: 0;
  font-size: 0.82rem;
  color: var(--color-text-secondary);
}

.payload-text {
  width: 100%;
  min-height: 140px;
  resize: vertical;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 0.6rem;
  font-size: 0.78rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: var(--color-surface-2);
  color: var(--color-text);
}

.error {
  margin-top: 0.6rem;
  color: #ef4444;
  font-size: 0.86rem;
}

.progress-card {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  padding: 0.8rem;
  border-radius: 8px;
  background: rgba(59, 130, 246, 0.08);
  margin-bottom: 0.8rem;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 0.85rem;
  color: var(--color-text);
}

.progress-bar-track {
  height: 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.22);
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: 999px;
}

.progress-message {
  color: var(--color-text-secondary);
  font-size: 0.82rem;
}
</style>
