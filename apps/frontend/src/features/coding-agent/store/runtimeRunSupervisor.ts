import type { Ref } from 'vue'
import { logger } from '@/utils/logger'
import type { EngineId } from '@/services/coding-agent/adapterRegistry'
import { engineUsesRuntimeMeta, getControlPlanePrefix } from '@/services/coding-agent/engineCapabilities'
import type { SessionState } from '@/features/coding-agent/store/types'
import { buildBackendUrl } from '@/utils/backendUrl'

export const RUN_STALL_TIMEOUT_MS = 45000
export const RUN_SUPERVISOR_INTERVAL_MS = 5000
export const RUN_RECOVER_MIN_INTERVAL_MS = 15000
export const BACKEND_DIAG_MIN_INTERVAL_MS = 20000

export function computeRunWaitReason(state: SessionState): SessionState['runWaitReason'] {
  if (!state.isStreaming) return ''
  const hasPendingPermission = Object.values(state.permissionCardsById).some((item) => item.status === 'pending')
  if (hasPendingPermission) return 'waiting_permission'
  const hasPendingQuestion = Object.values(state.questionCardsById).some((item) => item.status === 'pending')
  if (hasPendingQuestion) return 'waiting_question'
  return 'generating'
}

export function summarizeToolSignals(state: SessionState) {
  let runningCount = 0
  let latestTool = ''
  let latestToolStatus = ''
  let latestOrder = -1
  for (const [messageID, parts] of Object.entries(state.partsByMessageId || {})) {
    for (const [partID, part] of Object.entries(parts || {})) {
      if (String(part?.type || '').toLowerCase() !== 'tool') continue
      const status = String(part.state?.status ?? (part as { status?: unknown }).status ?? '').toLowerCase()
      if (status === 'running') runningCount += 1
      const order = Number(state.partOrderByMessageId?.[messageID]?.[partID] ?? -1)
      if (order >= latestOrder) {
        latestOrder = order
        latestTool = String(part.tool || '')
        latestToolStatus = status
      }
    }
  }
  return { runningCount, latestTool, latestToolStatus }
}

export function buildRunDiagnostics(
  sessionID: string,
  state: SessionState,
  context: string,
  extra?: Record<string, unknown>
) {
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

export async function fetchRuntimeDiagnostics(
  sessionID: string,
  reason: string,
  ctx: {
    selectedEngine: Ref<EngineId>
    lastBackendDiagBySession: Record<string, number>
  }
): Promise<void> {
  if (!engineUsesRuntimeMeta(ctx.selectedEngine.value)) return
  const now = Date.now()
  const lastAt = Number(ctx.lastBackendDiagBySession[sessionID] || 0)
  if (now - lastAt < BACKEND_DIAG_MIN_INTERVAL_MS) return
  ctx.lastBackendDiagBySession[sessionID] = now
  try {
    const resp = await fetch(buildBackendUrl(`${getControlPlanePrefix(ctx.selectedEngine.value)}/diagnostics`))
    const payload = await resp.json().catch(() => null)
    logger.warn('[codingAgentStore] runtime_diagnostics', {
      sessionID,
      reason,
      engine: ctx.selectedEngine.value,
      status: resp.status,
      diagnostics: payload?.data || null
    })
  } catch (err) {
    logger.warn('[codingAgentStore] runtime_diagnostics_fetch_failed', {
      sessionID,
      reason,
      engine: ctx.selectedEngine.value,
      err
    })
  }
}

export function superviseStreamingSessionsLoop(ctx: {
  sessionStateById: Ref<Record<string, SessionState>>
  getOrCreateSessionState: (sessionID: string) => SessionState
  reconcileMessages: (sessionID: string) => Promise<void>
  ensureEventSubscription: (options?: { force?: boolean; reason?: string }) => Promise<void>
  fetchRuntimeDiagnostics: (sessionID: string, reason: string) => Promise<void>
  lastRunRecoverBySession: Record<string, number>
  clearRunSupervisorTimer: () => void
}): void {
  const now = Date.now()
  let hasStreaming = false
  for (const [sessionID, state] of Object.entries(ctx.sessionStateById.value)) {
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
    if (stalledDurationMs < RUN_STALL_TIMEOUT_MS) {
      state.runWaitReason = 'generating'
      continue
    }
    state.runWaitReason = 'stalled'
    const lastRecoverAt = Number(ctx.lastRunRecoverBySession[sessionID] || 0)
    if (now - lastRecoverAt < RUN_RECOVER_MIN_INTERVAL_MS) {
      continue
    }
    ctx.lastRunRecoverBySession[sessionID] = now
    logger.warn(
      '[codingAgentStore] run progress stalled, trigger reconcile',
      buildRunDiagnostics(sessionID, state, 'run_stalled', {
        stale_duration_ms: stalledDurationMs,
        recover_reason: 'run_stalled'
      })
    )
    void ctx.fetchRuntimeDiagnostics(sessionID, 'run_stalled')
    const transportStatus = String(state.transportStatus || '').toLowerCase()
    const isTransportHealthy = transportStatus === 'streaming'
    const recoverTask = isTransportHealthy
      ? ctx.reconcileMessages(sessionID)
      : ctx.ensureEventSubscription({ force: true, reason: 'run_stalled' }).then(() => ctx.reconcileMessages(sessionID))
    void recoverTask.catch((err) => {
      logger.warn('[codingAgentStore] run stalled recover failed', { sessionID, err })
    })
  }

  if (!hasStreaming) {
    ctx.clearRunSupervisorTimer()
  }
}
