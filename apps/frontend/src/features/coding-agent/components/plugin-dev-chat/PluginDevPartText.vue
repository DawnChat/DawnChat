<template>
  <div class="part-text markdown-body" v-html="renderedHtml" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const props = defineProps<{ text?: string }>()

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true
})

const renderedHtml = computed(() => {
  const source = String(props.text || '')
  const html = markdown.render(source)
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true }
  })
})
</script>

<style scoped>
.part-text {
  margin: 0.25rem 0 0 0;
  font-size: 0.9rem;
  line-height: 1.5;
  word-break: break-word;
}

.part-text :deep(p) {
  margin: 0.2rem 0 0.35rem 0;
}

.part-text :deep(ul),
.part-text :deep(ol) {
  margin: 0.2rem 0 0.4rem 1rem;
  padding: 0;
}

.part-text :deep(pre) {
  margin: 0.35rem 0;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface-2);
  padding: 0.5rem 0.6rem;
  overflow: auto;
}

.part-text :deep(code) {
  font-size: 0.84em;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.part-text :deep(pre code) {
  white-space: pre;
}

.part-text :deep(a) {
  color: var(--color-primary);
  text-decoration: underline;
}
</style>
