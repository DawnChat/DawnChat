<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="visible" class="dialog-overlay">
        <div class="dialog-container" @click.stop>
          <div class="dialog-header">
            <h3 class="dialog-title">{{ title }}</h3>
          </div>
          <div class="dialog-content">
            <p class="dialog-message">{{ message }}</p>
            <p v-if="runningWarning" class="dialog-warning">{{ runningWarning }}</p>
          </div>
          <div class="dialog-footer">
            <button class="dialog-btn dialog-btn-cancel" :disabled="busy" @click="emit('cancel')">
              {{ cancelLabel }}
            </button>
            <button class="dialog-btn dialog-btn-danger" :disabled="busy" @click="emit('exitDirectly')">
              {{ exitDirectlyLabel }}
            </button>
            <button class="dialog-btn dialog-btn-confirm" :disabled="busy" @click="emit('saveAndExit')">
              {{ saveAndExitLabel }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
  busy: boolean
  title: string
  message: string
  runningWarning: string
  saveAndExitLabel: string
  exitDirectlyLabel: string
  cancelLabel: string
}>()

const emit = defineEmits<{
  saveAndExit: []
  exitDirectly: []
  cancel: []
}>()
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.58);
  backdrop-filter: blur(3px);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10000;
}

.dialog-container {
  width: min(520px, calc(100% - 2rem));
  border-radius: 14px;
  background: var(--color-surface-1);
  border: 1px solid var(--color-border);
  box-shadow: 0 22px 48px rgba(0, 0, 0, 0.24);
}

.dialog-header {
  padding: 1rem 1rem 0.5rem 1rem;
}

.dialog-title {
  margin: 0;
  font-size: 1rem;
  color: var(--color-text);
}

.dialog-content {
  padding: 0 1rem 1rem 1rem;
}

.dialog-message {
  margin: 0;
  line-height: 1.6;
  color: var(--color-text);
}

.dialog-warning {
  margin: 0.75rem 0 0 0;
  line-height: 1.5;
  color: var(--color-text-secondary);
}

.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.6rem;
  padding: 0 1rem 1rem 1rem;
}

.dialog-btn {
  min-height: 34px;
  border-radius: 10px;
  padding: 0.45rem 0.85rem;
  border: 1px solid var(--color-border);
  background: var(--color-surface-3);
  color: var(--color-text);
  cursor: pointer;
}

.dialog-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.dialog-btn-danger {
  color: var(--color-error);
}

.dialog-btn-confirm {
  border-color: color-mix(in srgb, var(--color-primary) 35%, var(--color-border));
  background: color-mix(in srgb, var(--color-primary) 14%, var(--color-surface-3));
  color: var(--color-primary);
}

.dialog-enter-active,
.dialog-leave-active {
  transition: opacity 0.16s ease;
}

.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}
</style>
