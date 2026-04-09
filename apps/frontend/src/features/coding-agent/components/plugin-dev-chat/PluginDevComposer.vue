<template>
  <div class="composer">
    <PluginDevComposerImageTags
      :images="pendingImages"
      @preview="(payload) => emit('preview-image', payload)"
      @remove="(index) => emit('remove-image', index)"
    />
    <PluginDevComposerFileTags
      :files="pendingFiles"
      :tags-aria-label="fileTagsAriaLabel"
      :remove-label-prefix="fileTagRemovePrefix"
      @remove="(index) => emit('remove-file', index)"
    />
    <div class="input-wrapper">
      <input
        ref="fileInputRef"
        class="file-input"
        type="file"
        multiple
        @change="handleFileChange"
      />
      <div
        ref="editableRef"
        class="composer-input"
        :class="{ disabled: blocked }"
        :contenteditable="blocked ? 'false' : 'true'"
        :data-placeholder="placeholder"
        role="textbox"
        aria-multiline="true"
        @keydown="handleComposerKeydown"
        @input="handleInput"
        @paste="handlePaste"
        @compositionstart="handleCompositionStart"
        @compositionend="handleCompositionEnd"
        @click="emitSelectionChange"
        @keyup="emitSelectionChange"
        @focus="emitSelectionChange"
        @blur="emitSelectionChange"
      />
      <div v-if="blocked" class="blocked-tip">{{ blockedText }}</div>
      <div class="input-toolbar">
        <div class="toolbar-left">
          <div v-if="showEngineSelector" class="toolbar-select engine-select">
            <PluginDevInlineSelect
              :model-value="selectedEngine"
              :options="engineSelectOptions"
              label="Engine"
              :selected-status="selectedEngineHealthStatus || null"
              :selected-status-title="selectedEngineHealthTitle"
              @update:model-value="handleEngineChange"
            />
          </div>
          <div v-if="showAgentSelector" class="toolbar-select agent-select">
            <PluginDevInlineSelect
              :model-value="selectedAgent"
              :options="agentSelectOptions"
              label="Agent"
              @update:model-value="handleAgentChange"
            />
          </div>
          <div
            v-else-if="showEngineStatusIndicator"
            class="engine-status-indicator"
            :title="engineStatusTitle"
            :aria-label="engineStatusTitle"
          >
            <span class="engine-status-dot" :class="engineStatusClass" aria-hidden="true"></span>
          </div>
          <div v-if="showModelSelector" class="toolbar-select model-select">
            <PluginDevInlineSelect
              :model-value="selectedModelId"
              :options="modelSelectOptions"
              label="Model"
              @update:model-value="handleModelChange"
            />
          </div>
          <button
            v-if="enableFileAttachment"
            class="attachment-btn"
            type="button"
            :disabled="blocked || isUploadingAttachments"
            :title="filePickerLabel || 'Attach files'"
            :aria-label="filePickerLabel || 'Attach files'"
            @click="openFilePicker"
          >
            {{ filePickerLabel || 'Attach files' }}
          </button>
        </div>
        <button
          class="send-btn"
          :class="[`state-${actionMode}`, { 'is-interrupting': isInterrupting }]"
          :disabled="!isActionEnabled"
          :title="actionTitle"
          :aria-label="actionTitle"
          @click="handleActionClick"
        >
          <ArrowUp v-if="actionMode === 'send'" class="send-icon" aria-hidden="true" />
          <span v-else-if="actionMode === 'interrupt'" class="interrupt-stack" aria-hidden="true">
            <LoaderCircle class="interrupt-spinner" />
            <Square class="interrupt-stop-icon" />
          </span>
          <CircleOff v-else class="disabled-icon" aria-hidden="true" />
          <span class="sr-only">{{ actionTitle }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowUp, CircleOff, LoaderCircle, Square } from 'lucide-vue-next'
