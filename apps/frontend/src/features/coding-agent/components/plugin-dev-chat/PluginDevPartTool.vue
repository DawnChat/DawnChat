<template>
  <div class="tool-wrap" :data-kind="displayModel.kind">
    <button
      v-if="isCollapsible"
      class="tool-line tool-toggle"
      type="button"
      :aria-expanded="expanded ? 'true' : 'false'"
      @click="expanded = !expanded"
    >
      <Wrench class="tool-icon" :size="13" />
      <span class="tool-name">{{ displayModel.toolName }}</span>
      <span v-if="displayModel.argsPreview" class="tool-args" :title="displayModel.argsText">{{ displayModel.argsPreview }}</span>
      <span v-if="isWriteKind && displayModel.diffStat" class="tool-diff">{{ displayModel.diffStat }}</span>
      <ChevronRight class="tool-chevron" :size="12" :class="{ open: expanded }" />
      <span v-if="showStatus" class="tool-status" :data-status="status || 'pending'">
        {{ status || 'pending' }}
      </span>
    </button>
    <div v-else class="tool-line">
      <Wrench class="tool-icon" :size="13" />
      <span class="tool-name">{{ displayModel.toolName }}</span>
      <span v-if="displayModel.argsPreview" class="tool-args" :title="displayModel.argsText">{{ displayModel.argsPreview }}</span>
      <span v-if="isWriteKind && displayModel.diffStat" class="tool-diff">{{ displayModel.diffStat }}</span>
      <span v-if="showStatus" class="tool-status" :data-status="status || 'pending'">
        {{ status || 'pending' }}
      </span>
    </div>
    <div v-if="showDetails" class="tool-details">
      <template v-if="isWriteKind">
        <PluginDevCodeBlock
          :lines="displayModel.codeLines"
          :language="displayModel.languageHint"
          :preview-line-count="displayModel.previewLineCount || 4"
          :collapsible="true"
          :show-toggle="true"
        />
      </template>
      <template v-else-if="isReadKind">
        <PluginDevCodeBlock
          :lines="readPreviewLines"
          :language="displayModel.languageHint"
          :preview-line-count="displayModel.previewLineCount || 6"
          :collapsible="false"
          :show-toggle="false"
        />
        <p v-if="readTrimmedLineCount > 0" class="tool-summary">{{ readTrimmedLineCount }} lines omitted</p>
      </template>
      <template v-else>
        <pre v-if="displayModel.detailsText" class="tool-pre">{{ displayModel.detailsText }}</pre>
      </template>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronRight, Wrench } from 'lucide-vue-next'
import PluginDevCodeBlock from '@/features/coding-agent/components/plugin-dev-chat/PluginDevCodeBlock.vue'

const props = defineProps<{
  tool?: string
  status?: string
  text?: string
  display?: {
    kind: string
    renderMode?: 'inline' | 'collapsible'
    toolName?: string
    argsText?: string
    argsPreview?: string
    hasDetails?: boolean
    title: string
    summary: string
    detailBody?: string
    detailsText?: string
    command: string
    outputTail: string
    diffStat: string
    patchPreview: string
    languageHint?: string
    codeLines?: string[]
    previewLineCount?: number
    hiddenLineCount?: number
  }
}>()

