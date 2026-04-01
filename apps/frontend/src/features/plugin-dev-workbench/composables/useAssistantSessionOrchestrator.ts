import type {
  CapabilityInvokeExecutionContext,
  CapabilityInvokeRequest,
} from '@/composables/usePluginUiBridge'
import { logger } from '@/utils/logger'

interface SessionStepAction {
  type: string
  payload: Record<string, unknown>
}

interface SessionStep {
  id?: string
  action: SessionStepAction
  timeoutMs?: number
}

interface SessionState {
  sessionId: string
  pluginId: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  currentStepIndex: number
  totalSteps: number
  completedSteps: number
  currentStepId?: string
  startedAtMs: number
  updatedAtMs: number
  endedAtMs?: number
  stopRequested: boolean
  lastError?: string
  lastErrorCode?: string
}

interface SessionWaitRequest {
  sessionId: string
  waitFor: 'session_terminal' | 'runtime_event'
  timeoutMs?: number
  sinceSeq: number
  eventTypes: string[]
  match: Record<string, unknown>
}

interface UseAssistantSessionOrchestratorOptions {
  pluginId: { value: string }
}

function toRecord(raw: unknown): Record<string, unknown> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {}
  }
  return raw as Record<string, unknown>
}

function toSessionStep(raw: unknown, index: number): SessionStep | null {
  const record = toRecord(raw)
  const action = toRecord(record.action)
  const actionType = String(action.type || '').trim()
  if (!actionType) {
    return null
  }
  const rawActionPayload = action.payload
  const actionPayload = toRecord(rawActionPayload)
  const stepId = typeof record.id === 'string' ? record.id.trim() : ''
  const rawTimeoutMs = record.timeout_ms
  const timeoutMs = typeof rawTimeoutMs === 'number' && Number.isFinite(rawTimeoutMs) ? rawTimeoutMs : undefined
  return {
    id: stepId || `step-${index + 1}`,
    action: {
      type: actionType,
      payload: actionPayload,
    },
    timeoutMs,
  }
}

function buildSessionStatus(state: SessionState): Record<string, unknown> {
  const now = Date.now()
  const effectiveEndAtMs = typeof state.endedAtMs === 'number' ? state.endedAtMs : undefined
  const elapsedMs = Math.max(0, (effectiveEndAtMs ?? now) - state.startedAtMs)
  const progressPercent =
    state.totalSteps > 0 ? Math.min(100, Math.round((state.completedSteps / state.totalSteps) * 100)) : 0
  return {
    session_id: state.sessionId,
    status: state.status,
    current_step_index: state.currentStepIndex,
    current_step_id: state.currentStepId || '',
    completed_steps: state.completedSteps,
    total_steps: state.totalSteps,
    progress_percent: progressPercent,
    started_at_ms: state.startedAtMs,
    updated_at_ms: state.updatedAtMs,
    ended_at_ms: effectiveEndAtMs,
    elapsed_ms: elapsedMs,
    last_error: state.lastError || '',
    last_error_code: state.lastErrorCode || '',
  }
}

function toNonNegativeNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) {
    return value
  }
  return undefined
}

function toNonNegativeInteger(value: unknown): number | undefined {
  const parsed = toNonNegativeNumber(value)
  if (parsed === undefined) {
    return undefined
  }
  return Math.floor(parsed)
}

function toStringArray(raw: unknown): string[] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw
    .filter((item) => typeof item === 'string')
    .map((item) => item.trim())
    .filter(Boolean)
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

