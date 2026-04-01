<template>
  <div class="chat-shell">
    <div v-if="showPanelHeader && (panelTitle || (showRulesStatus && rulesVersionText))" class="panel-header">
      <div class="title-row">
        <h2 v-if="panelTitle">{{ panelTitle }}</h2>
        <p v-if="showRulesStatus && rulesVersionText" class="rules-status">{{ rulesVersionText }}</p>
      </div>
    </div>

    <PluginDevSessionTabs
      v-if="showSessionTabs"
      :sessions="sessions"
      :active-session-id="activeSessionId"
      :selected-engine="selectedEngine"
      :selected-engine-health-status="engineHealthStatus"
      :selected-engine-health-title="engineHealthTitle"
      :selected-agent="selectedAgent"
      :selected-tts-engine="selectedTtsEngine"
      :engine-options="engineOptions"
      :available-agents="availableAgents"
      :tts-engine-options="ttsEngineOptions"
      :show-tts-control="showTtsControl"
      :tts-enabled="ttsEnabled"
      :is-tts-active="isTtsActive"
      @switch-session="handleSwitchSession"
      @create-session="handleCreateSession"
      @select-engine="handleEngineChange"
      @select-agent="handleAgentChange"
      @select-tts-engine="(value) => emit('select-tts-engine', value)"
      @toggle-tts-enabled="emit('toggle-tts-enabled')"
    />

    <PluginDevMessageList
      :chat-rows="chatRows"
      :permission-cards="permissionCards"
      :question-cards="questionCards"
      :timeline-items="timelineItems"
      :active-reasoning-item-id="activeReasoningItemId"
      :is-streaming="isStreaming"
      :waiting-reason="waitingReason"
      :can-switch-plan-to-build="allowPlanToBuild && canSwitchPlanToBuild"
      :last-error="lastError"
      :last-error-raw="lastErrorRaw"
      :todos="activeSessionTodos"
      :empty-text="emptyText"
      :streaming-text="streamingText"
      @permission="handlePermission"
      @question-reply="handleQuestionReply"
      @question-reject="handleQuestionReject"
      @switch-to-build="handleSwitchToBuild"
    />

    <p v-if="switchNotice" class="switch-notice">{{ switchNotice }}</p>

    <PluginDevComposer
      v-if="showComposer"
      :model-value="modelValue"
      :placeholder="placeholder"
      :selected-engine="selectedEngine"
      :selected-engine-label="selectedEngineLabel"
      :selected-engine-health-status="engineHealthStatus"
      :selected-engine-health-title="engineHealthTitle"
      :selected-agent="selectedAgent"
      :selected-model-id="selectedModelId"
      :engine-options="engineOptions"
      :available-agents="availableAgents"
      :available-models="availableModels"
      :can-send="canSend"
      :can-interrupt="canInterrupt"
      :is-running="isStreaming"
      :is-interrupting="isInterrupting"
      :blocked="isBlocked"
      :blocked-text="effectiveBlockedText"
      :run-label="runLabel"
      :show-engine-selector="showEngineSelector"
      :show-agent-selector="showAgentSelector"
      :show-model-selector="showModelSelector"
      @update:model-value="(value) => emit('update:modelValue', value)"
      @select-engine="handleEngineChange"
      @select-agent="handleAgentChange"
      @select-model="handleModelChange"
      @selection-change="(payload) => emit('composer-selection-change', payload)"
      @send="handleSend"
      @interrupt="handleInterrupt"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useEngineHealth } from '@/composables/useEngineHealth'
import { useI18n } from '@/composables/useI18n'
import { logger } from '@/utils/logger'
import { useCodingAgentStore } from '@/features/coding-agent'
import { expandContextTokens } from '@/services/plugin-ui-bridge/contextToken'
import { isEngineId, type EngineId } from '@/services/coding-agent/adapterRegistry'
import type { WorkspaceResolveOptions, WorkspaceTarget } from '@/features/coding-agent'
import type { TtsPlaybackState } from '@/services/tts/ttsPlaybackQueue'
import PluginDevSessionTabs from '@/features/coding-agent/components/plugin-dev-chat/PluginDevSessionTabs.vue'
import PluginDevMessageList from '@/features/coding-agent/components/plugin-dev-chat/PluginDevMessageList.vue'
import PluginDevComposer from '@/features/coding-agent/components/plugin-dev-chat/PluginDevComposer.vue'

