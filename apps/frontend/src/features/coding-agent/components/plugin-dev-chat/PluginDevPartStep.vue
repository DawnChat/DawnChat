<template>
  <p class="step-item">{{ text || '' }}</p>
</template>

<script setup lang="ts">
defineProps<{ text?: string }>()
</script>

<style scoped>
.step-item {
  margin: 0.25rem 0 0 0;
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}
</style>
