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
            @click="selectedTemplateId = option.templateId"
          >
            <h4>{{ t.apps[option.nameKey] }}</h4>
            <p>{{ t.apps[option.descriptionKey] }}</p>
            <span>{{ option.stack }}</span>
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
}>()

const emit = defineEmits<{
  close: []
  confirm: [templateId: string]
}>()

const { t } = useI18n()

const options = DESKTOP_QUICK_TEMPLATE_OPTIONS

const selectedTemplateId = ref<string>(options[0].templateId)

const handleConfirm = () => {
  emit('confirm', selectedTemplateId.value)
}

watch(
  () => props.visible,
  (show) => {
    if (!show) return
    selectedTemplateId.value = options[0].templateId
  }
)
</script>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 1200; }
.modal-panel { width: 520px; max-width: calc(100vw - 2rem); background: var(--color-surface-1); border: 1px solid var(--color-border); border-radius: 12px; }
.header { display: flex; align-items: center; justify-content: space-between; padding: 1rem 1.25rem; border-bottom: 1px solid var(--color-border); }
.icon-btn { border: none; background: transparent; color: var(--color-text-secondary); font-size: 1.25rem; cursor: pointer; }
.body { padding: 1rem 1.25rem; display: flex; flex-direction: column; gap: .8rem; }
.description { margin: 0; color: var(--color-text-secondary); font-size: .86rem; }
.option-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .6rem; }
.option-card { border: 1px solid var(--color-border); border-radius: 10px; background: var(--color-surface-2); color: var(--color-text-primary); text-align: left; padding: .75rem .8rem; display: flex; flex-direction: column; gap: .38rem; cursor: pointer; transition: border-color .18s ease, transform .18s ease; }
.option-card:hover { border-color: color-mix(in srgb, var(--color-primary) 36%, var(--color-border)); transform: translateY(-1px); }
.option-card.active { border-color: var(--color-primary); background: color-mix(in srgb, var(--color-primary) 8%, var(--color-surface-2)); }
.option-card h4 { margin: 0; font-size: .9rem; }
.option-card p { margin: 0; color: var(--color-text-secondary); font-size: .76rem; line-height: 1.35; }
.option-card span { color: var(--color-text-secondary); font-size: .72rem; }
.footer { display: flex; justify-content: flex-end; gap: .5rem; padding: .9rem 1.25rem 1.1rem; border-top: 1px solid var(--color-border); }
.btn-primary,.btn-secondary { padding: .55rem 1rem; }

@media (max-width: 640px) {
  .option-grid { grid-template-columns: 1fr; }
}
</style>
