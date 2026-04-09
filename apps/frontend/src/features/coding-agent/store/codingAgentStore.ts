import { defineStore } from 'pinia'
import { computed, ref, type Ref } from 'vue'
import { logger } from '@/utils/logger'
import { ENGINE_OPENCODE, isEngineId, type EngineId, getEngineAdapter } from '@/services/coding-agent/adapterRegistry'
import { getEngineOptions } from '@/services/coding-agent/engineCapabilities'
import type {
  ModelOption,
  PermissionCard,
  QuestionCard,
  SessionMeta,
  SessionState,
  SessionTodoItem,
  TimelineItem,
  WorkspaceResolveOptions,
  WorkspaceTarget
} from '@/features/coding-agent/store/types'
import { buildTimelineItems } from '@/features/coding-agent/store/timelineBuilder'
import { createEventDispatcher } from '@/features/coding-agent/store/eventDispatcher'
import { createPermissionQuestionService } from '@/features/coding-agent/store/permissionQuestionService'
import { createRuntimeMetaLoader } from '@/features/coding-agent/store/runtimeMeta'
import { createSessionCrud } from '@/features/coding-agent/store/sessionCrud'
import { extractSessionErrorRawMessage, normalizeSessionMeta, toReadableSessionError } from '@/features/coding-agent/store/sessionHelpers'
import { createMessageRepository } from '@/features/coding-agent/store/messageRepository'
import { createSessionStateRepository } from '@/features/coding-agent/store/sessionStateRepository'
import { createChatProjectionService } from '@/features/coding-agent/store/chatProjectionService'
import { createEngineConfigBridge } from '@/features/coding-agent/store/engineConfigBridge'
import { createRuntimeOrchestrator } from '@/features/coding-agent/store/runtimeOrchestrator'
import { createPermissionStateService } from '@/features/coding-agent/store/permissionStateService'
import type { PromptPart } from '@/services/coding-agent/engineAdapter'

interface EngineOption {
  id: EngineId
  label: string
}

interface AgentOption {
  id: string
  label: string
  description: string
  mode: string
  hidden: boolean
}

interface OpenCodeRulesStatus {
  enabled: boolean
  current_version?: string
  current_dir?: string
  updated_at?: string
  reason?: string
}

interface BuildSessionStateSnapshot {
  sessionId: string
  isStreaming: boolean
  sessionRunStatus: string
  transportStatus: string
  lastError: string | null
  lastErrorRaw: string | null
}

const AGENT_KEY = 'codingAgent:selectedAgent'
const MODEL_KEY = 'codingAgent:selectedModel'
const ENGINE_KEY = 'codingAgent:selectedEngine'
const ACTIVE_SESSION_PREFIX = 'codingAgent:activeSession:'

