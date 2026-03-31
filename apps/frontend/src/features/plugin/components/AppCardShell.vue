<template>
  <div class="app-card" :class="{ running }">
    <div class="app-icon-large">
      <component :is="icon" v-if="typeof icon !== 'string'" :size="48" />
      <span v-else-if="icon">{{ icon }}</span>
      <Package v-else :size="48" />
    </div>
    <div class="app-info">
      <div class="app-header-row">
        <h3>{{ name }}</h3>
        <span v-if="isOfficial" class="official-badge">{{ officialText }}</span>
        <span v-if="isUserCreated" class="user-badge">{{ createdText }}</span>
      </div>
      <p class="app-desc">{{ description }}</p>
      <slot name="meta" />
    </div>
    <div class="app-actions">
      <slot name="actions" />
    </div>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { Package } from 'lucide-vue-next'

defineProps<{
  icon?: string | object
  name: string
  description: string
  isOfficial?: boolean
  isUserCreated?: boolean
  running?: boolean
  officialText: string
  createdText: string
}>()
</script>

<style scoped>
.app-card { display: flex; flex-direction: column; padding: 1.5rem; background: var(--color-surface-2); border: 1px solid var(--color-border); border-radius: 12px; transition: all 0.2s; }
.app-card:hover { border-color: var(--color-primary); box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); }
.app-card.running { border-color: #10b981; background: linear-gradient(135deg, var(--color-surface-2) 0%, rgba(16, 185, 129, 0.08) 100%); }
.app-icon-large { font-size: 3rem; text-align: center; margin-bottom: 1rem; }
.app-info { flex: 1; margin-bottom: 1rem; }
.app-header-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; flex-wrap: wrap; }
.app-header-row h3 { margin: 0; font-size: 1.1rem; }
.official-badge { padding: 0.125rem 0.375rem; background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }
.user-badge { padding: 0.125rem 0.375rem; background: rgba(16, 185, 129, 0.15); color: #10b981; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }
.app-desc { color: var(--color-text-secondary); font-size: 0.9rem; line-height: 1.5; margin: 0 0 1rem 0; }
.app-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
}

.app-actions :deep(button) {
  width: 100%;
  min-height: 40px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-actions :deep(.more-menu-wrap) {
  width: 100%;
}
</style>
