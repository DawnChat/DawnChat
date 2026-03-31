import type { Ref } from 'vue'
import { logger } from '@/utils/logger'
import type { SessionState } from '@/features/coding-agent/store/types'

export function createStreamWatchdog(input: {
  streamWatchdogs: Ref<Record<string, number>>
  getOrCreateSessionState: (sessionID: string) => SessionState
  reconcileMessages: (sessionID: string) => Promise<void>
  onStale?: (sessionID: string, meta: { staleDurationMs: number; lastActivityAt: number }) => void
  staleTimeoutMs?: number
  minRecoverIntervalMs?: number
}) {
  const { streamWatchdogs, onStale } = input
  const staleTimeoutMs = Number(input.staleTimeoutMs || 25000)
  const minRecoverIntervalMs = Number(input.minRecoverIntervalMs || 10000)
  const lastActivityBySession: Record<string, number> = {}
  const lastRecoverBySession: Record<string, number> = {}

  function clearStreamWatchdog(sessionID: string) {
    const timer = streamWatchdogs.value[sessionID]
    if (timer !== undefined) {
      window.clearTimeout(timer)
      delete streamWatchdogs.value[sessionID]
    }
    delete lastActivityBySession[sessionID]
  }

  function startStreamWatchdog(sessionID: string) {
    clearStreamWatchdog(sessionID)
    lastActivityBySession[sessionID] = Date.now()
    streamWatchdogs.value[sessionID] = window.setTimeout(() => {
      const now = Date.now()
      const lastActivityAt = Number(lastActivityBySession[sessionID] || now)
      const staleDurationMs = Math.max(0, now - lastActivityAt)
      const lastRecoverAt = Number(lastRecoverBySession[sessionID] || 0)
      const throttled = now - lastRecoverAt < minRecoverIntervalMs
      logger.warn('[codingAgentStore] stream watchdog observed prolonged quiet period', {
        sessionID,
        staleDurationMs,
        lastActivityAt,
        throttled
      })
      if (!throttled) {
        lastRecoverBySession[sessionID] = now
        onStale?.(sessionID, { staleDurationMs, lastActivityAt })
      }
      delete streamWatchdogs.value[sessionID]
    }, staleTimeoutMs)
  }

  function touchStreamWatchdog(sessionID: string) {
    if (!streamWatchdogs.value[sessionID]) return
    lastActivityBySession[sessionID] = Date.now()
    startStreamWatchdog(sessionID)
  }

  return {
    clearStreamWatchdog,
    startStreamWatchdog,
    touchStreamWatchdog
  }
}
