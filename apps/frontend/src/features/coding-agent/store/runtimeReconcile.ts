import type { Ref } from 'vue'
import { logger } from '@/utils/logger'
import type { CodingAgentMessage, CodingAgentMessageInfo, CodingAgentPart } from '@/services/coding-agent/engineAdapter'
import type { SessionState } from '@/features/coding-agent/store/types'
import { isRecord } from '@/features/coding-agent/store/runtimeTypeGuards'

export function readStablePartOrder(part: CodingAgentPart, existingOrder?: number): number {
  const ext = part as CodingAgentPart & { order?: unknown; index?: unknown; sequence?: unknown }
  const rawOrder = ext.order ?? ext.index ?? ext.sequence
  const parsedOrder = Number(rawOrder)
  if (Number.isFinite(parsedOrder)) {
    return parsedOrder
  }
  if (existingOrder !== undefined) {
    return existingOrder
  }
  return -1
}

export function replaceSessionMessageSnapshot(
  sessionID: string,
  rows: CodingAgentMessage[],
  deps: {
    getOrCreateSessionState: (sessionID: string) => SessionState
    pendingLocalUserMessageIdsBySession: Ref<Record<string, string[]>>
  }
): void {
  const state = deps.getOrCreateSessionState(sessionID)
  const pendingLocalIds = new Set(deps.pendingLocalUserMessageIdsBySession.value[sessionID] || [])
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

export function toUnixTime(value: unknown): number {
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

export function hasPendingInteractiveCards(state: SessionState): boolean {
  const hasPendingPermission = Object.values(state.permissionCardsById).some((item) => item.status === 'pending')
  if (hasPendingPermission) return true
  return Object.values(state.questionCardsById).some((item) => item.status === 'pending')
}

export function getLatestAssistantMessage(state: SessionState): CodingAgentMessageInfo | null {
  const assistants = Object.values(state.messagesById).filter((item) => String(item?.role || '').toLowerCase() === 'assistant')
  if (assistants.length === 0) {
    return null
  }
  assistants.sort((a, b) => {
    const ta = Math.max(toUnixTime(a?.time?.created), toUnixTime(a?.time?.completed))
    const tb = Math.max(toUnixTime(b?.time?.created), toUnixTime(b?.time?.completed))
    return ta - tb
  })
  return assistants[assistants.length - 1] ?? null
}

export function hasRunningToolOrReasoning(state: SessionState): boolean {
  const allParts = Object.values(state.partsByMessageId).flatMap((partsMap) => Object.values(partsMap || {}))
  for (const part of allParts) {
    const partType = String(part?.type || '').toLowerCase()
    if (partType === 'tool') {
      const toolStatus = String(part.state?.status || '').toLowerCase()
      if (toolStatus === 'pending' || toolStatus === 'running') {
        return true
      }
      continue
    }
    if (partType === 'reasoning') {
      const timeRaw = part.time
      const reasoningEnd = isRecord(timeRaw) ? timeRaw.end : undefined
      if (!reasoningEnd) {
        return true
      }
    }
  }
  return false
}

export function maybeFinalizeStreamingFromSnapshot(
  sessionID: string,
  deps: {
    getOrCreateSessionState: (sessionID: string) => SessionState
    clearStreamWatchdog: (sessionID: string) => void
  }
): void {
  const state = deps.getOrCreateSessionState(sessionID)
  if (!state.isStreaming) return
  if (hasPendingInteractiveCards(state)) return
  const latestAssistant = getLatestAssistantMessage(state)
  if (!latestAssistant) return
  const completedAt = toUnixTime(latestAssistant.time?.completed)
  if (!completedAt) return
  if (hasRunningToolOrReasoning(state)) return

  state.isStreaming = false
  state.sessionRunStatus = 'idle'
  state.runWaitReason = ''
  deps.clearStreamWatchdog(sessionID)
  logger.info('[codingAgentStore] inferred terminal state from snapshot reconcile', {
    sessionID,
    recover_reason: 'snapshot_terminal_inference',
    completed_at: completedAt
  })
}
