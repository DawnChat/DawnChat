<template>
  <section class="build-hub-hero">
    <div class="hero-head">
      <h2>{{ t.apps.buildHubTitle }}</h2>
      <p>{{ t.apps.buildHubSubtitle }}</p>
    </div>
    <div class="hero-input-wrap">
      <textarea
        class="hero-input"
        :value="modelValue"
        :placeholder="t.apps.buildHubPromptPlaceholder"
        @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
      />
      <div class="hero-actions">
        <button class="ui-btn ui-btn--neutral" type="button" @click="$emit('open-wizard')">
          {{ t.apps.createApp }}
        </button>
        <button class="ui-btn ui-btn--emphasis" type="button" :disabled="submitting" @click="$emit('submit')">
          {{ submitting ? t.apps.creating : t.apps.createFromPrompt }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from '@/composables/useI18n'

defineProps<{
  modelValue: string
  submitting?: boolean
}>()

defineEmits<{
  'update:modelValue': [value: string]
  submit: []
  'open-wizard': []
}>()

const { t } = useI18n()
</script>

<style scoped>
.build-hub-hero {
  border: 1px solid var(--color-border);
  background: var(--color-surface-1);
  border-radius: var(--buildhub-radius-lg);
  padding: var(--buildhub-space-lg) var(--buildhub-space-lg) var(--buildhub-space-md);
  display: flex;
  flex-direction: column;
  gap: var(--buildhub-space-sm);
}

.hero-head h2 {
  margin: 0;
  font-size: 1.5rem;
  line-height: 1.2;
}

.hero-head p {
  margin: 0.3rem 0 0;
  color: var(--color-text-secondary);
  font-size: 0.92rem;
  line-height: 1.4;
}

.hero-input-wrap {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.hero-input {
  width: 100%;
  min-height: 88px;
  border-radius: var(--buildhub-radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  color: var(--color-text-primary);
  padding: 0.72rem 0.82rem;
  resize: vertical;
  font-size: 0.92rem;
  line-height: 1.5;
}

.hero-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--buildhub-space-xs);
}

.hero-actions .ui-btn {
  min-height: var(--buildhub-btn-height);
  padding: 0 0.85rem;
  font-size: 0.86rem;
  line-height: 1;
  border-radius: var(--buildhub-radius-sm);
}
</style>
