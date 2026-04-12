import type { Ref } from 'vue'
import { logger } from '@/utils/logger'
import { ENGINE_OPENCODE, type EngineId } from '@/services/coding-agent/adapterRegistry'
import {
  engineSupportsWorkspacePayload,
  engineUsesRuntimeMeta,
  engineUsesWorkspaceSystemPrompt
} from '@/services/coding-agent/engineCapabilities'
import type { CodingAgentEvent, EngineAdapter, PromptPart } from '@/services/coding-agent/engineAdapter'
import type { ModelOption, SessionMeta, SessionState, SessionTodoItem, WorkspaceResolveOptions, WorkspaceTarget } from '@/features/coding-agent/store/types'
import { DEFAULT_SESSION_TITLE } from '@/features/coding-agent/store/sessionHelpers'
import { normalizeSessionTodos } from '@/features/coding-agent/store/toolDisplay'
import { createStreamWatchdog } from '@/features/coding-agent/store/streamWatchdog'
import { resolveWorkspaceTarget } from '@/features/coding-agent/store/workspaceTarget'
import {
  buildRunDiagnostics,
  fetchRuntimeDiagnostics,
  RUN_SUPERVISOR_INTERVAL_MS,
  superviseStreamingSessionsLoop
} from '@/features/coding-agent/store/runtimeRunSupervisor'
import { maybeFinalizeStreamingFromSnapshot, replaceSessionMessageSnapshot } from '@/features/coding-agent/store/runtimeReconcile'
import { createEventSubscriptionLifecycle, withTimeout } from '@/features/coding-agent/store/runtimeEventTransport'

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
  getActiveAdapter: () => EngineAdapter
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
  applyEvent: (evt: CodingAgentEvent) => void
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

  const transportInstanceSeq = { current: 0 }
  let runSupervisorTimer: number | null = null
  const lastRunRecoverBySession: Record<string, number> = {}
  const lastBackendDiagBySession: Record<string, number> = {}
  const reconcileInFlightBySession: Record<string, Promise<void> | undefined> = {}
  let disposing = false

  const fetchDiag = (sessionID: string, reason: string) =>
    fetchRuntimeDiagnostics(sessionID, reason, { selectedEngine, lastBackendDiagBySession })

  function clearRunSupervisorTimer() {
    if (runSupervisorTimer !== null) {
      window.clearInterval(runSupervisorTimer)
      runSupervisorTimer = null
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
    }, RUN_SUPERVISOR_INTERVAL_MS)
  }

  async function reconcileMessages(targetSessionID?: string) {
    const sessionID = String(targetSessionID || activeSessionId.value || '').trim()
    if (!sessionID) return
    if (reconcileInFlightBySession[sessionID]) {
      await reconcileInFlightBySession[sessionID]
      return
    }
    const task = (async () => {
      const adapter = getActiveAdapter()
      const rows = await withTimeout(adapter.listMessages(sessionID), 12000, `reconcile listMessages ${sessionID}`)
      replaceSessionMessageSnapshot(sessionID, rows, {
        getOrCreateSessionState,
        pendingLocalUserMessageIdsBySession
      })
      if (typeof adapter.getSessionTodos === 'function') {
        const todos = await withTimeout(adapter.getSessionTodos(sessionID), 8000, `reconcile todos ${sessionID}`)
        sessionTodosById.value[sessionID] = Array.isArray(todos) ? normalizeSessionTodos(todos) : []
      }
      await withTimeout(reconcileQuestions(sessionID), 8000, `reconcile questions ${sessionID}`)
      await withTimeout(reconcilePermissions(sessionID), 8000, `reconcile permissions ${sessionID}`)
      maybeFinalizeStreamingFromSnapshot(sessionID, {
        getOrCreateSessionState,
        clearStreamWatchdog
      })
    })()
    reconcileInFlightBySession[sessionID] = task
    try {
      await task
    } finally {
      delete reconcileInFlightBySession[sessionID]
    }
  }

  const eventTransport = {
    ensureEventSubscription: async (_options?: { force?: boolean; reason?: string }) => {},
    clearReconnectTimer: () => {}
  }

  function superviseStreamingSessions() {
    superviseStreamingSessionsLoop({
      sessionStateById,
      getOrCreateSessionState,
      reconcileMessages,
      ensureEventSubscription: (options) => eventTransport.ensureEventSubscription(options),
      fetchRuntimeDiagnostics: fetchDiag,
      lastRunRecoverBySession,
      clearRunSupervisorTimer
    })
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
    void fetchDiag(sessionID, 'watchdog_stale')
    await eventTransport.ensureEventSubscription({ force: true, reason: 'watchdog_stale' })
    await reconcileMessages(sessionID).catch((err) => {
      logger.warn('[codingAgentStore] stream watchdog reconcile failed', { sessionID, err })
    })
  }

  const { clearStreamWatchdog, startStreamWatchdog, touchStreamWatchdog } = createStreamWatchdog({
    streamWatchdogs,
    getOrCreateSessionState,
    reconcileMessages,
    onStale: (sessionID, meta) => {
      void recoverSilentStream(sessionID, meta.staleDurationMs)
    }
  })

  Object.assign(
    eventTransport,
    createEventSubscriptionLifecycle({
      disposing: () => disposing,
      eventUnsubscribe,
      selectedEngine,
      getActiveAdapter,
      activeSessionId,
      applyEvent,
      getOrCreateSessionState,
      touchStreamWatchdog,
      clearStreamWatchdog,
      fetchRuntimeDiagnostics: fetchDiag,
      ensureRunSupervisorTimer,
      transportInstanceSeq
    })
  )

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
      logger.info('[codingAgentStore] ensureReadyWithWorkspace_short_circuit', {
        workspaceId,
        pluginId: String(workspaceTarget.pluginId || ''),
        workspacePath: String(workspaceTarget.workspacePath || ''),
        activeSessionId: String(activeSessionId.value || '')
      })
      await eventTransport.ensureEventSubscription({ reason: 'ready_short_circuit' })
      return
    }

    if (ensureReadyPromise.value) {
      await ensureReadyPromise.value
      if (isReady.value && boundWorkspaceId.value === workspaceId && activeSessionId.value) {
        logger.info('[codingAgentStore] ensureReadyWithWorkspace_after_inflight', {
          workspaceId,
          pluginId: String(workspaceTarget.pluginId || ''),
          workspacePath: String(workspaceTarget.workspacePath || ''),
          activeSessionId: String(activeSessionId.value || '')
        })
        await eventTransport.ensureEventSubscription({ reason: 'ready_after_inflight' })
        return
      }
    }

    if (isReady.value && boundWorkspaceId.value && boundWorkspaceId.value !== workspaceId) {
      logger.info('[codingAgentStore] ensureReadyWithWorkspace_switch_workspace', {
        fromWorkspaceId: String(boundWorkspaceId.value || ''),
        fromPluginId: String(boundWorkspaceTarget.value?.pluginId || ''),
        fromWorkspacePath: String(boundWorkspaceTarget.value?.workspacePath || ''),
        toWorkspaceId: workspaceId,
        toPluginId: String(workspaceTarget.pluginId || ''),
        toWorkspacePath: String(workspaceTarget.workspacePath || ''),
        previousActiveSessionId: String(activeSessionId.value || '')
      })
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
            const hasDefaultAgent = nextAgents.some((item) => String(item?.id || '') === workspaceTarget.defaultAgent)
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

        await eventTransport.ensureEventSubscription({ reason: 'ensure_ready' })

        await loadSessions()
        await reconcileQuestions()
        const preferredSession = localStorage.getItem(activeSessionStorageKey(workspaceId)) || ''
        const fallbackSession =
          workspaceTarget.sessionStrategy === 'single' ? '' : sessions.value[0]?.id || ''

        if (preferredSession && sessions.value.some((item) => item.id === preferredSession)) {
          setActiveSession(preferredSession)
        } else if (fallbackSession) {
          setActiveSession(fallbackSession)
        } else {
          await createSession(DEFAULT_SESSION_TITLE, true)
        }

        logger.info('[codingAgentStore] ensureReadyWithWorkspace_session_selected', {
          workspaceId,
          pluginId: String(workspaceTarget.pluginId || ''),
          workspacePath: String(workspaceTarget.workspacePath || ''),
          preferredSession,
          fallbackSession,
          selectedSessionId: String(activeSessionId.value || ''),
          sessionIds: sessions.value.map((item) => item.id)
        })

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
    eventTransport.clearReconnectTimer()
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