import { parseContextTokens } from '@dawnchat/host-orchestration-sdk/assistant-client'
import PluginDevInlineSelect, { type PluginDevInlineSelectOption } from '@/features/coding-agent/components/plugin-dev-chat/PluginDevInlineSelect.vue'
import PluginDevComposerFileTags, {
  type ComposerPendingFileTag
} from '@/features/coding-agent/components/plugin-dev-chat/PluginDevComposerFileTags.vue'
import PluginDevComposerImageTags from '@/features/coding-agent/components/plugin-dev-chat/PluginDevComposerImageTags.vue'
import type { PromptFilePart } from '@/services/coding-agent/engineAdapter'

interface ModelOption {
  id: string
  label: string
}

interface AgentOption {
  id: string
  label?: string
  description?: string
}

interface EngineOption {
  id: string
  label: string
}

const props = withDefaults(defineProps<{
  modelValue: string
  placeholder: string
  selectedEngine: string
  selectedEngineLabel?: string
  selectedEngineHealthStatus?: 'checking' | 'healthy' | 'unhealthy'
  selectedEngineHealthTitle?: string
  selectedAgent: string
  selectedModelId: string
  engineOptions: EngineOption[]
  availableAgents: AgentOption[]
  availableModels: ModelOption[]
  canSend: boolean
  canInterrupt?: boolean
  isRunning?: boolean
  isInterrupting?: boolean
  blocked: boolean
  blockedText: string
  runLabel: string
  showEngineSelector?: boolean
  showAgentSelector?: boolean
  showModelSelector?: boolean
  pendingImages?: PromptFilePart[]
  pendingFiles?: ComposerPendingFileTag[]
  enableFileAttachment?: boolean
  isUploadingAttachments?: boolean
  filePickerLabel?: string
  fileTagsAriaLabel?: string
  fileTagRemovePrefix?: string
}>(), {
  showEngineSelector: true,
  showAgentSelector: true,
  showModelSelector: true,
  canInterrupt: false,
  isRunning: false,
  isInterrupting: false,
  pendingImages: () => [],
  pendingFiles: () => [],
  enableFileAttachment: false,
  isUploadingAttachments: false,
  filePickerLabel: '',
  fileTagsAriaLabel: 'Attached files',
  fileTagRemovePrefix: 'Remove'
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'select-engine': [value: string]
  'select-agent': [value: string]
  'select-model': [value: string]
  'selection-change': [payload: { start: number; end: number; focused: boolean }]
  'paste-image': [parts: PromptFilePart[]]
  'preview-image': [payload: { index: number; anchorEl: HTMLElement | null }]
  'remove-image': [index: number]
  'pick-files': [files: File[]]
  'remove-file': [index: number]
  send: []
  interrupt: []
}>()
const editableRef = ref<HTMLDivElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const isComposing = ref(false)
const actionMode = computed<'send' | 'interrupt' | 'disabled'>(() => {
  if (props.canInterrupt) return 'interrupt'
  if (props.canSend) return 'send'
  return 'disabled'
})
const isActionEnabled = computed(() => {
  if (actionMode.value === 'disabled') return false
  if (actionMode.value === 'interrupt' && props.isInterrupting) return false
  return true
})
const actionTitle = computed(() => {
  if (actionMode.value === 'interrupt') {
    return props.isInterrupting ? '正在取消' : '取消运行'
  }
  if (actionMode.value === 'send') {
    return props.runLabel || '发送'
  }
  return '当前不可发送'
})
const engineStatusTitle = computed(() => {
  return props.selectedEngineHealthTitle || props.selectedEngineLabel || props.selectedEngine || 'Agent 引擎状态'
})
const showEngineStatusIndicator = computed(() => {
  return !props.showEngineSelector && Boolean(props.selectedEngine || props.selectedEngineLabel || props.selectedEngineHealthStatus)
})
const engineStatusClass = computed(() => {
  return props.selectedEngineHealthStatus ? `is-${props.selectedEngineHealthStatus}` : 'is-idle'
})

const engineSelectOptions = computed<PluginDevInlineSelectOption[]>(() => {
  return props.engineOptions.map((engine) => ({
    value: engine.id,
    label: engine.label,
    title: engine.label
  }))
})

const agentSelectOptions = computed<PluginDevInlineSelectOption[]>(() => {
  return props.availableAgents.map((agent) => ({
    value: agent.id,
    label: agent.label || agent.id,
    title: agent.description || agent.label || agent.id,
    description: agent.description || ''
  }))
})

const modelSelectOptions = computed<PluginDevInlineSelectOption[]>(() => {
  return props.availableModels.map((model) => ({
    value: model.id,
    label: model.label,
    title: model.label
  }))
})

const normalizeRawText = (value: string): string => {
  return String(value || '').replace(/\u00a0/g, ' ')
}

const serializeNode = (node: Node): string => {
  if (node.nodeType === Node.TEXT_NODE) {
    return normalizeRawText((node as Text).data || '')
  }
  if (!(node instanceof HTMLElement)) {
    return ''
  }
  if (node.dataset.tokenRaw) {
    return String(node.dataset.tokenRaw || '')
  }
  if (node.tagName === 'BR') {
    return '\n'
  }
  let text = ''
  node.childNodes.forEach((child) => {
    text += serializeNode(child)
  })
  if ((node.tagName === 'DIV' || node.tagName === 'P') && text && !text.endsWith('\n')) {
    text += '\n'
  }
  return text
}

const serializeEditable = () => {
  const el = editableRef.value
  if (!el) return ''
  let text = ''
  el.childNodes.forEach((node) => {
    text += serializeNode(node)
  })
  return text
}

const rawLength = (node: Node): number => {
  if (node.nodeType === Node.TEXT_NODE) {
    return normalizeRawText((node as Text).data || '').length
  }
  if (!(node instanceof HTMLElement)) return 0
  if (node.dataset.tokenRaw) {
    return String(node.dataset.tokenRaw || '').length
  }
  if (node.tagName === 'BR') return 1
  let total = 0
  node.childNodes.forEach((child) => {
    total += rawLength(child)
  })
  if ((node.tagName === 'DIV' || node.tagName === 'P') && total > 0) {
    return total + 1
  }
  return total
}

const findOffsetFromPosition = (container: Node | null, offset: number): number => {
  const root = editableRef.value
  if (!root || !container) return 0
  let total = 0
  const walk = (node: Node): boolean => {
    if (node === container) {
      if (node.nodeType === Node.TEXT_NODE) {
        total += Math.min(offset, normalizeRawText((node as Text).data || '').length)
        return true
      }
      const children = node.childNodes
      for (let i = 0; i < Math.min(offset, children.length); i += 1) {
        total += rawLength(children[i])
      }
      return true
    }
    if (node.nodeType === Node.TEXT_NODE) {
      total += rawLength(node)
      return false
    }
    if (node instanceof HTMLElement && node.dataset.tokenRaw) {
      total += rawLength(node)
      return false
    }
    const children = node.childNodes
    for (let i = 0; i < children.length; i += 1) {
      if (walk(children[i])) return true
    }
    return false
  }
  walk(root)
  return total
}

const emitSelectionChange = () => {
  const el = editableRef.value
  if (!el) {
    emit('selection-change', { start: 0, end: 0, focused: false })
    return
  }
  const selection = window.getSelection()
  if (!selection || selection.rangeCount === 0) {
    emit('selection-change', {
      start: 0,
      end: 0,
      focused: document.activeElement === el
    })
    return
  }
  const range = selection.getRangeAt(0)
  const start = findOffsetFromPosition(range.startContainer, range.startOffset)
  const end = findOffsetFromPosition(range.endContainer, range.endOffset)
  emit('selection-change', {
    start,
    end,
    focused: document.activeElement === el
  })
}

const renderEditableFromModel = () => {
  const el = editableRef.value
  if (!el) return
  const current = serializeEditable()
  if (current === props.modelValue) return
  const fragment = document.createDocumentFragment()
  const segments = parseContextTokens(props.modelValue || '')
  for (const seg of segments) {
    if (seg.type === 'text') {
      if (seg.text) {
        fragment.appendChild(document.createTextNode(seg.text))
      }
      continue
    }
    const tokenEl = document.createElement('span')
    tokenEl.className = 'context-chip'
    tokenEl.contentEditable = 'false'
    tokenEl.dataset.tokenRaw = seg.data.raw
    tokenEl.dataset.preview = seg.data.preview
    const dot = document.createElement('span')
    dot.className = 'chip-dot'
    const text = document.createElement('span')
    text.className = 'chip-text'
    text.textContent = seg.data.preview || 'context'
    const removeButton = document.createElement('button')
    removeButton.className = 'chip-remove'
    removeButton.type = 'button'
    removeButton.textContent = '×'
    removeButton.title = '移除上下文'
    removeButton.setAttribute('aria-label', '移除上下文')
    removeButton.addEventListener('mousedown', (event) => {
      event.preventDefault()
    })
    removeButton.addEventListener('click', () => {
      tokenEl.remove()
      focusEditableAtEnd()
      void syncModelValueFromEditable()
    })
    tokenEl.append(dot, text, removeButton)
    fragment.appendChild(tokenEl)
  }
  el.replaceChildren(fragment)
}

const syncModelValueFromEditable = async () => {
  const value = serializeEditable()
  emit('update:modelValue', value)
  await nextTick()
  emitSelectionChange()
}

const handleInput = async () => {
  await syncModelValueFromEditable()
}

const focusEditableAtEnd = () => {
  const el = editableRef.value
  if (!el) return
  el.focus()
  const selection = window.getSelection()
  if (!selection) return
  const range = document.createRange()
  range.selectNodeContents(el)
  range.collapse(false)
  selection.removeAllRanges()
  selection.addRange(range)
}

const insertTextAtCaret = (text: string) => {
  const el = editableRef.value
  const selection = window.getSelection()
  if (!el || !selection) return
  if (selection.rangeCount === 0) {
    focusEditableAtEnd()
  }
  const activeSelection = window.getSelection()
  if (!activeSelection || activeSelection.rangeCount === 0) return
  const range = activeSelection.getRangeAt(0)
  range.deleteContents()
  const node = document.createTextNode(text)
  range.insertNode(node)
  range.setStartAfter(node)
  range.setEndAfter(node)
  activeSelection.removeAllRanges()
  activeSelection.addRange(range)
}

const removeAdjacentToken = (direction: 'backward' | 'forward'): boolean => {
  const el = editableRef.value
  const selection = window.getSelection()
  if (!el || !selection || selection.rangeCount === 0 || !selection.isCollapsed) return false
  const range = selection.getRangeAt(0)
  const { startContainer, startOffset } = range
  let target: HTMLElement | null = null
  if (startContainer.nodeType === Node.TEXT_NODE) {
    const textNode = startContainer as Text
    if (direction === 'backward' && startOffset === 0) {
      const prev = textNode.previousSibling
      if (prev instanceof HTMLElement && prev.dataset.tokenRaw) target = prev
    }
    if (direction === 'forward' && startOffset === textNode.data.length) {
      const next = textNode.nextSibling
      if (next instanceof HTMLElement && next.dataset.tokenRaw) target = next
    }
  } else if (startContainer instanceof HTMLElement) {
    const children = startContainer.childNodes
    if (direction === 'backward' && startOffset > 0) {
      const prev = children[startOffset - 1]
      if (prev instanceof HTMLElement && prev.dataset.tokenRaw) target = prev
    }
    if (direction === 'forward' && startOffset < children.length) {
      const next = children[startOffset]
      if (next instanceof HTMLElement && next.dataset.tokenRaw) target = next
    }
  }
  if (!target) return false
  target.remove()
  return true
}

const handleCompositionStart = () => {
  isComposing.value = true
}

const handleCompositionEnd = () => {
  isComposing.value = false
  emitSelectionChange()
}

const toDataUrl = async (file: File): Promise<string> => {
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      resolve(String(reader.result || ''))
    }
    reader.onerror = () => {
      reject(reader.error || new Error('读取剪贴板图片失败'))
    }
    reader.readAsDataURL(file)
  })
}