const props = withDefaults(defineProps<{
  modelValue: string
  workspaceTarget?: WorkspaceTarget | null
  pluginId?: string
  panelTitle?: string
  emptyText: string
  placeholder: string
  streamingText: string
  blockedText: string
  externalBlocked?: boolean
  externalBlockedText?: string
  runLabel: string
  newChatLabel: string
  showRulesStatus?: boolean
  showPanelHeader?: boolean
  showSessionTabs?: boolean
  showEngineSelector?: boolean
  showAgentSelector?: boolean
  showModelSelector?: boolean
  showComposer?: boolean
  allowPlanToBuild?: boolean
  forceEngine?: EngineId | null
  forceAgent?: string | null
  showTtsControl?: boolean
  ttsEnabled?: boolean
  ttsPlaybackState?: TtsPlaybackState
  ttsStreamStatus?: 'idle' | 'connecting' | 'reconnecting' | 'streaming' | 'closed'
  selectedTtsEngine?: string
  ttsEngineOptions?: Array<{ id: string; label: string }>
  planSwitchAppliedText?: string
  planKeepInputHintText?: string
  planBuildPrefillText?: string
}>(), {
  workspaceTarget: null,
  pluginId: undefined,
  panelTitle: '',
  showRulesStatus: false,
  showPanelHeader: true,
  showSessionTabs: true,
  showEngineSelector: true,
  showAgentSelector: true,
  showModelSelector: true,
  showComposer: true,
  showTtsControl: false,
  ttsEnabled: true,
  ttsPlaybackState: 'idle',
  ttsStreamStatus: 'idle',
  selectedTtsEngine: 'system',
  ttsEngineOptions: () => [],
  allowPlanToBuild: false,
  forceEngine: null,
  forceAgent: null,
  planSwitchAppliedText: '已切换到 Build 模式。',
  planKeepInputHintText: '已保留你当前输入。',
  planBuildPrefillText: '请根据计划开始执行实现。',
  externalBlocked: false,
  externalBlockedText: ''
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'composer-selection-change': [payload: { start: number; end: number; focused: boolean }]
  'toggle-tts-enabled': []
  'stop-tts': []
  'select-tts-engine': [value: string]
}>()

const { t } = useI18n()
const switchNotice = ref('')
const isInterrupting = ref(false)
let lastSwitchTimestamp = 0
let lastSwitchSession = ''

const codingAgentStore = useCodingAgentStore()
const {
  selectedEngine,
  availableAgents,
  availableModels,
  engineOptions,
  selectedAgent,
  selectedModelId,
  chatRows,
  timelineItems,
  activeReasoningItemId,
  permissionCards,
  questionCards,
  activeSessionTodos,
  canSwitchPlanToBuild,
  sessions,
  activeSessionId,
  isStreaming,
  waitingReason,
  canInterrupt,
  lastError,
  lastErrorRaw,
  rulesStatus
} = storeToRefs(codingAgentStore)
const { engineHealthStatus, engineHealthTitle } = useEngineHealth(selectedEngine as any)

// Permission 卡片只负责展示与交互，不应阻断用户继续输入/发送。
const isBlocked = computed(() => questionCards.value.length > 0 || Boolean(props.externalBlocked))
const effectiveBlockedText = computed(() => {
  if (props.externalBlocked && props.externalBlockedText) {
    return props.externalBlockedText
  }
  return props.blockedText
})
const canSend = computed(() => props.modelValue.trim().length > 0 && !isStreaming.value && !isBlocked.value)
const rulesVersionText = computed(() => {
  const status = rulesStatus.value
  if (!status || !status.enabled) {
    return String((t.value as any).apps?.sharedRulesDisabled || '共享规则: 未启用')
  }
  const version = String(status.current_version || '').trim()
  if (!version) {
    return String((t.value as any).apps?.sharedRulesEnabled || '共享规则: 已启用')
  }
  return String((t.value as any).apps?.sharedRulesVersion || '共享规则: v{version}').replace('{version}', version)
})

const selectedEngineLabel = computed(() => {
  return engineOptions.value.find((item) => item.id === selectedEngine.value)?.label || selectedEngine.value
})
const isTtsActive = computed(() => {
  if (!props.ttsEnabled) return false
  if (props.ttsStreamStatus === 'streaming' || props.ttsStreamStatus === 'connecting' || props.ttsStreamStatus === 'reconnecting') {
    return true
  }
  return props.ttsPlaybackState === 'playing' || props.ttsPlaybackState === 'buffering'
})

function getWorkspaceOptions(forceRestart = false): WorkspaceResolveOptions {
  return {
    workspaceTarget: props.workspaceTarget || null,
    pluginId: props.pluginId,
    forceRestart
  }
}

async function syncForcedRuntimeSelection() {
  if (props.forceEngine && selectedEngine.value !== props.forceEngine) {
    codingAgentStore.selectEngine(props.forceEngine)
  }
  if (props.forceAgent && selectedAgent.value !== props.forceAgent) {
    codingAgentStore.selectAgent(props.forceAgent)
  }
}

const handleSend = async () => {
  if (canInterrupt.value && isStreaming.value) {
    await handleInterrupt()
    return
  }
  const content = props.modelValue.trim()
  if (!content) return
  const transformed = expandContextTokens(String(content)).trim()
  emit('update:modelValue', '')
  try {
    await syncForcedRuntimeSelection()
    await codingAgentStore.sendText(transformed, getWorkspaceOptions())
    logger.info('coding_chat_shell_send', {
      workspaceId: props.workspaceTarget?.id || props.pluginId || '',
      size: transformed.length,
      agent: selectedAgent.value,
      model: selectedModelId.value,
      sessionId: activeSessionId.value
    })
  } catch (err) {
    logger.error('coding_chat_shell_send_failed', err)
  }
}

const handleInterrupt = async () => {
  if (!canInterrupt.value || isInterrupting.value) return
  isInterrupting.value = true
  try {
    const ok = await codingAgentStore.interruptActiveRun()
    if (!ok) {
      logger.warn('coding_chat_shell_interrupt_not_applied', {
        sessionId: activeSessionId.value,
        engine: selectedEngine.value
      })
    } else {
      logger.info('coding_chat_shell_interrupt', {
        sessionId: activeSessionId.value,
        engine: selectedEngine.value
      })
    }
  } catch (err) {
    logger.error('coding_chat_shell_interrupt_failed', err)
  } finally {
    isInterrupting.value = false
  }
}

const handleAgentChange = (value: string) => {
  codingAgentStore.selectAgent(value)
}

const handleEngineChange = async (value: string) => {
  if (!isEngineId(value)) {
    logger.warn('coding_chat_shell_engine_invalid', { value })
    return
  }
  codingAgentStore.selectEngine(value)
  await codingAgentStore.ensureReadyWithWorkspace(getWorkspaceOptions())
  await syncForcedRuntimeSelection()
}

const handleModelChange = (value: string) => {
  codingAgentStore.selectModel(value)
}

const handlePermission = async (
  id: string,
  response: 'once' | 'always' | 'reject',
  remember?: boolean
) => {
  try {
    await codingAgentStore.replyPermission(id, response, remember)
  } catch (err) {
    logger.error('coding_chat_shell_permission_failed', err)
  }
}

const handleQuestionReply = async (requestID: string, answers: string[][]) => {
  try {
    await codingAgentStore.replyQuestion(requestID, answers)
  } catch (err) {
    logger.error('coding_chat_shell_question_reply_failed', err)
  }
}

const handleQuestionReject = async (requestID: string) => {
  try {
    await codingAgentStore.rejectQuestion(requestID)
  } catch (err) {
    logger.error('coding_chat_shell_question_reject_failed', err)
  }
}

const handleCreateSession = async () => {
  try {
    await codingAgentStore.createSession(props.newChatLabel, true)
  } catch (err) {
    logger.error('coding_chat_shell_create_session_failed', err)
  }
}

const handleSwitchToBuild = () => {
  if (!props.allowPlanToBuild) return
  const sessionId = String(activeSessionId.value || '')
  const now = Date.now()
  if (sessionId && sessionId === lastSwitchSession && now - lastSwitchTimestamp < 1500) {
    return
  }
  lastSwitchSession = sessionId
  lastSwitchTimestamp = now
  codingAgentStore.selectAgent('build')
  logger.info('coding_chat_shell_switch_to_build', {
    sessionId,
    fromAgent: 'plan',
    toAgent: 'build'
  })
  if (!props.modelValue.trim()) {
    emit('update:modelValue', props.planBuildPrefillText)
    switchNotice.value = props.planSwitchAppliedText
  } else {
    switchNotice.value = `${props.planSwitchAppliedText} ${props.planKeepInputHintText}`
  }
  window.setTimeout(() => {
    if (switchNotice.value.startsWith(props.planSwitchAppliedText)) {
      switchNotice.value = ''
    }
  }, 2400)
}

const handleSwitchSession = async (sessionID: string) => {
  try {
    await codingAgentStore.switchSession(sessionID)
  } catch (err) {
    logger.error('coding_chat_shell_switch_session_failed', err)
  }
}

watch(
  () => [props.forceEngine, props.forceAgent] as const,
  () => {
    syncForcedRuntimeSelection().catch((err) => {
      logger.error('coding_chat_shell_sync_forced_selection_failed', err)
    })
  },
  { immediate: true }
)

watch(
  () => [props.workspaceTarget?.id || '', props.pluginId || ''] as const,
  async ([workspaceId, pluginId], [prevWorkspaceId, prevPluginId]) => {
    if (!workspaceId && !pluginId) return
    if (workspaceId === prevWorkspaceId && pluginId === prevPluginId) return
    try {
      await syncForcedRuntimeSelection()
      await codingAgentStore.ensureReadyWithWorkspace(getWorkspaceOptions())
    } catch (err) {
      logger.error('coding_chat_shell_workspace_switch_failed', err)
    }
  }
)

onMounted(async () => {
  try {
    await syncForcedRuntimeSelection()
    await codingAgentStore.ensureReadyWithWorkspace(getWorkspaceOptions())
  } catch (err) {
    logger.error('coding_chat_shell_init_failed', err)
  }
})

</script>

<style scoped>
.chat-shell {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-surface-1);
}

.panel-header {
  padding: 1rem 1rem 0.7rem 1rem;
  border-bottom: 1px solid var(--color-border);
}

.title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.title-row h2 {
  margin: 0;
  font-size: 1rem;
}

.rules-status {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin: 0;
}

.switch-notice {
  margin: 0 1rem;
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}
</style>
