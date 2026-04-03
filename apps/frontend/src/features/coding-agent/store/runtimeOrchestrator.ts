import type { Ref } from 'vue'
import { logger } from '@/utils/logger'
import { ENGINE_OPENCODE, type EngineId } from '@/services/coding-agent/adapterRegistry'
import {
  engineSupportsWorkspacePayload,
  engineUsesRuntimeMeta,
  engineUsesWorkspaceSystemPrompt,
  getControlPlanePrefix
} from '@/services/coding-agent/engineCapabilities'
import type { CodingAgentPart, PromptPart } from '@/services/coding-agent/engineAdapter'
import type { ModelOption, SessionMeta, SessionState, SessionTodoItem, WorkspaceResolveOptions, WorkspaceTarget } from '@/features/coding-agent/store/types'
import { DEFAULT_SESSION_TITLE } from '@/features/coding-agent/store/sessionHelpers'
import { normalizeSessionTodos } from '@/features/coding-agent/store/toolDisplay'
import { createStreamWatchdog } from '@/features/coding-agent/store/streamWatchdog'
import { resolveWorkspaceTarget } from '@/features/coding-agent/store/workspaceTarget'
import { buildBackendUrl } from '@/utils/backendUrl'

export function createRuntimeOrchestrator(input: {
  selectedEngine: Ref<EngineId>
  selectedAgent: Ref<string>
  selectedModel: Ref<ModelOption | null>
  selectedModelId: Ref<string>
  availableModels: Ref<ModelOption[]>
  isReady: Ref<boolean>
  boundWorkspaceTarget: Ref<WorkspaceTarget | null>
  workspaceProfile: Ref<WorkspaceTarget | null>
  boundWorkspaceId: Ref<string>
  sessions: Ref<SessionMeta[]>
  activeSessionId: Ref<string>
  sessionStateById: Ref<Record<string, SessionState>>
  sessionTodosById: Ref<Record<string, SessionTodoItem[]>>
  messageSessionById: Ref<Record<string, string>>
  globalError: Ref<string | null>
  eventUnsubscribe: Ref<(() => void) | null>
  ensureReadyPromise: Ref<Promise<void> | null>
  pendingLocalUserMessageIdsBySession: Ref<Record<string, string[]>>
  streamWatchdogs: Ref<Record<string, number>>
  getActiveAdapter: () => any
  loadRuntimeMeta: (options?: WorkspaceResolveOptions) => Promise<void>
  loadWorkspaceProfile: (target: WorkspaceTarget) => Promise<void>
  setAvailableAgents: (rows: unknown[]) => void
  activeSessionStorageKey: (workspaceId: string) => string
  setActiveSession: (id: string) => void
  createSession: (title?: string, injectContext?: boolean) => Promise<string>
  loadSessions: () => Promise<void>
  buildWorkspaceSystemPrompt: (workspaceLabel: string) => string
  tryRenameDefaultSessionAfterSend: (targetSessionID: string, content: string) => void
  getOrCreateSessionState: (sessionID: string) => SessionState
  reconcileQuestions: (targetSessionID?: string) => Promise<void>
  reconcilePermissions: (targetSessionID?: string) => Promise<void>
  updateSessionTouch: (sessionID: string) => void
  pushLocalUserEcho: (sessionID: string, content: string) => void
  clearPendingLocalUserEchoes: (sessionID: string) => void
  applyEvent: (evt: any) => void
}) {
  const {
    selectedEngine,
    selectedAgent,
    selectedModel,
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
    eventUnsubscribe,
    ensureReadyPromise,
    pendingLocalUserMessageIdsBySession,
    streamWatchdogs,
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
    applyEvent
  } = input
  let transportInstanceSeq = 0
  let transportReconnectTimer: number | null = null
  let runSupervisorTimer: number | null = null
  const runStallTimeoutMs = 45000
  const runSupervisorIntervalMs = 5000
  const runRecoverMinIntervalMs = 15000
  const backendDiagMinIntervalMs = 20000
  const lastRunRecoverBySession: Record<string, number> = {}
  const lastBackendDiagBySession: Record<string, number> = {}
  const reconcileInFlightBySession: Record<string, Promise<void> | undefined> = {}
  let disposing = false

  const { clearStreamWatchdog, startStreamWatchdog, touchStreamWatchdog } = createStreamWatchdog({
    streamWatchdogs,
    getOrCreateSessionState,
    reconcileMessages,
    onStale: (sessionID, meta) => {
      void recoverSilentStream(sessionID, meta.staleDurationMs)
    }
  })

  function clearReconnectTimer() {
    if (transportReconnectTimer !== null) {
      window.clearTimeout(transportReconnectTimer)
      transportReconnectTimer = null
    }
  }

  function clearRunSupervisorTimer() {
    if (runSupervisorTimer !== null) {
      window.clearInterval(runSupervisorTimer)
      runSupervisorTimer = null
    }
  }

  function computeRunWaitReason(state: SessionState): SessionState['runWaitReason'] {
    if (!state.isStreaming) return ''
    const hasPendingPermission = Object.values(state.permissionCardsById).some((item) => item.status === 'pending')
    if (hasPendingPermission) return 'waiting_permission'
    const hasPendingQuestion = Object.values(state.questionCardsById).some((item) => item.status === 'pending')
    if (hasPendingQuestion) return 'waiting_question'
    return 'generating'
  }

  function summarizeToolSignals(state: SessionState) {
    let runningCount = 0
    let latestTool = ''
    let latestToolStatus = ''
    let latestOrder = -1
    for (const [messageID, parts] of Object.entries(state.partsByMessageId || {})) {
      for (const [partID, part] of Object.entries(parts || {})) {
        if (String((part as any)?.type || '').toLowerCase() !== 'tool') continue
        const status = String((part as any)?.state?.status || (part as any)?.status || '').toLowerCase()
        if (status === 'running') runningCount += 1
        const order = Number(state.partOrderByMessageId?.[messageID]?.[partID] ?? -1)
        if (order >= latestOrder) {
          latestOrder = order
          latestTool = String((part as any)?.tool || '')
          latestToolStatus = status
        }
      }
    }
    return { runningCount, latestTool, latestToolStatus }
  }

  function buildRunDiagnostics(sessionID: string, state: SessionState, context: string, extra?: Record<string, unknown>) {
    const toolSignals = summarizeToolSignals(state)
    return {
      sessionID,
      context,
      transport_status: String(state.transportStatus || '').toLowerCase(),
      session_run_status: String(state.sessionRunStatus || '').toLowerCase(),
      run_wait_reason: state.runWaitReason,
      last_non_heartbeat_event_at: state.lastNonHeartbeatEventAt,
      pending_permission_count: Object.values(state.permissionCardsById).filter((item) => item.status === 'pending').length,
      pending_question_count: Object.values(state.questionCardsById).filter((item) => item.status === 'pending').length,
      tool_running_count: toolSignals.runningCount,
      latest_tool: toolSignals.latestTool,
      latest_tool_status: toolSignals.latestToolStatus,
      message_count: Object.keys(state.messagesById || {}).length,
      ...extra
    }
  }

  async function fetchRuntimeDiagnostics(sessionID: string, reason: string) {
    if (!engineUsesRuntimeMeta(selectedEngine.value)) return
    const now = Date.now()
    const lastAt = Number(lastBackendDiagBySession[sessionID] || 0)
    if (now - lastAt < backendDiagMinIntervalMs) return
    lastBackendDiagBySession[sessionID] = now
    try {
      const resp = await fetch(buildBackendUrl(`${getControlPlanePrefix(selectedEngine.value)}/diagnostics`))
      const payload = await resp.json().catch(() => null)
      logger.warn('[codingAgentStore] runtime_diagnostics', {
        sessionID,
        reason,
        engine: selectedEngine.value,
        status: resp.status,
        diagnostics: payload?.data || null
      })
    } catch (err) {
      logger.warn('[codingAgentStore] runtime_diagnostics_fetch_failed', {
        sessionID,
        reason,
        engine: selectedEngine.value,
        err
      })
    }
  }

  function superviseStreamingSessions() {
    const now = Date.now()
    let hasStreaming = false
    for (const [sessionID, state] of Object.entries(sessionStateById.value)) {
      if (!state?.isStreaming) {
        state.runWaitReason = ''
        continue
      }
      hasStreaming = true
      const nextReason = computeRunWaitReason(state)
      if (nextReason === 'waiting_permission' || nextReason === 'waiting_question') {
        state.runWaitReason = nextReason
        continue
      }
      const lastBusinessAt = Number(state.lastNonHeartbeatEventAt || 0) || now
      const stalledDurationMs = Math.max(0, now - lastBusinessAt)
      if (stalledDurationMs < runStallTimeoutMs) {
        state.runWaitReason = 'generating'
        continue
      }
      state.runWaitReason = 'stalled'
      const lastRecoverAt = Number(lastRunRecoverBySession[sessionID] || 0)
      if (now - lastRecoverAt < runRecoverMinIntervalMs) {
        continue
      }
      lastRunRecoverBySession[sessionID] = now
      logger.warn(
        '[codingAgentStore] run progress stalled, trigger reconcile',
        buildRunDiagnostics(sessionID, state, 'run_stalled', {
          stale_duration_ms: stalledDurationMs,
          recover_reason: 'run_stalled'
        })
      )
      void fetchRuntimeDiagnostics(sessionID, 'run_stalled')
      const transportStatus = String(state.transportStatus || '').toLowerCase()
      const isTransportHealthy = transportStatus === 'streaming'
      const recoverTask = isTransportHealthy
        ? reconcileMessages(sessionID)
        : ensureEventSubscription({ force: true, reason: 'run_stalled' }).then(() => reconcileMessages(sessionID))
      void recoverTask.catch((err) => {
        logger.warn('[codingAgentStore] run stalled recover failed', { sessionID, err })
      })
    }

    if (!hasStreaming) {
      clearRunSupervisorTimer()
    }
  }

  function ensureRunSupervisorTimer() {
    if (runSupervisorTimer !== null || disposing) return
    runSupervisorTimer = window.setInterval(() => {
      if (disposing) {
        clearRunSupervisorTimer()
        return
      }
      superviseStreamingSessions()
    }, runSupervisorIntervalMs)
  }

  function scheduleResubscribe(reason: string) {
    if (disposing || transportReconnectTimer !== null) return
    transportReconnectTimer = window.setTimeout(() => {
      clearReconnectTimer()
      void ensureEventSubscription({ force: true, reason })
    }, 250)
  }

  async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, label: string): Promise<T> {
    let timer: number | null = null
    try {
      return await Promise.race([
        promise,
        new Promise<T>((_, reject) => {
          timer = window.setTimeout(() => {
            reject(new Error(`${label}: timeout_${timeoutMs}ms`))
          }, timeoutMs)
        })
      ])
    } finally {
      if (timer !== null) {
        window.clearTimeout(timer)
      }
    }
  }

  async function recoverSilentStream(sessionID: string, staleDurationMs: number) {
    const state = getOrCreateSessionState(sessionID)
    logger.warn(
      '[codingAgentStore] stream watchdog triggering recovery',
      buildRunDiagnostics(sessionID, state, 'watchdog_stale', {
        stale_duration_ms: staleDurationMs,
        recover_reason: 'watchdog_stale'
      })
    )
    void fetchRuntimeDiagnostics(sessionID, 'watchdog_stale')
    await ensureEventSubscription({ force: true, reason: 'watchdog_stale' })
    await reconcileMessages(sessionID).catch((err) => {
      logger.warn('[codingAgentStore] stream watchdog reconcile failed', { sessionID, err })
    })
  }

  function resolveSessionIDFromEvent(evt: any): string {
    const topLevel = String(evt?.sessionID || '').trim()
    if (topLevel) return topLevel
    const props = evt?.properties || {}
    const direct = String(props?.sessionID || props?.sessionId || '').trim()
    if (direct) return direct
    const infoSession = String(props?.info?.sessionID || '').trim()
    if (infoSession) return infoSession
    return String(activeSessionId.value || '').trim()
  }

  function isTerminalEventType(type: string): boolean {
    return ['session.idle', 'run.completed', 'run.failed', 'run.interrupted', 'session.error'].includes(type)
  }

  async function ensureEventSubscription(options?: { force?: boolean; reason?: string }) {
    if (disposing) return
    const force = Boolean(options?.force)
    const reason = String(options?.reason || '').trim() || 'ensure'
    if (force && eventUnsubscribe.value) {
      eventUnsubscribe.value()
      eventUnsubscribe.value = null
    }
    if (eventUnsubscribe.value) {
      return
    }
    const transportInstanceId = `${String(selectedEngine.value || 'engine')}-transport-${++transportInstanceSeq}`
    logger.info('[codingAgentStore] creating event subscription', {
      transport_instance_id: transportInstanceId,
      reason
    })
    eventUnsubscribe.value = await getActiveAdapter().subscribeEvents((evt: any) => {
      if (disposing) return
      clearReconnectTimer()
      const eventType = String(evt?.type || '')
      const sessionID = resolveSessionIDFromEvent(evt)

      if (sessionID && eventType !== 'stream.status' && eventType !== 'server.heartbeat') {
        touchStreamWatchdog(sessionID)
      }
      if (sessionID && isTerminalEventType(eventType)) {
        clearStreamWatchdog(sessionID)
      }
      if (eventType === 'stream.status') {
        const status = String(evt?.properties?.status || '').toLowerCase()
        if (status === 'reconnecting' || status === 'closed') {
          const latestState = sessionID ? getOrCreateSessionState(sessionID) : null
          logger.warn('[codingAgentStore] transport_status_signal', {
            sessionID,
            status,
            transport_instance_id: transportInstanceId,
            transport_error: String(evt?.properties?.error || ''),
            run_wait_reason: latestState?.runWaitReason || ''
          })
          if (sessionID) {
            void fetchRuntimeDiagnostics(sessionID, `transport_${status}`)
          }
        }
        if (status === 'closed') {
          scheduleResubscribe('stream_closed')
        }
      }

      applyEvent(evt)
      if (sessionID) {
        const latestState = getOrCreateSessionState(sessionID)
        if (latestState.isStreaming) {
          ensureRunSupervisorTimer()
        } else {
          latestState.runWaitReason = ''
        }
      }
    })
  }

  function readStablePartOrder(part: CodingAgentPart, existingOrder?: number): number {
    const rawOrder = (part as any)?.order ?? (part as any)?.index ?? (part as any)?.sequence
    const parsedOrder = Number(rawOrder)
    if (Number.isFinite(parsedOrder)) {
      return parsedOrder
    }
    if (existingOrder !== undefined) {
      return existingOrder
    }
    return -1
  }

  function replaceSessionMessageSnapshot(sessionID: string, rows: Array<{ info: any; parts: CodingAgentPart[] }>) {
    const state = getOrCreateSessionState(sessionID)
    const pendingLocalIds = new Set(pendingLocalUserMessageIdsBySession.value[sessionID] || [])
    const previousMessages = state.messagesById
    const previousParts = state.partsByMessageId
    const previousPartOrder = state.partOrderByMessageId
    const nextMessages: SessionState['messagesById'] = {}
    const nextParts: SessionState['partsByMessageId'] = {}
    const nextPartOrder: SessionState['partOrderByMessageId'] = {}
    let nextPartOrderSeq = 0

    const allocateFallbackOrder = () => {
      nextPartOrderSeq += 1
      return nextPartOrderSeq
    }

    for (const row of rows) {
      const messageID = String(row?.info?.id || '').trim()
      if (!messageID) continue
      nextMessages[messageID] = {
        ...(previousMessages[messageID] || {}),
        ...(row.info || {})
      }
      nextParts[messageID] = {}
      nextPartOrder[messageID] = {}
      for (const part of row.parts || []) {
        const partID = String(part?.id || '').trim()
        if (!partID) continue
        const stableOrder = readStablePartOrder(part, previousPartOrder[messageID]?.[partID])
        const finalOrder = stableOrder >= 0 ? stableOrder : allocateFallbackOrder()
        nextPartOrderSeq = Math.max(nextPartOrderSeq, finalOrder)
        nextPartOrder[messageID][partID] = finalOrder
        nextParts[messageID][partID] = {
          ...(previousParts[messageID]?.[partID] || {}),
          ...part
        }
      }
    }

    // Preserve optimistic user echoes until the server emits the canonical message.
    for (const pendingMessageID of pendingLocalIds) {
      if (nextMessages[pendingMessageID] || !previousMessages[pendingMessageID]) continue
      nextMessages[pendingMessageID] = previousMessages[pendingMessageID]
      nextParts[pendingMessageID] = { ...(previousParts[pendingMessageID] || {}) }
      nextPartOrder[pendingMessageID] = { ...(previousPartOrder[pendingMessageID] || {}) }
      for (const order of Object.values(nextPartOrder[pendingMessageID])) {
        nextPartOrderSeq = Math.max(nextPartOrderSeq, Number(order) || 0)
      }
    }

    state.messagesById = nextMessages
    state.partsByMessageId = nextParts
    state.partOrderByMessageId = nextPartOrder
    state.partOrderSeq = nextPartOrderSeq
  }

  function toUnixTime(value: unknown): number {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }
    if (typeof value === 'string') {
      const trimmed = value.trim()
      if (!trimmed) return 0
      const numeric = Number(trimmed)
      if (Number.isFinite(numeric)) {
        return numeric
      }
      const parsed = Date.parse(trimmed)
      if (Number.isFinite(parsed)) {
        return parsed
      }
    }
    return 0
  }

  function hasPendingInteractiveCards(state: SessionState): boolean {
    const hasPendingPermission = Object.values(state.permissionCardsById).some((item) => item.status === 'pending')
    if (hasPendingPermission) return true
    return Object.values(state.questionCardsById).some((item) => item.status === 'pending')
  }

  function getLatestAssistantMessage(state: SessionState): Record<string, any> | null {
    const assistants = Object.values(state.messagesById).filter((item) => String(item?.role || '').toLowerCase() === 'assistant')
    if (assistants.length === 0) {
      return null
    }
    assistants.sort((a, b) => {
      const ta = Math.max(toUnixTime((a as any)?.time?.created), toUnixTime((a as any)?.time?.completed))
      const tb = Math.max(toUnixTime((b as any)?.time?.created), toUnixTime((b as any)?.time?.completed))
      return ta - tb
    })
    return assistants[assistants.length - 1] as Record<string, any>
  }

  function hasRunningToolOrReasoning(state: SessionState): boolean {
    const allParts = Object.values(state.partsByMessageId).flatMap((partsMap) => Object.values(partsMap || {}))
    for (const part of allParts) {
      const partType = String(part?.type || '').toLowerCase()
      if (partType === 'tool') {
        const toolStatus = String((part as any)?.state?.status || '').toLowerCase()
        if (toolStatus === 'pending' || toolStatus === 'running') {
          return true
        }
        continue
      }
      if (partType === 'reasoning') {
        const reasoningEnd = (part as any)?.time?.end
        if (!reasoningEnd) {
          return true
        }
      }
    }
    return false
  }

  function maybeFinalizeStreamingFromSnapshot(sessionID: string) {
    const state = getOrCreateSessionState(sessionID)
    if (!state.isStreaming) return
    if (hasPendingInteractiveCards(state)) return
    const latestAssistant = getLatestAssistantMessage(state)
    if (!latestAssistant) return
    const completedAt = toUnixTime((latestAssistant as any)?.time?.completed)
    if (!completedAt) return
    if (hasRunningToolOrReasoning(state)) return

    state.isStreaming = false
    state.sessionRunStatus = 'idle'
    state.runWaitReason = ''
    clearStreamWatchdog(sessionID)
    logger.info('[codingAgentStore] inferred terminal state from snapshot reconcile', {
      sessionID,
      recover_reason: 'snapshot_terminal_inference',
      completed_at: completedAt
    })
  }

  async function reconcileMessages(targetSessionID?: string) {
    const sessionID = String(targetSessionID || activeSessionId.value || '').trim()
    if (!sessionID) return
    if (reconcileInFlightBySession[sessionID]) {
      await reconcileInFlightBySession[sessionID]
      return
    }
    const task = (async () => {
      const adapter = getActiveAdapter() as any
      const rows = (await withTimeout(
        adapter.listMessages(sessionID),
        12000,
        `reconcile listMessages ${sessionID}`
      )) as Array<{ info: any; parts: CodingAgentPart[] }>
      replaceSessionMessageSnapshot(sessionID, rows)
      if (typeof adapter.getSessionTodos === 'function') {
        const todos = await withTimeout(adapter.getSessionTodos(sessionID), 8000, `reconcile todos ${sessionID}`)
        sessionTodosById.value[sessionID] = Array.isArray(todos) ? normalizeSessionTodos(todos) : []
      }
      await withTimeout(reconcileQuestions(sessionID), 8000, `reconcile questions ${sessionID}`)
      await withTimeout(reconcilePermissions(sessionID), 8000, `reconcile permissions ${sessionID}`)
      maybeFinalizeStreamingFromSnapshot(sessionID)
    })()
    reconcileInFlightBySession[sessionID] = task
    try {
      await task
    } finally {
      delete reconcileInFlightBySession[sessionID]
    }
  }

  function clearRuntimeState() {
    sessions.value = []
    activeSessionId.value = ''
    sessionStateById.value = {}
    sessionTodosById.value = {}
    messageSessionById.value = {}
    boundWorkspaceTarget.value = null
    isReady.value = false
    globalError.value = null
  }

  async function ensureReady() {
    throw new Error('Coding 会话必须绑定 workspace target，请使用 ensureReadyWithWorkspace')
  }

  async function ensureReadyWithWorkspace(options?: WorkspaceResolveOptions) {
    const workspaceTarget = resolveWorkspaceTarget(options)
    if (!workspaceTarget) {
      throw new Error('请提供 workspace target')
    }
    const workspaceId = workspaceTarget.id

    if (isReady.value && boundWorkspaceId.value === workspaceId && activeSessionId.value) {
      await ensureEventSubscription({ reason: 'ready_short_circuit' })
      return
    }

    if (ensureReadyPromise.value) {
      await ensureReadyPromise.value
      if (isReady.value && boundWorkspaceId.value === workspaceId && activeSessionId.value) {
        await ensureEventSubscription({ reason: 'ready_after_inflight' })
        return
      }
    }

    if (isReady.value && boundWorkspaceId.value && boundWorkspaceId.value !== workspaceId) {
      dispose()
      clearRuntimeState()
    }

    ensureReadyPromise.value = (async () => {
      try {
        globalError.value = null
        await loadWorkspaceProfile(workspaceTarget)
        if (workspaceTarget.defaultAgent && selectedAgent.value !== workspaceTarget.defaultAgent) {
          selectedAgent.value = workspaceTarget.defaultAgent
        }
        if (engineUsesRuntimeMeta(selectedEngine.value)) {
          await loadRuntimeMeta({ workspaceTarget, forceRestart: options?.forceRestart })
        } else {
          const adapter = getActiveAdapter()
          const [agentsResp, modelsResp] = await Promise.allSettled([
            adapter.listAgents ? adapter.listAgents() : Promise.resolve([]),
            adapter.listModels ? adapter.listModels() : Promise.resolve([])
          ])
          const nextAgents = agentsResp.status === 'fulfilled' ? agentsResp.value : []
          setAvailableAgents(nextAgents)
          if (workspaceTarget.defaultAgent) {
            const hasDefaultAgent = nextAgents.some((item: any) => String(item?.id || '') === workspaceTarget.defaultAgent)
            if (hasDefaultAgent) {
              selectedAgent.value = workspaceTarget.defaultAgent
            }
          }

          const nextModels = modelsResp.status === 'fulfilled' ? modelsResp.value : []
          availableModels.value = Array.isArray(nextModels) ? nextModels : []
          if (availableModels.value.length === 0) {
            selectedModelId.value = ''
            localStorage.setItem('codingAgent:selectedModel', '')
          } else if (!availableModels.value.some((item) => item.id === selectedModelId.value)) {
            selectedModelId.value = availableModels.value[0].id
            localStorage.setItem('codingAgent:selectedModel', selectedModelId.value)
          }
        }
        boundWorkspaceTarget.value = workspaceProfile.value
          ? { ...workspaceTarget, ...workspaceProfile.value }
          : workspaceTarget

        await ensureEventSubscription({ reason: 'ensure_ready' })

        await loadSessions()
        await reconcileQuestions()
        const preferredSession = localStorage.getItem(activeSessionStorageKey(workspaceId)) || ''
        const fallbackSession =
          workspaceTarget.sessionStrategy === 'single'
            ? ''
            : sessions.value[0]?.id || ''

        if (preferredSession && sessions.value.some((item) => item.id === preferredSession)) {
          setActiveSession(preferredSession)
        } else if (fallbackSession) {
          setActiveSession(fallbackSession)
        } else {
          await createSession(DEFAULT_SESSION_TITLE, true)
        }

        if (activeSessionId.value) {
          await reconcileMessages(activeSessionId.value)
        }

        isReady.value = true
      } catch (err) {
        isReady.value = false
        const message = err instanceof Error ? err.message : String(err)
        globalError.value = message
        logger.error('[codingAgentStore] ensureReadyWithWorkspace failed', err)
        throw err
      } finally {
        ensureReadyPromise.value = null
      }
    })()

    await ensureReadyPromise.value
  }

  function summarizeLocalEchoFromParts(parts: PromptPart[]): string {
    const text = parts
      .filter((part): part is Extract<PromptPart, { type: 'text' }> => part.type === 'text')
      .map((part) => String(part.text || ''))
      .join('\n')
      .trim()
    const imageCount = parts.filter((part) => {
      if (part.type !== 'file') return false
      return String(part.mime || '').toLowerCase().startsWith('image/')
    }).length
    if (text && imageCount > 0) {
      return `${text}\n[已附加 ${imageCount} 张图片]`
    }
    if (text) return text
    if (imageCount > 0) {
      return `[已发送 ${imageCount} 张图片]`
    }
    return ''
  }

  async function sendPromptParts(parts: PromptPart[], options?: WorkspaceResolveOptions) {
    const normalizedParts = (Array.isArray(parts) ? parts : [])
      .map((part) => {
        if (!part || typeof part !== 'object') return null
        if (part.type === 'text') {
          const text = String(part.text || '').trim()
          if (!text) return null
          return { type: 'text', text } as const
        }
        if (part.type === 'file') {
          const mime = String(part.mime || '').trim()
          const url = String(part.url || '').trim()
          const filename = String(part.filename || '').trim()
          if (!mime || !url) return null
          return {
            type: 'file',
            mime,
            url,
            ...(filename ? { filename } : {})
          } as const
        }
        return null
      })
      .filter((part): part is PromptPart => Boolean(part))
    if (normalizedParts.length === 0) return

    const hasFileParts = normalizedParts.some((part) => part.type === 'file')
    if (hasFileParts && selectedEngine.value !== ENGINE_OPENCODE) {
      throw new Error('当前引擎暂不支持图片输入，请切换 OpenCode。')
    }

    const workspaceTarget = resolveWorkspaceTarget(options)
    if (!workspaceTarget) {
      throw new Error('发送消息前必须绑定 workspace target')
    }

    await ensureReadyWithWorkspace({ workspaceTarget, forceRestart: options?.forceRestart })
    const targetSessionID = activeSessionId.value
    if (!targetSessionID) {
      throw new Error('session not ready')
    }

    const state = getOrCreateSessionState(targetSessionID)
    state.lastError = null
    state.lastErrorRaw = null
    state.isStreaming = true
    state.sessionRunStatus = 'running'
    state.runWaitReason = 'generating'
    state.lastNonHeartbeatEventAt = Date.now()
    startStreamWatchdog(targetSessionID)
    ensureRunSupervisorTimer()

    const model = selectedModel.value
    const systemPrompt = engineUsesWorkspaceSystemPrompt(selectedEngine.value)
      ? buildWorkspaceSystemPrompt(workspaceTarget.displayName)
      : undefined
    const primaryText = normalizedParts
      .filter((part): part is Extract<PromptPart, { type: 'text' }> => part.type === 'text')
      .map((part) => String(part.text || ''))
      .find((value) => value.trim().length > 0)
    const echoText = summarizeLocalEchoFromParts(normalizedParts)
    const payload = {
      parts: normalizedParts,
      agent: selectedAgent.value,
      ...(engineSupportsWorkspacePayload(selectedEngine.value) && workspaceTarget.pluginId
        ? { plugin_id: workspaceTarget.pluginId }
        : {}),
      ...(engineSupportsWorkspacePayload(selectedEngine.value) && workspaceTarget.projectId
        ? { project_id: workspaceTarget.projectId }
        : {}),
      ...(engineSupportsWorkspacePayload(selectedEngine.value) && workspaceTarget.workspacePath
        ? { workspace_path: workspaceTarget.workspacePath }
        : {}),
      ...(engineSupportsWorkspacePayload(selectedEngine.value) ? { workspace_kind: workspaceTarget.kind } : {}),
      ...(systemPrompt ? { system: systemPrompt } : {}),
      model: model
        ? {
            providerID: model.providerID,
            modelID: model.modelID
          }
        : undefined
    }

    try {
      if (echoText) {
        pushLocalUserEcho(targetSessionID, echoText)
      }
      await getActiveAdapter().promptAsync(targetSessionID, payload)
      updateSessionTouch(targetSessionID)
      if (primaryText) {
        tryRenameDefaultSessionAfterSend(targetSessionID, primaryText)
      }
    } catch (err) {
      clearPendingLocalUserEchoes(targetSessionID)
      const message = err instanceof Error ? err.message : String(err)
      state.lastError = message
      state.lastErrorRaw = message
      state.isStreaming = false
      state.sessionRunStatus = 'error'
      state.runWaitReason = ''
      throw err
    }
  }

  async function sendText(text: string, options?: WorkspaceResolveOptions) {
    const content = text.trim()
    if (!content) return
    await sendPromptParts([{ type: 'text', text: content }], options)
  }

  async function interruptSession(targetSessionID?: string): Promise<boolean> {
    const sessionID = String(targetSessionID || activeSessionId.value || '').trim()
    if (!sessionID) return false
    const state = getOrCreateSessionState(sessionID)
    state.lastError = null
    state.lastErrorRaw = null
    state.sessionRunStatus = 'interrupting'
    try {
      const ok = await getActiveAdapter().interruptSession(sessionID)
      if (!ok) {
        state.lastError = '当前会话不存在或已结束，无法中断。'
        state.lastErrorRaw = state.lastError
        return false
      }
      clearStreamWatchdog(sessionID)
      state.isStreaming = false
      state.sessionRunStatus = 'interrupted'
      state.runWaitReason = ''
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      state.lastError = message
      state.lastErrorRaw = message
      logger.warn('[codingAgentStore] interrupt session failed', { sessionID, err })
      return false
    }
  }

  function dispose() {
    disposing = true
    clearReconnectTimer()
    clearRunSupervisorTimer()
    if (eventUnsubscribe.value) {
      eventUnsubscribe.value()
      eventUnsubscribe.value = null
    }
    pendingLocalUserMessageIdsBySession.value = {}
    for (const sessionID of Object.keys(streamWatchdogs.value)) {
      clearStreamWatchdog(sessionID)
    }
    for (const sessionID of Object.keys(sessionStateById.value)) {
      const state = getOrCreateSessionState(sessionID)
      state.isStreaming = false
      state.transportStatus = 'closed'
      state.runWaitReason = ''
    }
    disposing = false
  }

  return {
    ensureReady,
    ensureReadyWithWorkspace,
    reconcileMessages,
    sendPromptParts,
    sendText,
    interruptSession,
    dispose,
    clearRuntimeState,
    clearStreamWatchdog,
    startStreamWatchdog,
    touchStreamWatchdog
  }
}