const extractClipboardImages = async (event: ClipboardEvent): Promise<PromptFilePart[]> => {
  const items = Array.from(event.clipboardData?.items || [])
  const imageFilesFromItems = items
    .filter((item) => item.kind === 'file' && String(item.type || '').toLowerCase().startsWith('image/'))
    .map((item) => item.getAsFile())
    .filter((file): file is File => Boolean(file))
  const imageFilesFromList = Array.from(event.clipboardData?.files || []).filter((file) =>
    String(file.type || '').toLowerCase().startsWith('image/')
  )
  const imageFiles = imageFilesFromItems.length > 0 ? imageFilesFromItems : imageFilesFromList
  if (imageFiles.length === 0) return []
  return await Promise.all(
    imageFiles.map(async (file, index) => {
      const mime = String(file.type || 'application/octet-stream').trim() || 'application/octet-stream'
      const name = String(file.name || '').trim() || `pasted-image-${Date.now()}-${index + 1}.png`
      return {
        type: 'file' as const,
        mime,
        filename: name,
        url: await toDataUrl(file)
      }
    })
  )
}

const handlePaste = async (event: ClipboardEvent) => {
  const hasImageInClipboard = Array.from(event.clipboardData?.items || []).some((item) => {
    return item.kind === 'file' && String(item.type || '').toLowerCase().startsWith('image/')
  }) || Array.from(event.clipboardData?.files || []).some((file) => {
    return String(file.type || '').toLowerCase().startsWith('image/')
  })
  if (hasImageInClipboard) {
    // 必须先拦截默认粘贴，避免浏览器先把图片节点插入 contenteditable。
    event.preventDefault()
  }
  const imageParts = await extractClipboardImages(event)
  if (imageParts.length > 0) {
    emit('paste-image', imageParts)
    return
  }
  event.preventDefault()
  const text = String(event.clipboardData?.getData('text/plain') || '').replace(/\r\n?/g, '\n')
  if (!text) return
  insertTextAtCaret(text)
  await syncModelValueFromEditable()
}

