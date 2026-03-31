<template>
  <div class="code-wrap">
    <div class="code-grid">
      <template v-for="(line, idx) in visibleLines" :key="`${idx}-${line}`">
        <div class="line-no">{{ idx + 1 }}</div>
        <div class="line-text" v-html="highlightLine(line)"></div>
      </template>
      <template v-if="visibleLines.length === 0">
        <div class="line-no">1</div>
        <div class="line-text muted">{{ emptyText }}</div>
      </template>
    </div>
    <div v-if="showToggle && hiddenLineCount > 0" class="code-footer">
      <span class="hidden-lines">{{ hiddenLineCount }} hidden lines</span>
      <button class="toggle-btn" type="button" @click="expanded = !expanded">
        {{ expanded ? '收起' : '展开' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import go from 'highlight.js/lib/languages/go'
import ini from 'highlight.js/lib/languages/ini'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import python from 'highlight.js/lib/languages/python'
import rust from 'highlight.js/lib/languages/rust'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import 'highlight.js/styles/github-dark.css'

hljs.registerLanguage('bash', bash)
hljs.registerLanguage('css', css)
hljs.registerLanguage('go', go)
hljs.registerLanguage('ini', ini)
hljs.registerLanguage('java', java)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('python', python)
hljs.registerLanguage('rust', rust)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('xml', xml)
hljs.registerLanguage('yaml', yaml)

const props = withDefaults(
  defineProps<{
    lines?: string[]
    language?: string
    previewLineCount?: number
    collapsible?: boolean
    showToggle?: boolean
    initiallyExpanded?: boolean
    emptyText?: string
  }>(),
  {
    lines: () => [],
    language: 'plaintext',
    previewLineCount: 4,
    collapsible: true,
    showToggle: true,
    initiallyExpanded: false,
    emptyText: '(empty)'
  }
)

const expanded = ref(Boolean(props.initiallyExpanded))

watch(
  () => props.initiallyExpanded,
  (value) => {
    expanded.value = Boolean(value)
  }
)

const normalizedLines = computed(() => (Array.isArray(props.lines) ? props.lines : []))
const hiddenLineCount = computed(() => Math.max(0, normalizedLines.value.length - Math.max(1, props.previewLineCount)))
const visibleLines = computed(() => {
  if (!props.collapsible || expanded.value) return normalizedLines.value
  return normalizedLines.value.slice(0, Math.max(1, props.previewLineCount))
})

const escapeHtml = (text: string): string =>
  String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

const highlightLine = (line: string): string => {
  const source = String(line ?? '')
  if (!source) return '&nbsp;'
  const language = String(props.language || 'plaintext').trim().toLowerCase()
  if (!language || language === 'plaintext') {
    return escapeHtml(source)
  }
  try {
    if (hljs.getLanguage(language)) {
      return hljs.highlight(source, { language, ignoreIllegals: true }).value
    }
    return hljs.highlightAuto(source).value
  } catch {
    return escapeHtml(source)
  }
}
</script>

<style scoped>
.code-wrap {
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  border-radius: 8px;
  background: #0d1117;
  overflow: hidden;
}

.code-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 0.74rem;
  line-height: 1.45;
}

.line-no {
  color: #7d8590;
  user-select: none;
  text-align: right;
  padding: 0.14rem 0.45rem 0.14rem 0.4rem;
  border-right: 1px solid #30363d;
  background: #111826;
}

.line-text {
  padding: 0.14rem 0.55rem;
  white-space: pre-wrap;
  word-break: break-word;
  color: #e6edf3;
}

.line-text.muted {
  color: #7d8590;
}

.code-footer {
  border-top: 1px solid #30363d;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.35rem 0.55rem;
  background: #0b1320;
}

.hidden-lines {
  font-size: 0.72rem;
  color: #7d8590;
}

.toggle-btn {
  border: 1px solid #30363d;
  border-radius: 6px;
  background: #111826;
  color: #c9d1d9;
  font-size: 0.72rem;
  height: 24px;
  padding: 0 0.45rem;
  cursor: pointer;
}
</style>
