<template>
  <div class="navigator-content">
    <nav class="section-nav">
      <div
        v-for="item in sections"
        :key="item.id"
        :class="['nav-item', { active: currentSection === item.id, 'ui-selected': currentSection === item.id }]"
        @click="$emit('change-section', item.id)"
      >
        <component :is="item.icon" :size="20" class="icon" />
        <span class="label">{{ item.label }}</span>
      </div>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/composables/useI18n'
import { CheckCircle2, Store } from 'lucide-vue-next'

interface Props {
  currentSection?: string
}

defineProps<Props>()
defineEmits<{
  'change-section': [section: string]
}>()

const { t } = useI18n()

const sections = computed(() => [
  { id: 'installed', icon: CheckCircle2, label: t.value.tools.installed },
  { id: 'market', icon: Store, label: t.value.tools.market }
])
</script>

<style scoped>
.navigator-content {
  padding: 1rem 0;
}

.section-nav {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
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
</style>