const handleComposerKeydown = async (event: KeyboardEvent) => {
  const isImeConfirm = event.isComposing || isComposing.value || (event as KeyboardEvent & { keyCode?: number }).keyCode === 229
  if (event.key === 'Enter' && isImeConfirm) {
    return
  }
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (!props.canSend) return
    emit('send')
    return
  }
  if (event.key === 'Enter' && event.shiftKey) {
    event.preventDefault()
    insertTextAtCaret('\n')
    await syncModelValueFromEditable()
    return
  }
  if (event.key === 'Backspace') {
    if (removeAdjacentToken('backward')) {
      event.preventDefault()
      await syncModelValueFromEditable()
    }
    return
  }
  if (event.key === 'Delete') {
    if (removeAdjacentToken('forward')) {
      event.preventDefault()
      await syncModelValueFromEditable()
    }
  }
}

const handleActionClick = () => {
  if (!isActionEnabled.value) return
  if (actionMode.value === 'interrupt') {
    emit('interrupt')
    return
  }
  if (actionMode.value === 'send') {
    emit('send')
  }
}

const handleEngineChange = (value: string) => {
  emit('select-engine', value)
}

const handleAgentChange = (value: string) => {
  emit('select-agent', value)
}

const handleModelChange = (value: string) => {
  emit('select-model', value)
}

