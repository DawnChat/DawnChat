<template>
  <p class="unknown-part">{{ text || '' }}</p>
</template>

<script setup lang="ts">
defineProps<{ text?: string }>()
</script>

<style scoped>
.unknown-part {
  color: var(--color-text-secondary);
  font-size: 0.8rem;
}
</style>
