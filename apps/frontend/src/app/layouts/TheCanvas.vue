<template>
  <main class="the-canvas">
    <slot />
  </main>
</template>

<script setup lang="ts">
</script>

<style scoped>
.the-canvas {
  flex: 1;
  height: 100vh;
  background: var(--color-bg-primary);
  overflow-y: auto;
  padding: 0; /* 移除 padding，由内部视图组件自己控制 */
}

/* 自定义滚动条 */
.the-canvas::-webkit-scrollbar {
  width: 8px;
}

.the-canvas::-webkit-scrollbar-track {
  background: transparent;
}

.the-canvas::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 4px;
}

.the-canvas::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-disabled);
}
</style>

