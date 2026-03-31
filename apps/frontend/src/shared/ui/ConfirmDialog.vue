<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="visible" class="dialog-overlay" @click="handleOverlayClick">
        <div class="dialog-container" @click.stop>
          <div class="dialog-header">
            <component :is="icon" v-if="typeof icon !== 'string'" :size="32" class="dialog-icon-component" />
            <span v-else class="dialog-icon">{{ icon }}</span>
            <h3 class="dialog-title">{{ displayTitle }}</h3>
          </div>
          
          <div class="dialog-content">
            <p class="dialog-message">{{ displayMessage }}</p>
            <div v-if="detail" class="dialog-detail">
              {{ detail }}
            </div>
          </div>
          
          <div class="dialog-footer">
            <button
              v-if="showCancel"
              class="dialog-btn dialog-btn-cancel"
              @click="handleCancel"
              :disabled="loading"
            >
              {{ displayCancelText }}
            </button>
            <button
              class="dialog-btn dialog-btn-confirm"
              @click="handleConfirm"
              :disabled="loading"
              :class="{ loading: loading, danger: type === 'danger' }"
            >
              <span v-if="!loading">{{ displayConfirmText }}</span>
              <span v-else class="loading-spinner"></span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { HelpCircle } from 'lucide-vue-next'
import { computed } from 'vue'
import { useI18n } from '../../composables/useI18n'

const { t } = useI18n()

interface Props {
  visible?: boolean
  title?: string
  message?: string
  detail?: string
  icon?: any
  confirmText?: string
  cancelText?: string
  loading?: boolean
  closeOnOverlay?: boolean
  type?: 'default' | 'danger'
  showCancel?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  title: undefined,
  message: undefined,
  detail: '',
  icon: HelpCircle,
  confirmText: undefined,
  cancelText: undefined,
  loading: false,
  closeOnOverlay: true,
  type: 'default',
  showCancel: true
})

// Use computed or simple fallback logic in template/script
const displayTitle = computed(() => props.title || t.value.common.confirmTitle)
const displayMessage = computed(() => props.message || t.value.common.confirmMessage)
const displayConfirmText = computed(() => props.confirmText || t.value.common.confirm)
const displayCancelText = computed(() => props.cancelText || t.value.common.cancel)


const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

const handleConfirm = () => {
  if (!props.loading) {
    emit('confirm')
  }
}

const handleCancel = () => {
  if (!props.loading) {
    emit('cancel')
    emit('update:visible', false)
  }
}

const handleOverlayClick = () => {
  if (props.closeOnOverlay && !props.loading) {
    handleCancel()
  }
}
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 20px;
}

.dialog-container {
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  max-width: 480px;
  width: 100%;
  overflow: hidden;
  animation: slideIn 0.2s ease-out;
}

@keyframes slideIn {
  from {
    transform: translateY(-20px) scale(0.95);
    opacity: 0;
  }
  to {
    transform: translateY(0) scale(1);
    opacity: 1;
  }
}

.dialog-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 24px 24px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.dialog-icon-component {
  color: #667eea;
}

.dialog-btn-confirm.danger .dialog-icon-component {
  color: #ff6b6b;
}

.dialog-icon {
  font-size: 32px;
  line-height: 1;
}

.dialog-title {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin: 0;
  flex: 1;
}

.dialog-content {
  padding: 24px;
}

.dialog-message {
  font-size: 16px;
  line-height: 1.6;
  color: #555;
  margin: 0;
  white-space: pre-wrap;
}

.dialog-detail {
  margin-top: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-left: 3px solid #667eea;
  border-radius: 4px;
  font-size: 14px;
  color: #666;
  font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
}

.dialog-footer {
  display: flex;
  gap: 12px;
  padding: 16px 24px 24px;
  justify-content: flex-end;
}

.dialog-btn {
  padding: 12px 32px;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 100px;
}

.dialog-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.dialog-btn-cancel {
  background: #f5f5f5;
  color: #666;
}

.dialog-btn-cancel:hover:not(:disabled) {
  background: #e0e0e0;
}

.dialog-btn-confirm {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  position: relative;
}

.dialog-btn-confirm:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.dialog-btn-confirm.loading {
  pointer-events: none;
}

.loading-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 过渡动画 */
.dialog-enter-active,
.dialog-leave-active {
  transition: opacity 0.2s;
}

.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}

.dialog-enter-active .dialog-container,
.dialog-leave-active .dialog-container {
  transition: transform 0.2s, opacity 0.2s;
}

.dialog-enter-from .dialog-container,
.dialog-leave-to .dialog-container {
  transform: translateY(-20px) scale(0.95);
  opacity: 0;
}

/* 危险操作样式 */
.dialog-btn-confirm.danger {
  background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
}

.dialog-btn-confirm.danger:hover:not(:disabled) {
  box-shadow: 0 4px 12px rgba(255, 107, 107, 0.4);
}
</style>
