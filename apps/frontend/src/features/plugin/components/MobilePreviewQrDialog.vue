<template>
  <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
    <div class="modal-panel">
      <div class="modal-header">
        <h3>{{ t.apps.mobilePreviewQrTitle }}</h3>
        <button class="icon-btn" @click="$emit('close')">×</button>
      </div>
      <div class="modal-body">
        <p class="desc">{{ t.apps.mobilePreviewQrDesc }}</p>
        <p v-if="lanIp" class="meta">{{ t.apps.mobilePreviewLanIp }}: {{ lanIp }}</p>
        <div v-if="loading" class="state-text">{{ t.common.loading }}</div>
        <div v-else-if="error" class="state-text error">{{ error }}</div>
        <div v-else-if="shareUrl" class="qr-wrap">
          <img :src="qrImageUrl" :alt="t.apps.mobilePreviewQrAlt" class="qr-image" />
          <code class="share-url">{{ shareUrl }}</code>
          <div class="actions">
            <button class="btn-secondary ui-btn ui-btn--neutral" @click="copyLink">{{ t.apps.mobilePreviewCopyLink }}</button>
          </div>
          <p v-if="copied" class="copied">{{ t.common.copied }}</p>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary ui-btn ui-btn--neutral" @click="$emit('close')">{{ t.common.close }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from '@/composables/useI18n'
import { logger } from '@/utils/logger'

const props = defineProps<{
  visible: boolean
  shareUrl: string
  lanIp?: string
  loading?: boolean
  error?: string | null
}>()

defineEmits<{ close: [] }>()
const { t } = useI18n()
const copied = ref(false)

const qrImageUrl = computed(() => {
  const encoded = encodeURIComponent(props.shareUrl || '')
  return `https://api.qrserver.com/v1/create-qr-code/?size=280x280&margin=12&data=${encoded}`
})

const copyLink = async () => {
  const text = String(props.shareUrl || '').trim()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 1400)
  } catch (err) {
    logger.warn('copy_mobile_share_url_failed', { err: String(err) })
  }
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
  width: 560px;
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
  margin: 0 0 0.5rem;
  color: var(--color-text-secondary);
}

.meta {
  margin: 0 0 0.75rem;
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}

.state-text {
  color: var(--color-text-secondary);
}

.state-text.error {
  color: #ef4444;
}

.qr-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.qr-image {
  width: 280px;
  height: 280px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: #fff;
}

.share-url {
  width: 100%;
  text-align: left;
  word-break: break-all;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  border-radius: 8px;
  padding: 0.55rem 0.65rem;
}

.actions {
  display: flex;
  justify-content: center;
}

.copied {
  margin: 0;
  color: var(--color-primary);
  font-size: 0.85rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  padding: 0.9rem 1.25rem 1.1rem;
  border-top: 1px solid var(--color-border);
}

.btn-secondary {
  border: 1px solid var(--color-button-neutral-border);
  border-radius: 8px;
  padding: 0.55rem 1rem;
}
</style>