const expanded = ref(false)
const isCollapsible = computed(() => {
  if (props.display?.renderMode !== 'collapsible') return false
  return Boolean(displayModel.value.hasDetails)
})
const displayModel = computed(() => {
  const name = String(props.display?.toolName || props.tool || 'tool')
  const args = String(props.display?.argsText || '').trim()
  const argsPreview = String(props.display?.argsPreview || args).trim()
  const summary = String(props.display?.summary || props.text || '').trim()
  const details = String(props.display?.detailBody || props.display?.detailsText || props.display?.patchPreview || '').trim()
  const shellOutput = String(props.display?.outputTail || '').trim()
  const hasDetails = Boolean(props.display?.hasDetails || details || shellOutput)
  return {
    kind: String(props.display?.kind || 'other'),
    toolName: name,
    argsText: args,
    argsPreview,
    hasDetails,
    summary,
    detailsText: details || shellOutput,
    diffStat: String(props.display?.diffStat || '').trim(),
    languageHint: String(props.display?.languageHint || 'plaintext'),
    codeLines: Array.isArray(props.display?.codeLines) ? props.display?.codeLines : [],
    previewLineCount: Number(props.display?.previewLineCount || 4),
    hiddenLineCount: Number(props.display?.hiddenLineCount || 0)
  }
})
const isReadKind = computed(() => displayModel.value.kind === 'read')
const isWriteKind = computed(() => displayModel.value.kind === 'write')
const readPreviewLines = computed(() => {
  if (!isReadKind.value) return []
  return displayModel.value.codeLines.slice(0, 22)
})
const readTrimmedLineCount = computed(() => {
  if (!isReadKind.value) return 0
  return Math.max(0, displayModel.value.codeLines.length - readPreviewLines.value.length)
})
const showStatus = computed(() => {
  const status = String(props.status || '').toLowerCase()
  return status === 'error' || status === 'failed'
})
const showDetails = computed(() => {
  if (isReadKind.value || isWriteKind.value) {
    if (isCollapsible.value) {
      return expanded.value && Boolean(displayModel.value.codeLines.length || displayModel.value.detailsText)
    }
    return Boolean(displayModel.value.codeLines.length || displayModel.value.detailsText)
  }
  if (isCollapsible.value) {
    return expanded.value && Boolean(displayModel.value.detailsText)
  }
  return displayModel.value.kind === 'bash' && Boolean(displayModel.value.detailsText)
})
</script>

<style scoped>
.tool-wrap {
  margin-top: 0.32rem;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.28rem;
}

.tool-line {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  max-width: min(100%, 760px);
  min-width: 0;
  gap: 0.34rem;
  padding: 0.12rem 0.16rem;
  border-radius: 6px;
  color: var(--color-text-secondary);
  line-height: 1.25;
}

.tool-toggle {
  cursor: pointer;
  border: none;
  background: transparent;
}

.tool-toggle:hover,
.tool-line:hover {
  background: color-mix(in srgb, var(--color-primary) 8%, transparent);
}

.tool-icon {
  flex: 0 0 auto;
  color: color-mix(in srgb, var(--color-primary) 65%, var(--color-text-secondary));
}

.tool-name {
  flex: 0 0 auto;
  color: var(--color-text);
  font-size: 0.78rem;
}

.tool-wrap[data-kind='write'] .tool-name {
  color: color-mix(in srgb, var(--color-primary) 68%, var(--color-text));
}

.tool-args {
  min-width: 0;
  font-size: 0.77rem;
  color: var(--color-text-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: min(52vw, 460px);
}

.tool-chevron {
  flex: 0 0 auto;
  color: var(--color-text-secondary);
  transition: transform 120ms ease;
}

.tool-chevron.open {
  transform: rotate(90deg);
}

.tool-status {
  flex: 0 0 auto;
  margin-left: 0.25rem;
  font-size: 0.74rem;
  color: var(--color-primary);
  text-transform: lowercase;
}

.tool-status[data-status='error'] {
  color: #d9534f;
}

.tool-status[data-status='failed'] {
  color: #d9534f;
}

.tool-diff {
  flex: 0 0 auto;
  border: 1px solid color-mix(in srgb, var(--color-primary) 34%, var(--color-border));
  border-radius: 10px;
  padding: 0 0.35rem;
  font-size: 0.7rem;
  color: var(--color-primary);
}

.tool-details {
  margin-left: 1.15rem;
  max-width: min(100%, 760px);
}

.tool-summary {
  margin: 0;
  font-size: 0.78rem;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.tool-pre {
  margin: 0.25rem 0 0 0;
  padding: 0.45rem 0.52rem;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  background: color-mix(in srgb, var(--color-surface-2) 92%, transparent);
  color: var(--color-text-secondary);
  font-size: 0.74rem;
  line-height: 1.42;
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

</style>
