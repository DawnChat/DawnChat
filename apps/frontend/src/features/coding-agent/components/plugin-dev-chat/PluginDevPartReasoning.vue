<template>
  <div class="reasoning-item" :class="{ open: expanded }">
    <button class="reasoning-toggle" type="button" @click="emit('toggle')">
      <Brain class="reasoning-icon" :size="13" />
      <span class="reasoning-label">reasoning</span>
      <ChevronRight class="reasoning-chevron" :size="12" :class="{ open: expanded }" />
    </button>
    <PluginDevPartText v-if="expanded" class="reasoning-text" :text="text || ''" />
  </div>
</template>

<script setup lang="ts">
import { Brain, ChevronRight } from 'lucide-vue-next'
import PluginDevPartText from '@/features/coding-agent/components/plugin-dev-chat/PluginDevPartText.vue'

defineProps<{
  text?: string
  expanded: boolean
}>()

const emit = defineEmits<{
  toggle: []
}>()
</script>

<style scoped>
.reasoning-item {
  margin-top: 0.32rem;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.28rem;
}

.reasoning-toggle {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  max-width: min(100%, 760px);
  min-width: 0;
  gap: 0.34rem;
  padding: 0.12rem 0.16rem;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  line-height: 1.25;
  font-size: 0.78rem;
  cursor: pointer;
}

.reasoning-toggle:hover {
  background: color-mix(in srgb, var(--color-primary) 8%, transparent);
}

.reasoning-icon {
  flex: 0 0 auto;
  color: color-mix(in srgb, var(--color-primary) 65%, var(--color-text-secondary));
}

.reasoning-label {
  color: var(--color-text);
}

.reasoning-chevron {
  flex: 0 0 auto;
  color: var(--color-text-secondary);
  transition: transform 120ms ease;
}

.reasoning-chevron.open {
  transform: rotate(90deg);
}

.reasoning-text {
  margin-left: 1.15rem;
  max-width: min(100%, 760px);
}
</style>