const openFilePicker = () => {
  if (props.blocked || props.isUploadingAttachments) return
  fileInputRef.value?.click()
}

const handleFileChange = (event: Event) => {
  const input = event.target as HTMLInputElement | null
  const files = Array.from(input?.files || [])
  if (files.length > 0) {
    emit('pick-files', files)
  }
  if (input) {
    input.value = ''
  }
}

watch(
  () => props.modelValue,
  () => {
    renderEditableFromModel()
  }
)

onMounted(() => {
  renderEditableFromModel()
})
</script>

<style scoped>
.composer {
  border-top: 1px solid var(--color-border);
  padding: 0.85rem 1rem 1rem 1rem;
}

.input-wrapper {
  display: flex;
  flex-direction: column;
  background: var(--color-surface-3);
  border: 1px solid var(--color-border-strong);
  border-radius: 10px;
  padding: 0.72rem 0.8rem 0.56rem 0.8rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.file-input {
  display: none;
}

.input-wrapper:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-primary) 18%, transparent);
}

.composer-input {
  width: 100%;
  min-height: 92px;
  max-height: 210px;
  overflow-y: auto;
  border: none;
  background: transparent;
  color: var(--color-text);
  outline: none;
  font-family: inherit;
  font-size: 0.92rem;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.composer-input.disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.composer-input:empty::before {
  content: attr(data-placeholder);
  color: var(--color-text-secondary);
  pointer-events: none;
}

.composer-input :deep(.context-chip) {
  display: inline-flex;
  align-items: center;
  gap: 0.42rem;
  max-width: min(100%, 22rem);
  margin: 0 0.28rem 0.18rem 0;
  padding: 0.18rem 0.24rem 0.18rem 0.3rem;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--color-primary) 28%, var(--color-border-strong));
  background: color-mix(in srgb, var(--color-primary) 14%, var(--color-surface-2));
  color: color-mix(in srgb, var(--color-primary) 82%, var(--color-text));
  font-size: 0.78rem;
  line-height: 1.2;
  user-select: none;
  vertical-align: middle;
  box-shadow:
    inset 0 1px 0 color-mix(in srgb, white 10%, transparent),
    0 1px 2px rgba(0, 0, 0, 0.08);
}

