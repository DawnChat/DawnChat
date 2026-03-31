<template>
  <section class="primary-actions">
    <button class="action-card" type="button" @click="$emit('quick-create')">
      <span class="title">{{ t.apps.createFromPrompt }}</span>
      <span class="desc">{{ t.apps.buildHubSubtitle }}</span>
    </button>
    <button class="action-card" type="button" :disabled="resuming" @click="$emit('continue-build')">
      <span class="title">{{ resuming ? t.apps.starting : t.apps.continueBuild }}</span>
      <span class="desc">{{ t.apps.recentEdited }}</span>
    </button>
    <button class="action-card" type="button" @click="$emit('import-or-copy')">
      <span class="title">{{ t.apps.importOrCopy }}</span>
      <span class="desc">{{ t.apps.recommendedMarket }}</span>
    </button>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from '@/composables/useI18n'

defineProps<{
  resuming?: boolean
}>()

defineEmits<{
  'quick-create': []
  'continue-build': []
  'import-or-copy': []
}>()

const { t } = useI18n()
</script>

<style scoped>
.primary-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--buildhub-space-sm);
}

.action-card {
  border: 1px solid var(--color-border);
  border-radius: var(--buildhub-radius-md);
  background: var(--color-surface-1);
  padding: 0.82rem 0.88rem;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-height: 86px;
}

.action-card:hover:not(:disabled) {
  border-color: var(--color-primary);
  background: var(--color-surface-2);
}

.action-card:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.title {
  color: var(--color-text-primary);
  font-size: 1.05rem;
  font-weight: 600;
  line-height: 1.2;
}

.desc {
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  line-height: 1.35;
}

@media (max-width: 1100px) {
  .primary-actions {
    grid-template-columns: 1fr;
  }
}
</style>
