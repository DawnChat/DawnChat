<template>
  <div class="assistant-compact-shell">
    <div class="compact-input" :class="{ focused: inputFocused }">
      <textarea
        ref="inputRef"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="isBlocked"
        rows="1"
        @input="handleInput"
        @keydown="handleKeydown"
        @compositionstart="handleCompositionStart"
        @compositionend="handleCompositionEnd"
        @select="emitSelectionChange"
        @focus="handleFocus"
        @blur="handleBlur"
      />
      <button class="send-btn" :disabled="!canSend" @click="handleSend">{{ sendLabel }}</button>
    </div>
    <button class="expand-toggle" :class="{ active: panelExpanded }" @click="panelExpanded = !panelExpanded">
      {{ panelExpanded ? collapseLabel : expandLabel }}
    </button>
    <Transition name="compact-log-panel">
      <div class="overlay-panel" v-show="panelExpanded">
        <CodingChatShell
          :model-value="modelValue"
          :plugin-id="pluginId"
          :panel-title="''"
          :empty-text="emptyText"
          :placeholder="placeholder"
          :streaming-text="streamingText"
          :blocked-text="blockedText"
          :external-blocked="externalBlocked"
          :external-blocked-text="externalBlockedText"
          :run-label="sendLabel"
          :new-chat-label="newChatLabel"
          :show-rules-status="true"
          :show-panel-header="false"
          :show-session-tabs="false"
          :show-engine-selector="false"
          :show-agent-selector="false"
          :show-model-selector="false"
          :show-composer="false"
          :show-tts-control="true"
          :tts-enabled="ttsEnabled"
          :tts-playback-state="ttsPlaybackState"
          :tts-stream-status="ttsStreamStatus"
          :allow-plan-to-build="true"
          :plan-switch-applied-text="planSwitchAppliedText"
          :plan-keep-input-hint-text="planKeepInputHintText"
          :plan-build-prefill-text="planBuildPrefillText"
          @update:model-value="(value) => emit('updateModelValue', value)"
          @composer-selection-change="(payload) => emit('composerSelectionChange', payload)"
          @toggle-tts-enabled="emit('toggleTtsEnabled')"
          @stop-tts="emit('stopTts')"
        />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from '@/composables/useI18n'
import { expandContextTokens } from '@dawnchat/host-orchestration-sdk/assistant-client'
import { logger } from '@/utils/logger'
import CodingChatShell from '@/features/coding-agent/components/CodingChatShell.vue'
import { useCodingAgentStore } from '@/features/coding-agent/store/codingAgentStore'
import type { TtsPlaybackState } from '@/services/tts/ttsPlaybackQueue'

const props = withDefaults(defineProps<{
  modelValue: string
  pluginId: string
  externalBlocked: boolean
  externalBlockedText: string
  ttsEnabled: boolean
  ttsPlaybackState: TtsPlaybackState
  ttsStreamStatus: 'idle' | 'connecting' | 'reconnecting' | 'streaming' | 'closed'
}>(), {
  externalBlocked: false,
  externalBlockedText: ''
})

const emit = defineEmits<{
  updateModelValue: [value: string]
  composerSelectionChange: [payload: { start: number; end: number; focused: boolean }]
  toggleTtsEnabled: []
  stopTts: []
}>()

const panelExpanded = ref(false)
const inputFocused = ref(false)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const isComposing = ref(false)
const codingAgentStore = useCodingAgentStore()
const { questionCards, isStreaming } = storeToRefs(codingAgentStore)
const { t } = useI18n()

const labels = computed(() => {
  const apps = (t.value as any).apps || {}
  return {
    emptyText: String(apps.devChatEmpty || '等待输入指令...'),
    placeholder: String(apps.devChatPlaceholder || '描述你想要的修改...'),
    streamingText: String(apps.devChatStreaming || '正在生成中'),
    blockedText: String(apps.blockedByQuestion || '请先回答待处理问题或权限请求，再继续发送消息。'),
    externalBlockedText: String(apps.blockedByDepsInstall || '正在准备开发环境，完成后你就可以继续让 Coding Agent 修改代码。'),
    newChatLabel: String(apps.newChat || 'New Chat'),
    planSwitchAppliedText: String(apps.planSwitchApplied || '已切换到 Build 模式。'),
    planKeepInputHintText: String(apps.planKeepInputHint || '已保留你当前输入。'),
    planBuildPrefillText: String(apps.planBuildPrefill || '请根据计划开始执行实现。'),
    collapseLabel: String(apps.workbenchCompactCollapse || '收起日志'),
    expandLabel: String(apps.workbenchCompactExpand || '展开日志')
  }
})

const isBlocked = computed(() => questionCards.value.length > 0 || props.externalBlocked)
const canSend = computed(() => props.modelValue.trim().length > 0 && !isBlocked.value && !isStreaming.value)

const emptyText = computed(() => labels.value.emptyText)
const placeholder = computed(() => labels.value.placeholder)
const streamingText = computed(() => labels.value.streamingText)
const blockedText = computed(() => labels.value.blockedText)
const externalBlockedText = computed(() => labels.value.externalBlockedText)
const newChatLabel = computed(() => labels.value.newChatLabel)
const planSwitchAppliedText = computed(() => labels.value.planSwitchAppliedText)
const planKeepInputHintText = computed(() => labels.value.planKeepInputHintText)
const planBuildPrefillText = computed(() => labels.value.planBuildPrefillText)
const collapseLabel = computed(() => labels.value.collapseLabel)
const expandLabel = computed(() => labels.value.expandLabel)
const sendLabel = computed(() => String((t.value as any).common?.run || '发送'))