.composer-input :deep(.chip-dot) {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-primary) 78%, white 4%);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary) 16%, transparent);
}

.composer-input :deep(.chip-text) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: inherit;
  font-weight: 500;
}

.composer-input :deep(.chip-remove) {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  cursor: pointer;
  font-size: 0.86rem;
  line-height: 1;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.composer-input :deep(.chip-remove:hover) {
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
  color: var(--color-danger);
}

.blocked-tip {
  margin-top: 0.4rem;
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}

.input-toolbar {
  margin-top: 0.65rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.7rem;
}

.toolbar-left {
  min-width: 0;
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: max-content;
  align-items: center;
  gap: 0.42rem;
  flex: 1 1 auto;
  justify-content: start;
  overflow-x: auto;
  overflow-y: visible;
}

.toolbar-select {
  display: block;
  flex: 0 0 auto;
}

.engine-status-indicator {
  width: 24px;
  height: 24px;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.engine-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-text-secondary) 88%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 14%, transparent);
  color: color-mix(in srgb, var(--color-text-secondary) 88%, transparent);
}

.engine-status-dot.is-healthy {
  background: #22c55e;
  color: #22c55e;
}

.engine-status-dot.is-unhealthy {
  background: #ef4444;
  color: #ef4444;
}

.engine-status-dot.is-checking {
  background: #f59e0b;
  color: #f59e0b;
  animation: select-status-pulse 1.15s ease-in-out infinite;
}

.engine-status-dot.is-idle {
  background: color-mix(in srgb, var(--color-text-secondary) 88%, transparent);
  color: color-mix(in srgb, var(--color-text-secondary) 88%, transparent);
}

.engine-select {
  max-width: 100%;
}

.agent-select {
  max-width: 100%;
}

.model-select {
  max-width: 11rem;
}

.toolbar-select :deep(.inline-select) {
  width: auto;
}

