<template>
  <aside class="iwp-drawer" :class="{ collapsed: collapsed }">
    <div class="iwp-drawer-header">
      <span v-if="!collapsed">{{ title }}</span>
      <button class="toggle-btn ui-btn ui-btn--neutral" @click="emit('toggle')">{{ collapsed ? '›' : '‹' }}</button>
    </div>
    <div v-if="!collapsed && loading" class="iwp-drawer-loading">{{ loadingLabel }}</div>
    <div v-else-if="!collapsed" class="iwp-drawer-list">
      <button
        v-for="file in files"
        :key="file.path"
        class="file-item"
        :class="{ active: file.path === activeFilePath }"
        @click="emit('openFile', file.path)"
      >
        {{ file.path }}
      </button>
      <div v-if="files.length === 0" class="iwp-empty">{{ emptyLabel }}</div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import type { IwpMarkdownFileMeta } from '@/services/plugins/iwpWorkbenchApi'

defineProps<{
  collapsed: boolean
  loading: boolean
  files: IwpMarkdownFileMeta[]
  activeFilePath: string
  title: string
  loadingLabel: string
  emptyLabel: string
}>()

const emit = defineEmits<{
  toggle: []
  openFile: [path: string]
}>()
</script>

<style scoped>
.iwp-drawer {
  width: 280px;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--wb-border-subtle);
  background: var(--wb-pane-side);
  overflow: hidden;
  transition: width 0.18s ease;
}

.iwp-drawer.collapsed {
  width: 44px;
}

.iwp-drawer-header {
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0.55rem 0 0.75rem;
  border-bottom: 1px solid var(--wb-border-subtle);
  color: var(--color-text);
  font-size: 0.78rem;
  font-weight: 600;
  background: var(--wb-pane-chrome);
  box-shadow: var(--wb-inset-shadow);
}

.toggle-btn {
  min-height: 28px;
  width: 28px;
  border-radius: 7px;
  padding: 0;
}

.iwp-drawer-loading,
.iwp-empty {
  padding: 0.7rem 0.85rem;
  color: var(--color-text-secondary);
  font-size: 0.8rem;
}

.iwp-drawer-list {
  overflow: auto;
  padding: 0.4rem;
  background: var(--wb-pane-side);
}

.file-item {
  width: 100%;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  text-align: left;
  border-radius: 8px;
  padding: 0.45rem 0.52rem;
  font-size: 0.79rem;
  cursor: pointer;
}

.file-item:hover {
  background: var(--color-surface-2);
  color: var(--color-text);
}

.file-item.active {
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
  color: var(--color-primary);
}

</style>