const emitSelectionChange = () => {
  const input = inputRef.value
  if (!input) {
    emit('composerSelectionChange', { start: 0, end: 0, focused: false })
    return
  }
  emit('composerSelectionChange', {
    start: input.selectionStart || 0,
    end: input.selectionEnd || 0,
    focused: document.activeElement === input
  })
}

const handleInput = (event: Event) => {
  const target = event.target as HTMLTextAreaElement
  emit('updateModelValue', target.value)
}

const handleFocus = () => {
  inputFocused.value = true
  emitSelectionChange()
}

const handleBlur = () => {
  inputFocused.value = false
  emitSelectionChange()
}

const handleSend = async () => {
  if (!canSend.value) return
  const transformed = expandContextTokens(String(props.modelValue || '')).trim()
  if (!transformed) return
  emit('updateModelValue', '')
  try {
    await codingAgentStore.sendText(transformed, { pluginId: props.pluginId })
  } catch (error) {
    logger.error('assistant_compact_shell_send_failed', error)
  }
}

const handleKeydown = async (event: KeyboardEvent) => {
  if (event.isComposing || isComposing.value || (event as KeyboardEvent & { keyCode?: number }).keyCode === 229) {
    return
  }
  if (event.key !== 'Enter' || event.shiftKey) return
  event.preventDefault()
  await handleSend()
}

const handleCompositionStart = () => {
  isComposing.value = true
}

const handleCompositionEnd = () => {
  isComposing.value = false
}
</script>

<style scoped>
.assistant-compact-shell {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.expand-toggle {
  pointer-events: auto;
  position: absolute;
  right: 0.9rem;
  bottom: 4.2rem;
  border: 1px solid color-mix(in srgb, var(--color-border-strong) 84%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-surface-1) 76%, transparent);
  color: var(--color-text-secondary);
  font-size: 0.74rem;
  min-height: 26px;
  padding: 0 0.64rem;
  backdrop-filter: blur(8px);
  z-index: 34;
}

.expand-toggle.active {
  color: var(--color-primary);
  border-color: color-mix(in srgb, var(--color-primary) 62%, var(--color-border-strong));
}

.compact-input {
  pointer-events: auto;
  position: absolute;
  right: 0.9rem;
  bottom: 0.9rem;
  width: min(560px, calc(100% - 1.6rem));
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  border: 1px solid color-mix(in srgb, var(--color-border-strong) 88%, transparent);
  border-radius: 14px;
  padding: 0.46rem 0.5rem 0.46rem 0.58rem;
  background: color-mix(in srgb, var(--color-surface-1) 78%, transparent);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.22);
  backdrop-filter: blur(10px);
  z-index: 30;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease,
    background-color 0.18s ease;
}

.compact-input.focused {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--color-primary) 74%, var(--color-border-strong));
  box-shadow:
    0 14px 34px rgba(0, 0, 0, 0.24),
    0 0 0 2px color-mix(in srgb, var(--color-primary) 20%, transparent);
  background: color-mix(in srgb, var(--color-surface-1) 84%, transparent);
}

.compact-input textarea {
  flex: 1;
  min-height: 24px;
  max-height: 160px;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: var(--color-text);
  font-size: 0.84rem;
  line-height: 1.42;
  padding: 0.18rem 0.3rem 0.16rem 0.2rem;
}

.compact-input textarea:disabled {
  opacity: 0.64;
}

.send-btn {
  border: 1px solid color-mix(in srgb, var(--color-primary) 62%, var(--color-border-strong));
  border-radius: 10px;
  min-height: 30px;
  padding: 0 0.72rem;
  background: color-mix(in srgb, var(--color-primary) 86%, black 4%);
  color: var(--color-on-primary);
  font-size: 0.76rem;
  font-weight: 600;
}

.send-btn:disabled {
  opacity: 0.56;
}

.overlay-panel {
  pointer-events: auto;
  position: absolute;
  right: 0.9rem;
  bottom: 6.15rem;
  width: min(760px, calc(100% - 1.6rem));
  height: min(62%, 520px);
  border: 1px solid color-mix(in srgb, var(--color-border-strong) 88%, transparent);
  border-radius: 12px;
  overflow: hidden;
  background: color-mix(in srgb, var(--color-surface-1) 58%, transparent);
  box-shadow: 0 16px 34px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(10px);
  z-index: 28;
}

.compact-log-panel-enter-active,
.compact-log-panel-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.compact-log-panel-enter-from,
.compact-log-panel-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.985);
}

@media (max-width: 960px) {
  .compact-input {
    width: calc(100% - 1.2rem);
    right: 0.6rem;
    bottom: 0.7rem;
  }

  .expand-toggle {
    right: 0.6rem;
    bottom: 3.9rem;
  }

  .overlay-panel {
    width: calc(100% - 1.2rem);
    height: min(68%, 520px);
    right: 0.6rem;
    bottom: 5.8rem;
  }
}
</style>