export const useCodingAgentStore = defineStore('codingAgent', () => {
  const persistedEngine = String(localStorage.getItem(ENGINE_KEY) || '').trim()
  const selectedEngine = ref<EngineId>(isEngineId(persistedEngine) ? persistedEngine : ENGINE_OPENCODE)
  const selectedAgent = ref<string>(localStorage.getItem(AGENT_KEY) || 'build')
  const selectedModelId = ref<string>(localStorage.getItem(MODEL_KEY) || '')
  const isReady = ref(false)
  const availableAgentOptions = ref<AgentOption[]>([
    { id: 'build', label: 'build', description: '', mode: 'primary', hidden: false },
    { id: 'plan', label: 'plan', description: '', mode: 'primary', hidden: false }
  ])
  const availableModels = ref<ModelOption[]>([])
  const rulesStatus = ref<OpenCodeRulesStatus | null>(null)
  const workspaceProfile = ref<WorkspaceTarget | null>(null)

  const sessions = ref<SessionMeta[]>([])
  const activeSessionId = ref<string>('')
  const sessionStateById = ref<Record<string, SessionState>>({})
  const sessionTodosById = ref<Record<string, SessionTodoItem[]>>({})
  const messageSessionById = ref<Record<string, string>>({})
  const boundWorkspaceTarget = ref<WorkspaceTarget | null>(null)
  const boundWorkspaceId = computed(() => String(boundWorkspaceTarget.value?.id || '').trim())
  const globalError = ref<string | null>(null)

  const _streamWatchdogs = ref<Record<string, number>>({})
  const _lastPermissionTimelineDebug = ref('')
  const _pendingLocalUserMessageIdsBySession = ref<Record<string, string[]>>({})
  const _eventUnsubscribe = ref<(() => void) | null>(null)
  const _ensureReadyPromise = ref<Promise<void> | null>(null)

  const selectedModel = computed(() => {
    return availableModels.value.find((item) => item.id === selectedModelId.value) || null
  })

  const engineOptions = computed<EngineOption[]>(() => {
    return getEngineOptions()
  })

  const availableAgents = computed<AgentOption[]>(() => {
    return availableAgentOptions.value
  })

  function getActiveAdapter() {
    return getEngineAdapter(selectedEngine.value)
  }

  const sessionId = computed(() => activeSessionId.value)

  const sessionStateRepository = createSessionStateRepository({
    activeSessionPrefix: ACTIVE_SESSION_PREFIX,
    boundWorkspaceId,
    activeSessionId,
    sessions,
    sessionStateById,
    pendingLocalUserMessageIdsBySession: _pendingLocalUserMessageIdsBySession
  })
  const {
    activeSessionStorageKey,
    setActiveSession,
    getOrCreateSessionState,
    sortSessions,
    upsertSessionMeta,
    updateSessionTouch,
    findPermissionSessionID
  } = sessionStateRepository

  const messageRepository = createMessageRepository({
    getOrCreateSessionState,
    messageSessionById,
    pendingLocalUserMessageIdsBySession: _pendingLocalUserMessageIdsBySession
  })
  const {
    upsertMessageInfo,
    upsertPart,
    appendPartDelta,
    removePart,
    removeMessage,
    appendSessionErrorMessage,
    pushLocalUserEcho,
    clearPendingLocalUserEchoes
  } = messageRepository

  const engineConfigBridge = createEngineConfigBridge({
    selectedEngine,
    selectedAgent,
    selectedModelId,
    availableModels,
    activeSessionId,
    getActiveAdapter,
    persistSelectedAgent: (id: string) => localStorage.setItem(AGENT_KEY, id),
    persistSelectedModel: (id: string) => localStorage.setItem(MODEL_KEY, id)
  })
  const { selectAgent, selectModel, patchAgentV3SessionConfig } = engineConfigBridge

  const { setAvailableAgents, loadRuntimeMeta, loadWorkspaceProfile } = createRuntimeMetaLoader({
    selectedEngine,
    availableModels,
    availableAgentOptions,
    selectedModelId,
    selectedAgent,
    globalError,
    rulesStatus,
    workspaceProfile,
    persistSelectedAgent: (id: string) => localStorage.setItem(AGENT_KEY, id),
    selectModel
  })

  const projectionService = createChatProjectionService({
    activeSessionId,
    sessionStateById,
    selectedAgent
  })
  const { activeSessionState, orderedMessages, chatRows, activeReasoningItemId, canSwitchPlanToBuild } = projectionService

  const transportStatus = computed<string>(() => {
    return activeSessionState.value?.transportStatus || ''
  })

  const sessionRunStatus = computed<string>(() => {
    return activeSessionState.value?.sessionRunStatus || ''
  })

  const isStreaming = computed<boolean>(() => {
    return activeSessionState.value?.isStreaming || false
  })
  const waitingReason = computed<'' | 'generating' | 'waiting_permission' | 'waiting_question' | 'stalled'>(() => {
    return (activeSessionState.value?.runWaitReason || '') as '' | 'generating' | 'waiting_permission' | 'waiting_question' | 'stalled'
  })
  const canInterrupt = computed<boolean>(() => {
    const id = String(activeSessionId.value || '').trim()
    if (!id) return false
    const state = activeSessionState.value
    if (!state) return false
    if (state.isStreaming) return true
    const status = String(state.sessionRunStatus || '').toLowerCase()
    return ['running', 'streaming', 'busy', 'retry', 'interrupting'].includes(status)
  })

  const lastError = computed<string | null>(() => {
    return activeSessionState.value?.lastError || globalError.value
  })
  const lastErrorRaw = computed<string | null>(() => {
    return activeSessionState.value?.lastErrorRaw || globalError.value
  })

  const permissionCards = computed<PermissionCard[]>(() => {
    const state = activeSessionState.value
    if (!state) return []
    return Object.values(state.permissionCardsById)
  })

  const questionCards = computed<QuestionCard[]>(() => {
    const state = activeSessionState.value
    if (!state) return []
    return Object.values(state.questionCardsById)
  })

  const activeSessionTodos = computed<SessionTodoItem[]>(() => {
    const sessionID = activeSessionId.value
    if (!sessionID) return []
    return sessionTodosById.value[sessionID] || []
  })

  const timelineItems = computed<TimelineItem[]>(() => {
    const built = buildTimelineItems({
      rows: chatRows.value,
      questions: questionCards.value,
      permissions: permissionCards.value,
      todos: activeSessionTodos.value,
      activeSessionId: String(activeSessionId.value || '')
    })
    if (built.permissionDebug && _lastPermissionTimelineDebug.value !== built.permissionDebug.signature) {
      _lastPermissionTimelineDebug.value = built.permissionDebug.signature
      logger.info('[codingAgentStore] permission_timeline_debug', built.permissionDebug.payload)
    }
    return built.items
  })

  const permissionStateService = createPermissionStateService({
    activeSessionId,
    getActiveAdapter,
    getOrCreateSessionState,
    findPermissionSessionID
  })
  const {
    upsertPermissionCard,
    clearPermissionsBySession,
    upsertQuestionCard,
    removeQuestionCard,
    clearQuestionsBySession,
    replyPermission: replyPermissionInternal
  } = permissionStateService
  const permissionReconcileCooldownMs = 1500
  const lastPermissionReconcileBySession: Record<string, number> = {}

  const permissionQuestionService = createPermissionQuestionService({
    getAdapter: getActiveAdapter,
    sessionStateById,
    messageSessionById,
    activeSessionId,
    upsertQuestionCard,
    clearQuestionsBySession,
    upsertPermissionCard,
    clearPermissionsBySession
  })
  const { reconcileQuestions, reconcilePermissions, replyQuestion, rejectQuestion } = permissionQuestionService

  let runtimeOrchestrator: ReturnType<typeof createRuntimeOrchestrator> | null = null
  const sessionCrud = createSessionCrud({
    getAdapter: getActiveAdapter,
    selectedEngine: selectedEngine as Ref<string>,
    selectedAgent,
    selectedModel: selectedModel as Ref<ModelOption | null>,
    sessions,
    activeSessionId,
    sessionStateById,
    sessionTodosById,
    messageSessionById,
    boundWorkspaceTarget,
    workspaceProfile,
    globalError,
    setActiveSession,
    sortSessions,
    upsertSessionMeta,
    getOrCreateSessionState,
    patchAgentV3SessionConfig,
    reconcileMessages: async (targetSessionID?: string) => {
      if (!runtimeOrchestrator) return
      await runtimeOrchestrator.reconcileMessages(targetSessionID)
    }
  })
  const {
    loadSessions,
    buildWorkspaceSystemPrompt,
    createSession: createSessionRaw,
    switchSession: switchSessionRaw,
    renameSession,
    deleteSession,
    tryRenameDefaultSessionAfterSend
  } = sessionCrud

  let applyEventImpl = (_evt: any) => {}
  runtimeOrchestrator = createRuntimeOrchestrator({
    selectedEngine,
    selectedAgent,
    selectedModel: selectedModel as Ref<ModelOption | null>,
    selectedModelId,
    availableModels,
    isReady,
    boundWorkspaceTarget,
    workspaceProfile,
    boundWorkspaceId,
    sessions,
    activeSessionId,
    sessionStateById,
    sessionTodosById,
    messageSessionById,
    globalError,
    eventUnsubscribe: _eventUnsubscribe,
    ensureReadyPromise: _ensureReadyPromise,
    pendingLocalUserMessageIdsBySession: _pendingLocalUserMessageIdsBySession,
    streamWatchdogs: _streamWatchdogs,
    getActiveAdapter,
    loadRuntimeMeta,
    loadWorkspaceProfile,
    setAvailableAgents,
    activeSessionStorageKey,
    setActiveSession,
    createSession,
    loadSessions,
    buildWorkspaceSystemPrompt,
    tryRenameDefaultSessionAfterSend,
    getOrCreateSessionState,
    reconcileQuestions,
    reconcilePermissions,
    updateSessionTouch,
    pushLocalUserEcho,
    clearPendingLocalUserEchoes,
    applyEvent: (evt: any) => applyEventImpl(evt)
  })

  const { applyEvent } = createEventDispatcher({
    selectedEngine,
    workspaceProfile,
    activeSessionId,
    sessions,
    sessionTodosById,
    messageSessionById,
    globalError,
    selectedAgent,
    selectedModelId,
    getOrCreateSessionState,
    findPermissionSessionID,
    normalizeSessionMeta,
    extractSessionErrorRawMessage,
    toReadableSessionError,
    upsertSessionMeta,
    updateSessionTouch,
    clearPendingLocalUserEchoes,
    upsertMessageInfo,
    upsertPart,
    appendPartDelta,
    removePart,
    removeMessage,
    upsertPermissionCard,
    upsertQuestionCard,
    removeQuestionCard,
    appendSessionErrorMessage,
    reconcileMessages: async (sessionID: string) => {
      if (!runtimeOrchestrator) return
      await runtimeOrchestrator.reconcileMessages(sessionID)
    }
  })
  applyEventImpl = applyEvent

  const ensureReady = runtimeOrchestrator.ensureReady
  const ensureReadyWithWorkspace = runtimeOrchestrator.ensureReadyWithWorkspace
  const reconcileMessages = runtimeOrchestrator.reconcileMessages
  const sendPromptParts = runtimeOrchestrator.sendPromptParts as (
    parts: PromptPart[],
    options?: WorkspaceResolveOptions
  ) => Promise<void>
  const sendText = runtimeOrchestrator.sendText as (text: string, options?: WorkspaceResolveOptions) => Promise<void>
  const interruptActiveRun = async () => runtimeOrchestrator?.interruptSession(activeSessionId.value)
  const dispose = runtimeOrchestrator.dispose

  async function createSession(title?: string, injectContext = true, options?: WorkspaceResolveOptions): Promise<string> {
    if (options) {
      await ensureReadyWithWorkspace(options)
    }
    return await createSessionRaw(title, injectContext)
  }

  async function switchSession(sessionID: string, options?: WorkspaceResolveOptions): Promise<void> {
    if (options) {
      await ensureReadyWithWorkspace(options)
    }
    await switchSessionRaw(sessionID)
  }

  async function createBuildSession(title: string, options?: WorkspaceResolveOptions): Promise<string> {
    await ensureReadyWithWorkspace(options)
    return await createSessionRaw(title, true)
  }

  async function sendTextToSession(sessionID: string, text: string, options?: WorkspaceResolveOptions): Promise<void> {
    const targetSessionID = String(sessionID || '').trim()
    if (!targetSessionID) {
      throw new Error('session id is required')
    }
    await ensureReadyWithWorkspace(options)
    if (activeSessionId.value !== targetSessionID) {
      await switchSession(targetSessionID, options)
    }
    await sendText(text, options)
  }

  async function sendPartsToSession(sessionID: string, parts: PromptPart[], options?: WorkspaceResolveOptions): Promise<void> {
    const targetSessionID = String(sessionID || '').trim()
    if (!targetSessionID) {
      throw new Error('session id is required')
    }
    await ensureReadyWithWorkspace(options)
    if (activeSessionId.value !== targetSessionID) {
      await switchSession(targetSessionID, options)
    }
    await sendPromptParts(parts, options)
  }

  function getSessionStateSnapshot(sessionID: string): BuildSessionStateSnapshot | null {
    const targetSessionID = String(sessionID || '').trim()
    if (!targetSessionID) return null
    const state = sessionStateById.value[targetSessionID]
    if (!state) return null
    return {
      sessionId: targetSessionID,
      isStreaming: Boolean(state.isStreaming),
      sessionRunStatus: String(state.sessionRunStatus || ''),
      transportStatus: String(state.transportStatus || ''),
      lastError: state.lastError || null,
      lastErrorRaw: state.lastErrorRaw || null
    }
  }

  async function replyPermission(permissionId: string, response: 'once' | 'always' | 'reject', remember?: boolean) {
    const ok = await replyPermissionInternal(permissionId, response, remember)
    if (!ok) return ok
    const sessionID = String(findPermissionSessionID(permissionId) || activeSessionId.value || '').trim()
    if (!sessionID || !runtimeOrchestrator) return ok
    const now = Date.now()
    const last = Number(lastPermissionReconcileBySession[sessionID] || 0)
    if (now - last < permissionReconcileCooldownMs) {
      return ok
    }
    lastPermissionReconcileBySession[sessionID] = now
    try {
      await runtimeOrchestrator.reconcileMessages(sessionID)
    } catch (err) {
      logger.warn('[codingAgentStore] reconcile after permission reply failed', {
        sessionID,
        permissionId,
        err
      })
    }
    return ok
  }

  function selectEngine(engineId: EngineId) {
    selectedEngine.value = engineId
    localStorage.setItem(ENGINE_KEY, engineId)
      dispose()
    runtimeOrchestrator?.clearRuntimeState()
    boundWorkspaceTarget.value = null
  }

  return {
    selectedEngine,
    selectedAgent,
    selectedModelId,
    engineOptions,
    availableAgents,
    availableModels,
    rulesStatus,
    workspaceProfile,
    boundWorkspaceTarget,
    sessions,
    activeSessionId,
    sessionId,
    isReady,
    isStreaming,
    waitingReason,
    canInterrupt,
    transportStatus,
    sessionRunStatus,
    lastError,
    lastErrorRaw,
    orderedMessages,
    ensureReady,
    ensureReadyWithWorkspace,
    loadSessions,
    createSession,
    createBuildSession,
    switchSession,
    renameSession,
    deleteSession,
    sendText,
    sendPromptParts,
    sendTextToSession,
    sendPartsToSession,
    getSessionStateSnapshot,
    interruptActiveRun,
    replyPermission,
    reconcileMessages,
    selectAgent,
    selectEngine,
    selectModel,
    dispose,
    chatRows,
    timelineItems,
    activeReasoningItemId,
    permissionCards,
    questionCards,
    activeSessionTodos,
    canSwitchPlanToBuild,
    replyQuestion,
    rejectQuestion
  }
})
