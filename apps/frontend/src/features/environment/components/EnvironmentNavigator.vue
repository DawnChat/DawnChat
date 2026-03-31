<template>
  <nav class="environment-navigator">
    <div class="nav-items">
      <button
        v-for="item in navItems"
        :key="item.id"
        class="nav-item"
        :class="{ 
          active: currentCategory === item.id,
          'ui-selected': currentCategory === item.id,
          ready: item.status === 'ready',
          warning: item.status === 'warning',
          downloading: item.status === 'downloading'
        }"
        @click="handleSelect(item.id)"
      >
        <component :is="getIcon(item.icon)" class="nav-icon" :size="20" />
        <span class="nav-label">{{ item.label }}</span>
        <span class="nav-status">
          <CheckCircle2 v-if="item.status === 'ready'" class="status-icon ready" :size="14" />
          <AlertCircle v-else-if="item.status === 'warning'" class="status-icon warning" :size="14" />
          <span v-else-if="item.badge" class="status-badge">{{ item.badge }}</span>
          <span v-else-if="item.status === 'downloading'" class="status-icon downloading">
            <Loader2 class="animate-spin" :size="14" />
          </span>
        </span>
      </button>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useEnvironmentStore } from '@/features/environment/store'
import type { EnvironmentCategory } from '@/types/environment'
import { 
  Bot, 
  Volume2, 
  Mic, 
  Film, 
  Cloud,
  Image,
  AudioWaveform,
  CheckCircle2,
  AlertCircle,
  Loader2
} from 'lucide-vue-next'

const environmentStore = useEnvironmentStore()

const navItems = computed(() => environmentStore.navItems)
const currentCategory = computed(() => environmentStore.currentCategory)

const getIcon = (name: string) => {
  const icons: Record<string, any> = {
    Bot,
    Volume2,
    Mic,
    Film,
    Cloud,
    Image,
    AudioWaveform
  }
  return icons[name] || Bot
}

const handleSelect = (category: EnvironmentCategory) => {
  environmentStore.setCategory(category)
}
</script>

<style scoped>
.environment-navigator {
  width: 200px;
  min-width: 200px;
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  padding: 1rem 0.5rem;
}

.nav-items {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: transparent;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
  color: var(--color-text-secondary);
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

.nav-item.ui-selected .nav-status .status-icon {
  color: var(--color-interactive-selected-fg);
}

.nav-icon {
  font-size: 1.25rem;
  flex-shrink: 0;
}

.nav-label {
  flex: 1;
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-status {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.status-icon {
  font-size: 0.85rem;
  font-weight: 600;
}

.status-icon.ready {
  color: var(--color-success, #22c55e);
}

.status-icon.warning {
  color: var(--color-warning, #f59e0b);
}

.status-icon.downloading {
  display: flex;
  align-items: center;
  color: var(--color-primary);
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: var(--color-danger, #ef4444);
  color: white;
  border-radius: 9px;
  font-size: 0.7rem;
  font-weight: 600;
}

.nav-item.ui-selected .status-badge {
  background: color-mix(in srgb, var(--color-interactive-selected-fg) 24%, transparent);
}

</style>

