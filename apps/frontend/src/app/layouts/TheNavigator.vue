<template>
  <aside class="the-navigator">
    <div class="navigator-header">
      <h2 class="navigator-title">{{ title }}</h2>
    </div>

    <div class="navigator-content">
      <slot />
    </div>
  </aside>
</template>

<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<style scoped>
.the-navigator {
  width: 16rem; /* 256px */
  height: 100vh;
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.navigator-header {
  padding: 1.5rem 1rem;
  border-bottom: 1px solid var(--color-border);
}

.navigator-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.navigator-content {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

/* 自定义滚动条 */
.navigator-content::-webkit-scrollbar {
  width: 6px;
}

.navigator-content::-webkit-scrollbar-track {
  background: transparent;
}

.navigator-content::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 3px;
}

.navigator-content::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-disabled);
}
</style>

