<template>
  <div class="app-fullscreen">
    <div class="app-header">
      <button class="header-btn stop-btn" @click="$emit('stop', activeApp.id)" :title="t.apps.stop">
        <Square :size="20" />
      </button>
    </div>
    <iframe
      v-if="pluginUrl"
      :src="pluginUrl"
      class="app-iframe"
      frameborder="0"
      allow="clipboard-read; clipboard-write; microphone"
    ></iframe>
    <div v-else class="app-loading">
      <span class="spinner"></span>
      <span>{{ t.apps.starting }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Square } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'
import type { Plugin } from '@/features/plugin/types'

defineProps<{
  activeApp: Plugin
  pluginUrl: string
}>()

defineEmits<{
  stop: [appId: string]
}>()

const { t } = useI18n()
</script>

<style scoped>
.app-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 100;
  background: var(--color-bg);
  display: flex;
  flex-direction: column;
}

.app-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 1.5rem;
  background: transparent;
  pointer-events: none;
  z-index: 10;
}

.header-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  color: var(--color-text);
  cursor: pointer;
  pointer-events: auto;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  backdrop-filter: blur(8px);
}

.header-btn:hover {
  background: var(--color-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.stop-btn {
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.1);
}

.stop-btn:hover {
  background: #ef4444;
  color: white;
}

.app-iframe {
  flex: 1;
  width: 100%;
  height: 100%;
  border: none;
}

.app-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  color: var(--color-text-secondary);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