export function useAssistantSessionOrchestrator(options: UseAssistantSessionOrchestratorOptions) {
  const configuredPluginId = String(options.pluginId.value || '').trim()
  const sessionById = new Map<string, SessionState>()
  const sessionExecutionById = new Map<string, Promise<void>>()
  const activeSessionByPlugin = new Map<string, string>()
  const terminalWaitersBySession = new Map<string, Set<(state: SessionState) => void>>()
  const DEFAULT_SESSION_WAIT_TIMEOUT_MS = 115_000
  const EVENT_POLL_INTERVAL_MS = 250
  let seq = 0

  const resolvePluginId = (context: CapabilityInvokeExecutionContext): string => {
    return configuredPluginId || context.pluginId
  }

  const updateSessionTimestamp = (state: SessionState): void => {
    state.updatedAtMs = Date.now()
  }

  const notifyTerminalWaiters = (state: SessionState): void => {
    const waiters = terminalWaitersBySession.get(state.sessionId)
    if (!waiters || waiters.size === 0) {
      return
    }
    terminalWaitersBySession.delete(state.sessionId)
    for (const waiter of waiters) {
      waiter(state)
    }
  }

  const addTerminalWaiter = (sessionId: string, waiter: (state: SessionState) => void): (() => void) => {
    const waiters = terminalWaitersBySession.get(sessionId) || new Set<(state: SessionState) => void>()
    waiters.add(waiter)
    terminalWaitersBySession.set(sessionId, waiters)
    return () => {
      const currentWaiters = terminalWaitersBySession.get(sessionId)
      if (!currentWaiters) {
        return
      }
      currentWaiters.delete(waiter)
      if (currentWaiters.size === 0) {
        terminalWaitersBySession.delete(sessionId)
      }
    }
  }

  const releaseActiveSessionLock = (state: SessionState): void => {
    const activeSessionId = activeSessionByPlugin.get(state.pluginId)
    if (activeSessionId === state.sessionId) {
      activeSessionByPlugin.delete(state.pluginId)
    }
  }

  const markSessionTerminal = (
    state: SessionState,
    status: 'completed' | 'failed' | 'cancelled',
    errorCode?: string,
    errorMessage?: string
  ): void => {
    state.status = status
    state.endedAtMs = Date.now()
    state.updatedAtMs = state.endedAtMs
    if (errorCode) {
      state.lastErrorCode = errorCode
    }
    if (errorMessage) {
      state.lastError = errorMessage
    }
    notifyTerminalWaiters(state)
  }

  const parseSessionWait = (raw: Record<string, unknown>): SessionWaitRequest | null => {
    const sessionId = String(raw.session_id || '').trim()
    if (!sessionId) {
      return null
    }
    return {
      sessionId,
      waitFor: String(raw.wait_for || 'session_terminal').trim() === 'runtime_event'
        ? 'runtime_event'
        : 'session_terminal',
      timeoutMs: toNonNegativeNumber(raw.timeout_ms),
      sinceSeq: toNonNegativeInteger(raw.since_seq) ?? 0,
      eventTypes: toStringArray(raw.event_types),
      match: toRecord(raw.match),
    }
  }

  const executeSessionStep = async (
    context: CapabilityInvokeExecutionContext,
    sessionId: string,
    step: SessionStep,
    stepIndex: number,
    totalSteps: number
  ) => {
    const invoke: CapabilityInvokeRequest = {
      functionName: 'assistant.session_step_execute',
      payload: {
        session_id: sessionId,
        step_id: step.id,
        step_index: stepIndex,
        total_steps: totalSteps,
        action: {
          type: step.action.type,
          payload: step.action.payload,
        },
        timeout_ms: step.timeoutMs,
      },
      options: context.invoke.options,
    }
    return await context.executePluginCapability(invoke)
  }

  const requestSessionStepCancel = async (
    context: CapabilityInvokeExecutionContext,
    state: SessionState,
    reason: string
  ): Promise<Record<string, unknown>> => {
    const invoke: CapabilityInvokeRequest = {
      functionName: 'assistant.session_step_cancel',
      payload: {
        session_id: state.sessionId,
        step_id: state.currentStepId || '',
        reason,
      },
      options: context.invoke.options,
    }
    return await context.executePluginCapability(invoke)
  }

  const runSessionSteps = async (
    context: CapabilityInvokeExecutionContext,
    state: SessionState,
    steps: SessionStep[]
  ): Promise<void> => {
    try {
      for (let index = 0; index < steps.length; index += 1) {
        if (state.stopRequested) {
          if (state.status !== 'cancelled') {
            markSessionTerminal(state, 'cancelled', 'session_cancelled', state.lastError || 'session cancelled')
          }
          return
        }
        state.currentStepIndex = index
        const step = steps[index]
        state.currentStepId = step.id || ''
        updateSessionTimestamp(state)
        const stepResult = await executeSessionStep(context, state.sessionId, step, index, steps.length)
        if (state.stopRequested) {
          if (state.status !== 'cancelled') {
            markSessionTerminal(state, 'cancelled', 'session_cancelled', state.lastError || 'session cancelled')
          }
          return
        }
        if (!stepResult.ok) {
          markSessionTerminal(
            state,
            'failed',
            String(stepResult.error_code || 'step_failed'),
            String(stepResult.message || stepResult.error_code || 'step_failed')
          )
          return
        }
        state.completedSteps = index + 1
        updateSessionTimestamp(state)
      }
      markSessionTerminal(state, 'completed')
    } catch (error) {
      markSessionTerminal(state, 'failed', 'session_execution_exception', String(error))
      logger.warn('assistant_session_async_execution_failed', {
        pluginId: state.pluginId,
        sessionId: state.sessionId,
        error: String(error),
      })
    }
  }

  const ensureSessionExecution = (
    context: CapabilityInvokeExecutionContext,
    state: SessionState,
    steps: SessionStep[]
  ): void => {
    const existingExecution = sessionExecutionById.get(state.sessionId)
    if (existingExecution) {
      return
    }
    const execution = runSessionSteps(context, state, steps).finally(() => {
      sessionExecutionById.delete(state.sessionId)
      releaseActiveSessionLock(state)
    })
    sessionExecutionById.set(state.sessionId, execution)
  }

  const waitForSessionTerminal = async (
    state: SessionState,
    timeoutMs: number
  ): Promise<Record<string, unknown>> => {
    if (state.status !== 'running') {
      return {
        ok: true,
        data: {
          session_id: state.sessionId,
          wait_for: 'session_terminal',
          status: 'terminal',
          latest_seq: 0,
          session_status: buildSessionStatus(state),
        },
      }
    }
    return await new Promise<Record<string, unknown>>((resolve) => {
      const clearWaiter = addTerminalWaiter(state.sessionId, (nextState) => {
        window.clearTimeout(timer)
        resolve({
          ok: true,
          data: {
            session_id: nextState.sessionId,
            wait_for: 'session_terminal',
            status: 'terminal',
            latest_seq: 0,
            session_status: buildSessionStatus(nextState),
          },
        })
      })
      const timer = window.setTimeout(() => {
        clearWaiter()
        resolve({
          ok: true,
          data: {
            session_id: state.sessionId,
            wait_for: 'session_terminal',
            status: 'timed_out',
            latest_seq: 0,
            session_status: buildSessionStatus(state),
          },
        })
      }, timeoutMs)
    })
  }

  const waitForRuntimeEvent = async (
    context: CapabilityInvokeExecutionContext,
    state: SessionState,
    waitRequest: SessionWaitRequest,
    timeoutMs: number
  ): Promise<Record<string, unknown>> => {
    let latestSeq = waitRequest.sinceSeq
    const startedAt = Date.now()
    while (true) {
      if (state.status !== 'running') {
        return {
          ok: true,
          data: {
            session_id: state.sessionId,
            wait_for: 'runtime_event',
            status: 'terminal',
            latest_seq: latestSeq,
            session_status: buildSessionStatus(state),
          },
        }
      }
      const peekResult = await context.executePluginCapability({
        functionName: 'assistant.runtime.event.peek',
        payload: {
          session_id: state.sessionId,
          since_seq: latestSeq,
          limit: 50,
          event_types: waitRequest.eventTypes,
          match: waitRequest.match,
        },
        options: context.invoke.options,
      })
      if (!peekResult.ok) {
        return {
          ok: false,
          error_code: String(peekResult.error_code || 'runtime_event_wait_failed'),
          message: String(peekResult.message || peekResult.error_code || 'runtime event wait failed'),
        }
      }
      const peekData = toRecord(peekResult.data)
      const nextLatestSeq = toNonNegativeInteger(peekData.latest_seq)
      if (nextLatestSeq !== undefined) {
        latestSeq = Math.max(latestSeq, nextLatestSeq)
      }
      const events = Array.isArray(peekData.events)
        ? peekData.events.filter((event): event is Record<string, unknown> => Boolean(event) && typeof event === 'object')
        : []
      if (events.length > 0) {
        const matchedEvent = events[0]
        const matchedSeq = toNonNegativeInteger(matchedEvent.seq)
        if (matchedSeq !== undefined) {
          latestSeq = Math.max(latestSeq, matchedSeq)
        }
        return {
          ok: true,
          data: {
            session_id: state.sessionId,
            wait_for: 'runtime_event',
            status: 'matched',
            latest_seq: latestSeq,
            matched_event: matchedEvent,
            session_status: buildSessionStatus(state),
          },
        }
      }
      if (Date.now() - startedAt >= timeoutMs) {
        return {
          ok: true,
          data: {
            session_id: state.sessionId,
            wait_for: 'runtime_event',
            status: 'timed_out',
            latest_seq: latestSeq,
            session_status: buildSessionStatus(state),
          },
        }
      }
      await sleep(EVENT_POLL_INTERVAL_MS)
    }
  }

  const handleSessionStart = async (context: CapabilityInvokeExecutionContext): Promise<Record<string, unknown>> => {
    const payload = toRecord(context.invoke.payload)
    const pluginId = resolvePluginId(context)
    const activeSessionId = activeSessionByPlugin.get(pluginId)
    if (activeSessionId) {
      const activeState = sessionById.get(activeSessionId)
      if (activeState && (activeState.status === 'running' || sessionExecutionById.has(activeSessionId))) {
        return {
          ok: false,
          error_code: 'session_busy',
          message: `active session is running: ${activeSessionId}`,
          data: {
            active_session_id: activeSessionId,
          },
        }
      }
      activeSessionByPlugin.delete(pluginId)
    }
    const rawSteps = payload.steps
    if (!Array.isArray(rawSteps) || rawSteps.length === 0) {
      return {
        ok: false,
        error_code: 'invalid_step',
        message: 'steps must be a non-empty array',
      }
    }
    const steps: SessionStep[] = []
    for (let index = 0; index < rawSteps.length; index += 1) {
      const step = toSessionStep(rawSteps[index], index)
      if (!step) {
        return {
          ok: false,
          error_code: 'invalid_step',
          message: `steps[${index}].action.type is required`,
        }
      }
      steps.push(step)
    }
    seq += 1
    const sessionId = `sess_${Date.now()}_${seq}`
    const now = Date.now()
    const state: SessionState = {
      sessionId,
      pluginId,
      status: 'running',
      currentStepIndex: 0,
      totalSteps: steps.length,
      completedSteps: 0,
      currentStepId: steps[0]?.id || '',
      startedAtMs: now,
      updatedAtMs: now,
      stopRequested: false,
    }
    sessionById.set(sessionId, state)
    activeSessionByPlugin.set(pluginId, sessionId)
    ensureSessionExecution(context, state, steps)
    return {
      ok: true,
      data: {
        ...buildSessionStatus(state),
        accepted: true,
      },
    }
  }

  const handleSessionStatus = (context: CapabilityInvokeExecutionContext): Record<string, unknown> => {
    const payload = toRecord(context.invoke.payload)
    const sessionId = String(payload.session_id || '').trim()
    if (!sessionId) {
      return {
        ok: false,
        error_code: 'session_not_found',
        message: 'session_id is required',
      }
    }
    const state = sessionById.get(sessionId)
    if (!state || state.pluginId !== resolvePluginId(context)) {
      return {
        ok: false,
        error_code: 'session_not_found',
        message: `session not found: ${sessionId}`,
      }
    }
    return {
      ok: true,
      data: buildSessionStatus(state),
    }
  }

  const handleSessionStop = async (context: CapabilityInvokeExecutionContext): Promise<Record<string, unknown>> => {
    const payload = toRecord(context.invoke.payload)
    const sessionId = String(payload.session_id || '').trim()
    if (!sessionId) {
      return {
        ok: false,
        error_code: 'invalid_arguments',
        message: 'session_id is required',
      }
    }
    const state = sessionById.get(sessionId)
    if (!state || state.pluginId !== resolvePluginId(context)) {
      return {
        ok: false,
        error_code: 'session_not_found',
        message: `session not found: ${sessionId}`,
      }
    }
    if (state.status !== 'running') {
      return {
        ok: true,
        data: {
          ...buildSessionStatus(state),
          stopped: false,
          already_terminal: true,
        },
      }
    }
    const reason = String(payload.reason || '').trim()
    state.stopRequested = true
    updateSessionTimestamp(state)
    let cancelResult: Record<string, unknown> | null = null
    try {
      cancelResult = await requestSessionStepCancel(
        context,
        state,
        reason || 'session stopped by host'
      )
    } catch (error) {
      logger.warn('assistant_session_cancel_propagation_failed', {
        pluginId: state.pluginId,
        sessionId,
        currentStepId: state.currentStepId || '',
        error: String(error),
      })
    }
    markSessionTerminal(state, 'cancelled', 'session_stopped', reason || 'session stopped by host')
    const cancelData = cancelResult ? toRecord(cancelResult.data) : {}
    return {
      ok: true,
      data: {
        ...buildSessionStatus(state),
        stopped: true,
        already_terminal: false,
        cancel_propagated: cancelResult?.ok === true && cancelData.cancel_requested === true,
        cancelled_step_id: String(cancelData.step_id || state.currentStepId || ''),
      },
    }
  }

  const handleSessionWait = async (context: CapabilityInvokeExecutionContext): Promise<Record<string, unknown>> => {
    const payload = toRecord(context.invoke.payload)
    const waitRequest = parseSessionWait(payload)
    if (!waitRequest) {
      return {
        ok: false,
        error_code: 'invalid_arguments',
        message: 'session_id is required',
      }
    }
    const state = sessionById.get(waitRequest.sessionId)
    if (!state || state.pluginId !== resolvePluginId(context)) {
      return {
        ok: false,
        error_code: 'session_not_found',
        message: `session not found: ${waitRequest.sessionId}`,
      }
    }
    if (waitRequest.waitFor === 'runtime_event' && waitRequest.eventTypes.length === 0) {
      return {
        ok: false,
        error_code: 'invalid_arguments',
        message: 'event_types is required when wait_for=runtime_event',
      }
    }
    const timeoutMs = waitRequest.timeoutMs ?? DEFAULT_SESSION_WAIT_TIMEOUT_MS
    if (waitRequest.waitFor === 'session_terminal') {
      return await waitForSessionTerminal(state, timeoutMs)
    }
    return await waitForRuntimeEvent(context, state, waitRequest, timeoutMs)
  }

  const handleCapabilityInvokeRequest = async (
    context: CapabilityInvokeExecutionContext
  ): Promise<Record<string, unknown> | null> => {
    if (context.invoke.functionName === 'assistant.session.start') {
      return await handleSessionStart(context)
    }
    if (context.invoke.functionName === 'assistant.session.status') {
      return handleSessionStatus(context)
    }
    if (context.invoke.functionName === 'assistant.session.stop') {
      return handleSessionStop(context)
    }
    if (context.invoke.functionName === 'assistant.session.wait') {
      return await handleSessionWait(context)
    }
    return null
  }

  return {
    handleCapabilityInvokeRequest,
  }
}
