import type { Ref } from 'vue'
import { logger } from '@/utils/logger'
import type { EngineId } from '@/services/coding-agent/adapterRegistry'
import type { CodingAgentEvent, EngineAdapter } from '@/services/coding-agent/engineAdapter'
import type { SessionState } from '@/features/coding-agent/store/types'
import { isRecord } from '@/features/coding-agent/store/runtimeTypeGuards'

export async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, label: string): Promise<T> {
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

export function resolveSessionIDFromEvent(evt: CodingAgentEvent, activeSessionId: Ref<string>): string {
  const topLevel = String(evt.sessionID || '').trim()
  if (topLevel) return topLevel
  const props = evt.properties || {}
  const direct = String(props.sessionID ?? props.sessionId ?? '').trim()
  if (direct) return direct
  const info = props.info
  if (isRecord(info)) {
    const infoSession = String(info.sessionID ?? '').trim()
    if (infoSession) return infoSession
  }
  return String(activeSessionId.value || '').trim()
}

export function isTerminalEventType(type: string): boolean {
  return ['session.idle', 'run.completed', 'run.failed', 'run.interrupted', 'session.error'].includes(type)
}

export function createEventSubscriptionLifecycle(input: {
  disposing: () => boolean
  eventUnsubscribe: Ref<(() => void) | null>
  selectedEngine: Ref<EngineId>
  getActiveAdapter: () => EngineAdapter
  activeSessionId: Ref<string>
  applyEvent: (evt: CodingAgentEvent) => void
  getOrCreateSessionState: (sessionID: string) => SessionState
  touchStreamWatchdog: (sessionID: string) => void
  clearStreamWatchdog: (sessionID: string) => void
  fetchRuntimeDiagnostics: (sessionID: string, reason: string) => Promise<void>
  ensureRunSupervisorTimer: () => void
  transportInstanceSeq: { current: number }
}) {
  let transportReconnectTimer: number | null = null

  function clearReconnectTimer() {
    if (transportReconnectTimer !== null) {
      window.clearTimeout(transportReconnectTimer)
      transportReconnectTimer = null
    }
  }

  async function ensureEventSubscription(options?: { force?: boolean; reason?: string }) {
    if (input.disposing()) return
    const force = Boolean(options?.force)
    const reason = String(options?.reason || '').trim() || 'ensure'
    if (force && input.eventUnsubscribe.value) {
      input.eventUnsubscribe.value()
      input.eventUnsubscribe.value = null
    }
    if (input.eventUnsubscribe.value) {
      return
    }
    const transportInstanceId = `${String(input.selectedEngine.value || 'engine')}-transport-${++input.transportInstanceSeq.current}`
    logger.info('[codingAgentStore] creating event subscription', {
      transport_instance_id: transportInstanceId,
      reason
    })
    input.eventUnsubscribe.value = await input.getActiveAdapter().subscribeEvents((evt: CodingAgentEvent) => {
      if (input.disposing()) return
      clearReconnectTimer()
      const eventType = String(evt.type || '')
      const sessionID = resolveSessionIDFromEvent(evt, input.activeSessionId)

      if (sessionID && eventType !== 'stream.status' && eventType !== 'server.heartbeat') {
        input.touchStreamWatchdog(sessionID)
      }
      if (sessionID && isTerminalEventType(eventType)) {
        input.clearStreamWatchdog(sessionID)
      }
      if (eventType === 'stream.status') {
        const props = evt.properties || {}
        const status = String(props.status ?? '').toLowerCase()
        if (status === 'reconnecting' || status === 'closed') {
          const latestState = sessionID ? input.getOrCreateSessionState(sessionID) : null
          logger.warn('[codingAgentStore] transport_status_signal', {
            sessionID,
            status,
            transport_instance_id: transportInstanceId,
            transport_error: String(props.error ?? ''),
            run_wait_reason: latestState?.runWaitReason || ''
          })
          if (sessionID) {
            void input.fetchRuntimeDiagnostics(sessionID, `transport_${status}`)
          }
        }
        if (status === 'closed') {
          scheduleResubscribe('stream_closed')
        }
      }

      input.applyEvent(evt)
      if (sessionID) {
        const latestState = input.getOrCreateSessionState(sessionID)
        if (latestState.isStreaming) {
          input.ensureRunSupervisorTimer()
        } else {
          latestState.runWaitReason = ''
        }
      }
    })
  }

  function scheduleResubscribe(reason: string) {
    if (input.disposing() || transportReconnectTimer !== null) return
    transportReconnectTimer = window.setTimeout(() => {
      clearReconnectTimer()
      void ensureEventSubscription({ force: true, reason })
    }, 250)
  }

  return {
    ensureEventSubscription,
    clearReconnectTimer,
    scheduleResubscribe
  }
}
