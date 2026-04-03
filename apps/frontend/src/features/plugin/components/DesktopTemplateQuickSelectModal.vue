<template>
  <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
    <div class="modal-panel">
      <div class="header">
        <h3>{{ t.apps.desktopTemplateSelectTitle }}</h3>
        <button class="icon-btn" type="button" @click="$emit('close')">×</button>
      </div>
      <div class="body">
        <p class="description">{{ t.apps.desktopTemplateSelectDescription }}</p>
        <div class="option-grid">
          <button
            v-for="option in options"
            :key="option.templateId"
            class="option-card"
            :class="{ active: selectedTemplateId === option.templateId }"
            type="button"
            @click="handleSelectTemplate(option.templateId)"
          >
            <h4>{{ t.apps[option.nameKey] }}</h4>
            <p>{{ t.apps[option.descriptionKey] }}</p>
          </button>
        </div>
      </div>
      <div class="footer">
        <button class="btn-secondary ui-btn ui-btn--neutral" type="button" @click="$emit('close')">
          {{ t.common.cancel }}
        </button>
        <button class="btn-primary ui-btn ui-btn--emphasis" type="button" @click="handleConfirm">
          {{ t.common.confirm }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from '@/composables/useI18n'
import { DESKTOP_QUICK_TEMPLATE_OPTIONS } from '@/config/appTemplates'

const props = defineProps<{
  visible: boolean
  selectedTemplateId?: string | null
}>()

const emit = defineEmits<{
  close: []
  confirm: [templateId: string]
  selectionChange: [templateId: string]
}>()

const { t } = useI18n()

const options = DESKTOP_QUICK_TEMPLATE_OPTIONS

const DEFAULT_DESKTOP_TEMPLATE_ID = 'com.dawnchat.desktop-ai-assistant'

const resolveInitialTemplateId = () => {
  const remembered = String(props.selectedTemplateId || '').trim()
  if (remembered && options.some((option) => option.templateId === remembered)) return remembered
  const assistantOption = options.find((option) => option.templateId === DEFAULT_DESKTOP_TEMPLATE_ID)
  return assistantOption?.templateId || options[0].templateId
}

const selectedTemplateId = ref<string>(resolveInitialTemplateId())

const handleSelectTemplate = (templateId: string) => {
  selectedTemplateId.value = templateId
  emit('selectionChange', templateId)
}

const handleConfirm = () => {
  emit('confirm', selectedTemplateId.value)
}

watch(
  () => props.visible,
  (show) => {
    if (!show) return
    selectedTemplateId.value = resolveInitialTemplateId()
  }
)
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--color-app-canvas) 34%, rgba(5, 10, 20, 0.72));
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1200;
  padding: 0.9rem;
}

.modal-panel {
  width: min(500px, calc(100vw - 1.4rem));
  background: color-mix(in srgb, var(--color-surface-2) 92%, var(--color-app-canvas));
  border: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
  border-radius: 12px;
  box-shadow: 0 18px 46px rgba(15, 23, 42, 0.34);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.88rem 1rem;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
}

.icon-btn {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 1.1rem;
  line-height: 1;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  cursor: pointer;
}

.icon-btn:hover {
  color: var(--color-text-primary);
  background: color-mix(in srgb, var(--color-surface-2) 30%, transparent);
}

.body {
  padding: 0.92rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.72rem;
}

.description {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 0.82rem;
}

.option-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.52rem;
}

.option-card {
  border: 1px solid color-mix(in srgb, var(--color-border) 76%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-surface-2) 74%, transparent);
  color: var(--color-text-primary);
  text-align: left;
  padding: 0.68rem 0.74rem;
  display: flex;
  flex-direction: column;
  gap: 0.34rem;
  cursor: pointer;
  transition: border-color 0.18s ease, transform 0.18s ease, background 0.18s ease;
}

.option-card:hover {
  border-color: color-mix(in srgb, var(--color-primary) 36%, var(--color-border));
  transform: translateY(-1px);
  background: color-mix(in srgb, var(--color-surface-2) 90%, transparent);
}

.option-card.active {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 8%, var(--color-surface-2));
}

.option-card h4 {
  margin: 0;
  font-size: 0.86rem;
}

.option-card p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 0.74rem;
  line-height: 1.35;
}

.footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.48rem;
  padding: 0.78rem 1rem 0.9rem;
  border-top: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
}

.btn-primary,
.btn-secondary {
  padding: 0.52rem 0.92rem;
}

@media (max-width: 640px) {
  .option-grid { grid-template-columns: 1fr; }
}
</style>
