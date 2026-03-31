import type { Ref } from 'vue'
import { logger } from '@/utils/logger'
import { ENGINE_OPENCODE } from '@/services/coding-agent/adapterRegistry'
import type {
  CodingAgentEvent,
  CodingAgentMessageInfo,
  CodingAgentPart,
  CodingAgentQuestionRequest,
  CodingAgentSession
} from '@/services/coding-agent/engineAdapter'
import type { PermissionCard, QuestionCard, SessionState, SessionTodoItem, SessionMeta, WorkspaceTarget } from '@/features/coding-agent/store/types'
import { normalizePermissionPayload } from '@/features/coding-agent/store/permissionNormalizer'
import { normalizeSessionTodos, parseToolRawArgumentsSafe } from '@/features/coding-agent/store/toolDisplay'

interface EventDispatcherInput {
  selectedEngine: Ref<string>
  workspaceProfile: Ref<WorkspaceTarget | null>
  activeSessionId: Ref<string>
  sessions: Ref<SessionMeta[]>
  sessionTodosById: Ref<Record<string, SessionTodoItem[]>>
  messageSessionById: Ref<Record<string, string>>
  globalError: Ref<string | null>
  selectedAgent: Ref<string>
  selectedModelId: Ref<string>
  getOrCreateSessionState: (sessionID: string) => SessionState
  findPermissionSessionID: (permissionID: string) => string
  normalizeSessionMeta: (raw: CodingAgentSession) => SessionMeta
  extractSessionErrorRawMessage: (payload: unknown) => string
  toReadableSessionError: (raw: string) => string
  upsertSessionMeta: (meta: SessionMeta) => void
  updateSessionTouch: (sessionID: string) => void
  clearPendingLocalUserEchoes: (sessionID: string) => void
  upsertMessageInfo: (sessionID: string, info: CodingAgentMessageInfo) => void
  upsertPart: (sessionID: string, part: CodingAgentPart & { messageID?: string }) => void
  appendPartDelta: (
    sessionID: string,
    messageID: string,
    partID: string,
    field: string,
    delta: string,
    partType?: string
  ) => void
  removePart: (sessionID: string, messageID: string, partID: string) => void
  removeMessage: (sessionID: string, messageID: string) => void
  upsertPermissionCard: (sessionID: string, card: Partial<PermissionCard> & { id: string }) => void
  upsertQuestionCard: (sessionID: string, card: QuestionCard) => void
  removeQuestionCard: (sessionID: string, requestID: string) => void
  appendSessionErrorMessage: (sessionID: string, text: string, rawMessage: string) => void
  reconcileMessages: (sessionID: string) => Promise<void>
}