.toolbar-select :deep(.inline-select-trigger) {
  width: auto;
  min-width: 0;
  max-width: 100%;
}

.attachment-btn {
  height: 26px;
  padding: 0 0.65rem;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--color-border) 84%, transparent);
  background: color-mix(in srgb, var(--color-surface-2) 86%, transparent);
  color: var(--color-text-secondary);
  font-size: 0.76rem;
  line-height: 1;
  cursor: pointer;
  white-space: nowrap;
}

.attachment-btn:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--color-primary) 36%, var(--color-border));
  color: var(--color-text);
}

.attachment-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.engine-select :deep(.inline-select-label) {
  max-width: 6.2rem;
}

.agent-select :deep(.inline-select-label) {
  max-width: 6.8rem;
}

.model-select :deep(.inline-select-label) {
  max-width: 8.2rem;
}

.model-select :deep(.inline-select),
.model-select :deep(.inline-select-trigger) {
  width: 100%;
  max-width: 11rem;
}

.send-btn {
  --btn-fg: var(--color-button-neutral-fg);
  --btn-bg: var(--color-button-neutral-bg);
  --btn-border: var(--color-button-neutral-border);
  --btn-shadow: color-mix(in srgb, var(--color-text) 8%, transparent);
  flex: 0 0 auto;
  position: relative;
  border: 1px solid var(--btn-border);
  border-radius: 9px;
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--btn-fg);
  background: var(--btn-bg);
  box-shadow: 0 3px 10px var(--btn-shadow);
  cursor: pointer;
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease,
    border-color 0.16s ease,
    background-color 0.16s ease,
    color 0.16s ease,
    opacity 0.16s ease;
}

.send-btn.state-send {
  --btn-fg: var(--color-on-primary);
  --btn-bg: var(--color-button-emphasis-bg);
  --btn-border: color-mix(in srgb, var(--color-primary) 64%, var(--color-border-strong));
  --btn-shadow: color-mix(in srgb, var(--color-primary) 30%, transparent);
}

.send-btn.state-interrupt {
  --btn-fg: var(--color-button-danger-fg);
  --btn-bg: var(--color-button-danger-bg);
  --btn-border: var(--color-button-danger-border);
  --btn-shadow: color-mix(in srgb, var(--color-danger) 20%, transparent);
}

.send-btn.state-disabled {
  --btn-fg: var(--color-text-disabled);
  --btn-bg: var(--color-button-neutral-bg);
  --btn-border: var(--color-button-neutral-border);
  --btn-shadow: transparent;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 14px var(--btn-shadow);
}

.send-btn:active:not(:disabled) {
  transform: translateY(0);
}

.send-btn:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--color-primary) 24%, transparent),
    0 3px 10px var(--btn-shadow);
}

.send-btn:disabled {
  opacity: 0.92;
  cursor: not-allowed;
  transform: none;
}

.send-icon,
.disabled-icon {
  width: 15px;
  height: 15px;
  stroke-width: 2.15;
}

.send-icon {
  transform: translateY(-0.2px);
}

.interrupt-stack {
  width: 16px;
  height: 16px;
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.interrupt-spinner {
  width: 16px;
  height: 16px;
  opacity: 0.95;
  animation: ring-spin 1.25s linear infinite;
  stroke-width: 2;
}

.interrupt-stop-icon {
  width: 8px;
  height: 8px;
  position: absolute;
  stroke-width: 2.6;
  fill: currentColor;
}

.send-btn.is-interrupting .interrupt-spinner {
  animation-duration: 0.78s;
}

.send-btn.is-interrupting .interrupt-stop-icon {
  animation: interrupt-pulse 0.9s ease-in-out infinite;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@keyframes ring-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes interrupt-pulse {
  0%,
  100% {
    opacity: 0.72;
  }
  50% {
    opacity: 1;
  }
}

@keyframes select-status-pulse {
  0%,
  100% {
    opacity: 0.7;
    transform: scale(0.92);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
