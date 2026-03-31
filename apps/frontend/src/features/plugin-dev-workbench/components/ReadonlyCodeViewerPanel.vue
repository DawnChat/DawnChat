<template>
  <section class="readonly-panel">
    <div class="readonly-toolbar">
      <div class="readonly-meta">
        <span class="readonly-label">{{ title }}</span>
        <span class="readonly-path">{{ filePath || emptyPathLabel }}</span>
      </div>
      <button class="ui-btn ui-btn--neutral back-btn" @click="emit('back')">{{ backLabel }}</button>
    </div>
    <div v-if="loading" class="readonly-loading">{{ loadingLabel }}</div>
    <div v-else-if="error" class="readonly-error">{{ error }}</div>
    <div v-else class="readonly-content">
      <div
        v-for="(line, index) in codeLines"
        :key="index"
        class="code-line"
        :class="{ active: focusLine > 0 && focusLine === index + 1 }"
      >
        <span class="line-no">{{ index + 1 }}</span>
        <span class="line-text">{{ line }}</span>
      </div>
      <div v-if="codeLines.length === 0" class="readonly-empty">{{ emptyContentLabel }}</div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  title: string
  filePath: string
  focusLine: number
  loading: boolean
  error: string
  content: string
  backLabel: string
  loadingLabel: string
  emptyPathLabel: string
  emptyContentLabel: string
}>()

const emit = defineEmits<{
  back: []
}>()

const codeLines = computed(() => {
  return String(props.content || '').split('\n')
})
</script>

<style scoped>
.readonly-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--wb-pane-main);
}

.readonly-toolbar {
  min-height: 44px;
  border-bottom: 1px solid var(--wb-border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0 0.85rem;
  background: var(--wb-pane-side);
  box-shadow: var(--wb-inset-shadow);
}

.readonly-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.readonly-label {
  font-size: 0.76rem;
  color: var(--color-text-secondary);
}

.readonly-path {
  font-size: 0.82rem;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.back-btn {
  min-height: 30px;
  border-radius: 8px;
  padding: 0.38rem 0.7rem;
}

.readonly-loading,
.readonly-error,
.readonly-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  font-size: 0.82rem;
}

.readonly-error {
  color: var(--color-error);
}

.readonly-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--wb-pane-main);
  padding: 0.7rem 0;
}

.code-line {
  min-height: 24px;
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  align-items: start;
  gap: 0.6rem;
  padding: 0 0.85rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.8rem;
  line-height: 1.45;
}

.code-line.active {
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
}

.line-no {
  color: var(--color-text-secondary);
  user-select: none;
}

.line-text {
  color: var(--color-text);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