export function createEventDispatcher(input: EventDispatcherInput) {
  const {
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
    reconcileMessages
  } = input

  function normalizeDirectory(value: unknown): string {
    const normalized = String(value || '')
      .trim()
      .replace(/\\/g, '/')
    if (!normalized) return ''
    if (normalized === '/') return normalized
    return normalized.replace(/\/+$/, '')
  }

  function shouldAcceptSessionEvent(source: CodingAgentSession): boolean {
    if (selectedEngine.value !== ENGINE_OPENCODE) return true
    const workspaceDirectory = normalizeDirectory(workspaceProfile.value?.workspacePath)
    if (!workspaceDirectory) return true
    const sessionId = String(source?.id || '').trim()
    if (sessionId && sessions.value.some((item) => item.id === sessionId)) {
      return true
    }
    const sessionDirectory = normalizeDirectory(
      source?.directory || (source as { cwd?: unknown }).cwd
    )
    if (!sessionDirectory) {
      return false
    }
    return sessionDirectory === workspaceDirectory
  }

  function resolveSessionIDForEvent(evt: CodingAgentEvent): string {
    const topLevel = String((evt as any)?.sessionID || '').trim()
    if (topLevel) return topLevel
    const props = evt.properties || {}
    const direct = String(props.sessionID || props.sessionId || '').trim()
    if (direct) return direct

    const infoSession = String((props.info as any)?.sessionID || '').trim()
    if (infoSession) return infoSession

    const part = props.part as (CodingAgentPart & { sessionID?: string; sessionId?: string }) | undefined
    const partSession = String(part?.sessionID || part?.sessionId || '').trim()
    if (partSession) return partSession

    const messageID = String(props.messageID || (props.info as any)?.id || part?.messageID || '').trim()
    if (messageID && messageSessionById.value[messageID]) {
      return messageSessionById.value[messageID]
    }

    const source = props.permission || props.request || props
    const permissionSession = String(source?.sessionID || '').trim()
    if (permissionSession) return permissionSession
    const permissionID = String(source?.id || source?.requestID || source?.permissionID || '').trim()
    if (permissionID) {
      const mappedSessionID = findPermissionSessionID(permissionID)
      if (mappedSessionID) return mappedSessionID
    }

    const question = props.question || props.request || props
    const questionSession = String(question?.sessionID || '').trim()
    if (questionSession) return questionSession

    return activeSessionId.value
  }

  function applyEvent(evt: CodingAgentEvent) {
    const type = evt.type
    const props = evt.properties || {}
    const sessionID = resolveSessionIDForEvent(evt)
    const state = sessionID ? getOrCreateSessionState(sessionID) : null
    const eventID = Number((evt as any)?.eventID)
    if (state && Number.isFinite(eventID)) {
      const key = String(eventID)
      if (state.seenEventIDs[key]) {
        return
      }
      state.seenEventIDs[key] = true
    }
    if (state && type !== 'server.heartbeat') {
      state.lastNonHeartbeatEventAt = Date.now()
    }

    const pendingPermissionCount = state
      ? Object.values(state.permissionCardsById).filter((item) => item.status === 'pending').length
      : 0
    const pendingQuestionCount = state
      ? Object.values(state.questionCardsById).filter((item) => item.status === 'pending').length
      : 0

    const refreshRunWaitReason = (inputState: SessionState | null) => {
      if (!inputState) return
      if (!inputState.isStreaming) {
        inputState.runWaitReason = ''
        return
      }
      const pendingPermission = Object.values(inputState.permissionCardsById).some((item) => item.status === 'pending')
      if (pendingPermission) {
        inputState.runWaitReason = 'waiting_permission'
        return
      }
      const pendingQuestion = Object.values(inputState.questionCardsById).some((item) => item.status === 'pending')
      if (pendingQuestion) {
        inputState.runWaitReason = 'waiting_question'
        return
      }
      if (inputState.runWaitReason !== 'stalled') {
        inputState.runWaitReason = 'generating'
      }
    }

    if (type === 'stream.status') {
      const status = String(props?.status || '').toLowerCase()
      if (state) {
        state.transportStatus = status
        if (status === 'streaming') {
          state.transportError = null
        } else if (status === 'reconnecting' || status === 'closed') {
          state.transportError = String(props?.error || '').trim() || null
        }
        refreshRunWaitReason(state)
      }
      return
    }

    if (type === 'server.connected') {
      const target = String(activeSessionId.value || '').trim()
      if (target) {
        void reconcileMessages(target)
          .then(() => {
            const latest = getOrCreateSessionState(target)
            latest.transportStatus = 'streaming'
            latest.transportError = null
          })
          .catch((err) => {
            logger.warn('[codingAgentStore] reconcile on server.connected failed', { sessionID: target, err })
          })
      }
      return
    }

    if (type === 'session.created' || type === 'session.updated') {
      const source = (props?.session || props?.data || props) as CodingAgentSession | undefined
      if (source && typeof source === 'object' && String((source as any).id || '').trim()) {
        if (!shouldAcceptSessionEvent(source)) {
          return
        }
        upsertSessionMeta(normalizeSessionMeta(source))
      } else if (sessionID) {
        updateSessionTouch(sessionID)
      }
      return
    }

    if (type === 'session.status') {
      const rawStatus = props?.status
      const status =
        typeof rawStatus === 'string'
          ? rawStatus.toLowerCase()
          : String(rawStatus?.type || props?.legacy_status || '').toLowerCase()
      if (state) {
        state.sessionRunStatus = status
        state.isStreaming = ['running', 'streaming', 'busy', 'retry'].includes(status)
        refreshRunWaitReason(state)
        logger.debug('[codingAgentStore] run_status_updated', {
          sessionID,
          status,
          run_wait_reason: state.runWaitReason,
          pending_permission_count: pendingPermissionCount,
          pending_question_count: pendingQuestionCount,
          last_non_heartbeat_event_at: state.lastNonHeartbeatEventAt
        })
      }
      return
    }
    if (type === 'session.idle') {
      if (state) {
        state.sessionRunStatus = 'idle'
        state.isStreaming = false
        state.runWaitReason = ''
      }
      return
    }
    if (type === 'session.error') {
      const rawMessage = extractSessionErrorRawMessage(props) || 'session error'
      const message = toReadableSessionError(rawMessage)
      if (state) {
        state.sessionRunStatus = 'error'
        state.isStreaming = false
        state.runWaitReason = ''
        state.lastError = message
        state.lastErrorRaw = rawMessage
        appendSessionErrorMessage(sessionID, message, rawMessage)
      } else {
        globalError.value = message
      }
      logger.error('[codingAgentStore] session.error', {
        sessionId: sessionID,
        selectedAgent: selectedAgent.value,
        selectedModelId: selectedModelId.value,
        message,
        rawMessage,
        payload: props
      })
      return
    }

    if (type === 'message.updated') {
      const info = props?.info as CodingAgentMessageInfo
      if (sessionID && info) {
        if (String(info.role || '').toLowerCase() === 'user') {
          clearPendingLocalUserEchoes(sessionID)
        }
        upsertMessageInfo(sessionID, info)
        updateSessionTouch(sessionID)
      }
      return
    }
    if (type === 'message.part.updated') {
      const part = props?.part as CodingAgentPart & { messageID?: string }
      if (sessionID && part) {
        upsertPart(sessionID, part)
        updateSessionTouch(sessionID)
      }
      return
    }
    if (type === 'message.part.delta') {
      const part = props?.part as (CodingAgentPart & { messageID?: string }) | undefined
      if (sessionID && part) {
        upsertPart(sessionID, part)
        updateSessionTouch(sessionID)
        return
      }
      const messageID = String(props?.messageID || '')
      const partID = String(props?.partID || props?.id || '')
      const partType = String(props?.partType || '')
      const field = String(props?.field || 'text')
      const delta = props?.delta
      if (sessionID && messageID && partID && typeof delta === 'string' && delta.length > 0) {
        appendPartDelta(sessionID, messageID, partID, field, delta, partType || undefined)
        updateSessionTouch(sessionID)
      }
      return
    }
    if (type === 'message.part.removed') {
      const messageID = String(props?.messageID || '')
      const partID = String(props?.partID || '')
      if (sessionID && messageID && partID) {
        removePart(sessionID, messageID, partID)
      }
      return
    }
    if (type === 'todo.updated') {
      if (!sessionID) return
      const todos = Array.isArray(props?.todos) ? props.todos : []
      sessionTodosById.value[sessionID] = normalizeSessionTodos(todos)
      return
    }
    if (type === 'run.progress') {
      if (sessionID) {
        updateSessionTouch(sessionID)
      }
      return
    }
    if (type === 'run.interrupted') {
      if (state) {
        state.sessionRunStatus = 'interrupted'
        state.isStreaming = false
        state.runWaitReason = ''
      }
      return
    }
    if (type === 'run.completed' || type === 'run.failed') {
      if (state) {
        state.sessionRunStatus = type === 'run.completed' ? 'completed' : 'failed'
        state.isStreaming = false
        state.runWaitReason = ''
      }
      return
    }
    if (type === 'tool.input.start') {
      if (!sessionID) return
      const messageID = String(props?.messageID || '')
      const partID = String(props?.partID || '')
      if (!messageID || !partID) return
      upsertPart(sessionID, {
        id: partID,
        type: 'tool',
        messageID,
        tool: String(props?.toolName || props?.tool || 'tool'),
        callID: String(props?.callID || ''),
        state: {
          status: 'pending',
          input: {},
          rawArguments: ''
        }
      } as CodingAgentPart & { messageID: string })
      updateSessionTouch(sessionID)
      return
    }
    if (type === 'tool.input.delta') {
      if (!sessionID) return
      const messageID = String(props?.messageID || '')
      const partID = String(props?.partID || '')
      if (!messageID || !partID) return
      const targetState = getOrCreateSessionState(sessionID)
      const parts = targetState.partsByMessageId[messageID] || {}
      const existing = (parts[partID] || {}) as Record<string, unknown>
      const currentState = ((existing.state as Record<string, unknown>) || {}) as Record<string, unknown>
      const toolName = String(props?.toolName || props?.toolNamePreview || existing.tool || 'tool')
      const rawArguments = String(props?.rawArguments || props?.rawArgumentsPreview || '')
      upsertPart(sessionID, {
        id: partID,
        type: 'tool',
        messageID,
        tool: toolName,
        callID: String(props?.callID || existing.callID || ''),
        state: {
          ...currentState,
          status: 'pending',
          rawArguments,
          inputPreview: rawArguments,
          input: parseToolRawArgumentsSafe(rawArguments)
        }
      } as CodingAgentPart & { messageID: string })
      updateSessionTouch(sessionID)
      return
    }
    if (type === 'tool.input.end') {
      if (!sessionID) return
      const messageID = String(props?.messageID || '')
      const partID = String(props?.partID || '')
      if (!messageID || !partID) return
      const targetState = getOrCreateSessionState(sessionID)
      const parts = targetState.partsByMessageId[messageID] || {}
      const existing = (parts[partID] || {}) as Record<string, unknown>
      const currentState = ((existing.state as Record<string, unknown>) || {}) as Record<string, unknown>
      const rawArguments = String(props?.rawArguments || currentState.rawArguments || '')
      upsertPart(sessionID, {
        id: partID,
        type: 'tool',
        messageID,
        tool: String(props?.toolName || existing.tool || 'tool'),
        callID: String(props?.callID || existing.callID || ''),
        state: {
          ...currentState,
          status: 'running',
          rawArguments,
          inputPreview: rawArguments,
          input: parseToolRawArgumentsSafe(rawArguments)
        }
      } as CodingAgentPart & { messageID: string })
      updateSessionTouch(sessionID)
      return
    }
    if (type === 'message.removed') {
      const messageID = String(props?.messageID || '')
      if (sessionID && messageID) {
        removeMessage(sessionID, messageID)
      }
      return
    }
    if (type === 'permission.asked' || type === 'permission.updated' || type === 'permission.replied') {
      const card = normalizePermissionPayload(props, type)
      if (sessionID && card) {
        logger.info('[codingAgentStore] permission_event_received', {
          eventType: type,
          sessionID,
          permissionID: card.id,
          messageID: card.messageID,
          callID: card.callID,
          tool: card.tool,
          status: card.status
        })
        upsertPermissionCard(sessionID, {
          ...card,
          sessionID: card.sessionID || sessionID
        })
        const latest = getOrCreateSessionState(sessionID)
        refreshRunWaitReason(latest)
        logger.info('[codingAgentStore] run_waiting_signal', {
          sessionID,
          run_wait_reason: latest.runWaitReason,
          pending_permission_count: Object.values(latest.permissionCardsById).filter((item) => item.status === 'pending')
            .length,
          pending_question_count: Object.values(latest.questionCardsById).filter((item) => item.status === 'pending')
            .length,
          last_non_heartbeat_event_at: latest.lastNonHeartbeatEventAt
        })
      }
      return
    }
    if (type === 'question.asked') {
      const source = props as CodingAgentQuestionRequest
      const requestID = String(source?.id || '').trim()
      if (!sessionID || !requestID) return
      upsertQuestionCard(sessionID, {
        id: requestID,
        sessionID,
        messageID: String(source?.tool?.messageID || ''),
        questions: Array.isArray(source?.questions) ? source.questions : [],
        status: 'pending',
        toolCallID: String(source?.tool?.callID || '')
      })
      const latest = getOrCreateSessionState(sessionID)
      refreshRunWaitReason(latest)
      return
    }
    if (type === 'question.replied' || type === 'question.rejected') {
      const requestID = String((props as any)?.requestID || '').trim()
      if (!sessionID || !requestID) return
      removeQuestionCard(sessionID, requestID)
    }
  }

  return {
    applyEvent,
    resolveSessionIDForEvent
  }
}
