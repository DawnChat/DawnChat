<template>
  <div class="tool-wrap" :data-kind="displayModel.kind">
    <div class="tool-anchor">
      <div class="tool-line">
      <button
        v-if="isCollapsible"
        class="tool-main tool-toggle"
        type="button"
        :aria-expanded="expanded ? 'true' : 'false'"
        @click="expanded = !expanded"
      >
        <Wrench class="tool-icon" :size="13" />
        <span class="tool-name" :title="displayModel.title">{{ displayModel.title }}</span>
        <span v-if="displayModel.argsPreview" class="tool-args" :title="displayModel.argsText">{{ displayModel.argsPreview }}</span>
        <span v-if="isWriteKind && displayModel.diffStat" class="tool-diff">{{ displayModel.diffStat }}</span>
        <ChevronRight class="tool-chevron" :size="12" :class="{ open: expanded }" />
      </button>
      <div v-else class="tool-main">
        <Wrench class="tool-icon" :size="13" />
        <span class="tool-name" :title="displayModel.title">{{ displayModel.title }}</span>
        <span v-if="displayModel.argsPreview" class="tool-args" :title="displayModel.argsText">{{ displayModel.argsPreview }}</span>
        <span v-if="isWriteKind && displayModel.diffStat" class="tool-diff">{{ displayModel.diffStat }}</span>
      </div>
        <button
        v-if="displayModel.hasInput"
        ref="infoButtonRef"
        class="tool-info-btn"
        type="button"
        aria-label="查看 tool 参数"
        :aria-expanded="showInputPopover ? 'true' : 'false'"
        @click.stop="showInputPopover = !showInputPopover"
      >
        <Info :size="12" />
      </button>
      <span v-if="showStatus" class="tool-status" :data-status="status || 'pending'">
        {{ status || 'pending' }}
      </span>
      </div>
    </div>
    <div v-if="showDetails" class="tool-details">
      <template v-if="isReadKind || isWriteKind">
        <div class="tool-details-scroll">
          <PluginDevCodeBlock
            :lines="displayModel.codeLines"
            :language="displayModel.languageHint"
            :preview-line-count="displayModel.previewLineCount || 6"
            :collapsible="false"
            :show-toggle="false"
          />
        </div>
      </template>
      <template v-else>
        <pre v-if="displayModel.detailsText" class="tool-pre">{{ displayModel.detailsText }}</pre>
      </template>
    </div>
  </div>
  <FloatingPopover
    :visible="showInputPopover"
    :anchor-el="infoButtonRef"
    :width="520"
    placement="auto"
    panel-class="tool-input-popover"
    :surface-mix="90"
    @outside-click="showInputPopover = false"
  >
    <div class="tool-input-popover-meta">
      <div><strong>Tool</strong>: {{ displayModel.toolName }}</div>
    </div>
    <div class="tool-input-popover-title">Tool Input</div>
    <pre class="tool-input-pre">{{ displayModel.fullInputText }}</pre>
  </FloatingPopover>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronRight, Info, Wrench } from 'lucide-vue-next'
import PluginDevCodeBlock from '@/features/coding-agent/components/plugin-dev-chat/PluginDevCodeBlock.vue'
import FloatingPopover from '@/shared/ui/FloatingPopover.vue'

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
    fullInputText?: string
    fullOutputText?: string
    fullErrorText?: string
    hasInput?: boolean
    hasOutput?: boolean
    hasError?: boolean
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
const showInputPopover = ref(false)
const infoButtonRef = ref<HTMLButtonElement | null>(null)

const isCollapsible = computed(() => {
  if (props.display?.renderMode !== 'collapsible') return false
  return Boolean(displayModel.value.hasDetails)
})
const displayModel = computed(() => {
  const name = String(props.display?.toolName || props.tool || 'tool')
  const args = String(props.display?.argsText || '').trim()
  const argsPreview = String(props.display?.argsPreview || args).trim()
  const summary = String(props.display?.summary || props.text || '').trim()
  const title = String(props.display?.title || summary || name).trim() || name
  const hasError = Boolean(props.display?.hasError)
  const details = String(
    hasError
      ? props.display?.fullErrorText || props.display?.detailBody || props.display?.detailsText || ''
      : props.display?.detailBody || props.display?.detailsText || props.display?.fullOutputText || props.display?.patchPreview || ''
  ).trim()
  const shellOutput = String(props.display?.outputTail || '').trim()
  const hasDetails = Boolean(props.display?.hasDetails || details || shellOutput)
  return {
    kind: String(props.display?.kind || 'other'),
    title,
    toolName: name,
    argsText: args,
    argsPreview,
    fullInputText: String(props.display?.fullInputText || '').trim(),
    hasInput: Boolean(props.display?.hasInput),
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
const showStatus = computed(() => {
  const currentStatus = String(props.status || '').toLowerCase()
  return currentStatus === 'error' || currentStatus === 'failed'
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
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.28rem;
}

.tool-anchor {
  position: relative;
  width: fit-content;
  max-width: min(100%, 760px);
}

.tool-line {
  display: flex;
  align-items: center;
  width: fit-content;
  max-width: min(100%, 760px);
  min-width: 0;
  gap: 0.24rem;
  padding: 0.12rem 0.16rem;
  border-radius: 6px;
  color: var(--color-text-secondary);
  line-height: 1.25;
}

.tool-main {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  max-width: min(100%, 640px);
  gap: 0.34rem;
}

.tool-main.tool-toggle {
  cursor: pointer;
  border: none;
  background: transparent;
  padding: 0;
  color: inherit;
}

.tool-line:hover {
  background: color-mix(in srgb, var(--color-primary) 8%, transparent);
}

.tool-icon {
  flex: 0 0 auto;
  color: color-mix(in srgb, var(--color-primary) 65%, var(--color-text-secondary));
}

.tool-name {
  min-width: 0;
  max-width: min(52vw, 320px);
  color: var(--color-text);
  font-size: 0.78rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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

.tool-info-btn {
  flex: 0 0 auto;
  width: 20px;
  height: 20px;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  background: transparent;
  color: var(--color-text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.tool-info-btn:hover {
  background: color-mix(in srgb, var(--color-primary) 10%, transparent);
  color: var(--color-primary);
}

.tool-info-btn[aria-expanded='true'] {
  background: color-mix(in srgb, var(--color-primary) 16%, transparent);
  color: var(--color-primary);
  border-color: color-mix(in srgb, var(--color-primary) 42%, var(--color-border));
}

.tool-input-popover {
  max-width: min(520px, calc(100vw - 16px));
  max-height: 320px;
}

.tool-input-popover-title {
  margin: 0.35rem 0 0.35rem;
  font-size: 0.72rem;
  color: var(--color-text-secondary);
}

.tool-input-popover-meta {
  font-size: 0.73rem;
  line-height: 1.35;
  color: var(--color-text-secondary);
}

.tool-input-pre {
  margin: 0;
  font-size: 0.73rem;
  line-height: 1.42;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.tool-details {
  margin-left: 1.15rem;
  max-width: min(100%, 760px);
  width: min(100%, 760px);
}

.tool-details-scroll {
  max-height: 280px;
  overflow: auto;
  border-radius: 8px;
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
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

@media (max-width: 1200px) {
  .tool-input-popover {
    max-height: 280px;
  }
}
</style>
