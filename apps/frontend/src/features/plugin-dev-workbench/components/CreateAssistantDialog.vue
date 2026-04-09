<template>
  <div v-if="visible" class="modal-mask" @click.self="emit('close')">
    <div class="modal-panel">
      <div class="header">
        <div class="header-copy">
          <h3>{{ title }}</h3>
          <p class="sub">{{ description }}</p>
        </div>
        <button class="icon-btn" type="button" :disabled="submitting" @click="emit('close')">×</button>
      </div>

      <div class="body">
        <label class="label" for="assistant-name-input">{{ nameLabel }}</label>
        <input
          id="assistant-name-input"
          ref="nameInputRef"
          v-model.trim="name"
          class="input"
          type="text"
          :placeholder="namePlaceholder"
          :disabled="submitting"
          @keydown.enter.prevent="handleConfirm"
        >

        <template v-if="platformOptions.length > 0">
          <label class="label" for="assistant-platform-select">{{ platformLabel }}</label>
          <select
            id="assistant-platform-select"
            v-model="platform"
            class="input select-input"
            :disabled="submitting"
          >
            <option
              v-for="option in platformOptions"
              :key="option.value"
              :value="option.value"
              :disabled="option.disabled"
            >
              {{ option.label }}
            </option>
          </select>
          <p v-if="selectedPlatformDescription" class="platform-description">{{ selectedPlatformDescription }}</p>
        </template>

        <label v-if="showOpenAfterCreate" class="checkbox-row">
          <input v-model="openAfterCreate" type="checkbox" :disabled="submitting">
          <span>{{ openAfterCreateLabel }}</span>
        </label>
      </div>

      <div class="footer">
        <button class="btn-secondary ui-btn ui-btn--neutral" type="button" :disabled="submitting" @click="emit('close')">
          {{ cancelLabel }}
        </button>
        <button class="btn-primary ui-btn ui-btn--emphasis" type="button" :disabled="confirmDisabled" @click="handleConfirm">
          {{ submitting ? submittingLabel : confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  visible: boolean
  submitting?: boolean
  defaultName?: string
  defaultPlatform?: string
  platformOptions?: Array<{
    value: string
    label: string
    description?: string
    disabled?: boolean
  }>
  platformLabel?: string
  defaultOpenAfterCreate?: boolean
  showOpenAfterCreate?: boolean
  title: string
  description: string
  nameLabel: string
  namePlaceholder: string
  openAfterCreateLabel: string
  cancelLabel: string
  confirmLabel: string
  submittingLabel: string
}>(), {
  submitting: false,
  defaultName: '',
  defaultPlatform: 'desktop',
  platformOptions: () => [],
  platformLabel: 'Platform',
  defaultOpenAfterCreate: true,
  showOpenAfterCreate: true,
})

const emit = defineEmits<{
  close: []
  confirm: [payload: { name: string; openAfterCreate: boolean; platform: string }]
}>()

const name = ref('')
const platform = ref('desktop')
const openAfterCreate = ref(true)
const nameInputRef = ref<HTMLInputElement | null>(null)

const confirmDisabled = computed(() => props.submitting || !String(name.value || '').trim())
const selectedPlatformDescription = computed(() => {
  const selected = props.platformOptions.find((option) => option.value === platform.value)
  return String(selected?.description || '').trim()
})

const handleConfirm = () => {
  const normalized = String(name.value || '').trim()
  if (!normalized || props.submitting) return
  emit('confirm', {
    name: normalized,
    openAfterCreate: openAfterCreate.value,
    platform: platform.value,
  })
}

watch(
  () => props.visible,
  async (nextVisible) => {
    if (!nextVisible) return
    name.value = String(props.defaultName || '').trim()
    platform.value = String(props.defaultPlatform || 'desktop').trim() || 'desktop'
    openAfterCreate.value = Boolean(props.defaultOpenAfterCreate)
    await nextTick()
    nameInputRef.value?.focus()
    nameInputRef.value?.select()
  },
  { immediate: true }
)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.46);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.8rem;
  z-index: 10020;
}

.modal-panel {
  width: min(460px, calc(100vw - 1.2rem));
  border: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
  border-radius: 12px;
  background: color-mix(in srgb, var(--color-surface-1) 94%, var(--color-app-canvas));
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.34);
  overflow: hidden;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.8rem;
  padding: 0.9rem 1rem 0.8rem;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 84%, transparent);
}

.header-copy h3 {
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.3;
  font-weight: 620;
  color: var(--color-text-primary);
}

.sub {
  margin: 0.2rem 0 0;
  font-size: 0.74rem;
  line-height: 1.4;
  color: var(--color-text-secondary);
}

.icon-btn {
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}

.icon-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.body {
  padding: 0.9rem 1rem 0.95rem;
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}

.label {
  font-size: 0.76rem;
  line-height: 1.2;
  color: var(--color-text-secondary);
}

.input {
  width: 100%;
  height: 2.3rem;
  border: 1px solid color-mix(in srgb, var(--color-border) 84%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-surface-2) 78%, transparent);
  color: var(--color-text);
  font-size: 0.82rem;
  line-height: 1.2;
  padding: 0 0.75rem;
}

.select-input {
  padding-right: 2.2rem;
}

.platform-description {
  margin: -0.2rem 0 0;
  font-size: 0.74rem;
  line-height: 1.45;
  color: var(--color-text-secondary);
}

.checkbox-row {
  display: inline-flex;
  align-items: center;
  gap: 0.55rem;
  font-size: 0.77rem;
  line-height: 1.3;
  color: var(--color-text-secondary);
}

.footer {
  padding: 0.72rem 0.9rem 0.82rem;
  border-top: 1px solid color-mix(in srgb, var(--color-border) 84%, transparent);
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.btn-primary,
.btn-secondary {
  min-width: 96px;
  min-height: 32px;
  border-radius: 8px;
  padding: 0.35rem 0.9rem;
  font-size: 0.78rem;
  line-height: 1.1;
  font-weight: 600;
}
</style>
