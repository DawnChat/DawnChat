<template>
  <div class="navigator-content">
    <nav class="section-nav nav-section">
      <div class="nav-group-title">{{ t.apps.buildHubTitle }}</div>
      <div
        v-for="item in sections"
        :key="item.id"
        :class="['nav-item', { active: activeSection === item.id, 'ui-selected': activeSection === item.id }]"
        @click="$emit('change-section', item.id)"
      >
        <component :is="item.icon" :size="20" class="icon" />
        <span class="label">{{ item.label }}</span>
      </div>
    </nav>
    <div class="nav-actions">
      <button class="btn-create ui-btn ui-btn--neutral" @click="$emit('resume-dev')">{{ t.apps.continueBuild }}</button>
      <button class="btn-create ui-btn ui-btn--neutral" @click="$emit('create-app')">{{ t.apps.createApp }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from '@/composables/useI18n'
import { CheckCircle2, Compass, Store } from 'lucide-vue-next'

interface Props {
  currentSection?: string
}

defineProps<Props>()
defineEmits<{
  'change-section': [section: string]
  'create-app': []
  'resume-dev': []
}>()

const { t } = useI18n()
const route = useRoute()

const sections = computed(() => [
  { id: 'hub', icon: Compass, label: t.value.apps.buildHubTitle },
  { id: 'market', icon: Store, label: t.value.apps.market },
  { id: 'installed', icon: CheckCircle2, label: t.value.apps.installed }
])

const activeSection = computed(() => {
  const queryFilter = String(route.query.filter || '').trim().toLowerCase()
  if (queryFilter === 'market' || queryFilter === 'installed') {
    return queryFilter
  }
  return 'hub'
})
</script>

<style scoped>
.navigator-content {
  padding: 1rem 0;
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.section-nav {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.nav-group-title {
  margin-bottom: 0.4rem;
  padding: 0 1rem;
  color: var(--color-text-secondary);
  font-size: 0.78rem;
}

.nav-section {
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  cursor: pointer;
  border-radius: 8px;
  color: var(--color-text-secondary);
  transition: all 0.2s;
}

.nav-item:not(.ui-selected):hover {
  background: var(--color-hover);
  color: var(--color-text-primary);
}

.nav-item.ui-selected {
  background: var(--color-interactive-selected-bg);
  color: var(--color-interactive-selected-fg);
}

.nav-item.ui-selected:hover {
  background: var(--color-interactive-selected-bg-hover);
}

.icon {
  font-size: 1.2rem;
}

.label {
  font-size: 0.95rem;
  font-weight: 500;
}

.nav-actions {
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
  margin-top: auto;
}

.btn-create {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
}
</style>

