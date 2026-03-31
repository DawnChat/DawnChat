import type { Ref } from 'vue'
import type { CodingAgentMessageInfo, CodingAgentPart } from '@/services/coding-agent/engineAdapter'
import type { SessionState } from '@/features/coding-agent/store/types'

export function resolvePartOrder(part: CodingAgentPart, orderMap: Record<string, number>): number {
  const rawOrder = (part as any)?.order ?? (part as any)?.index ?? (part as any)?.sequence
  const parsedOrder = Number(rawOrder)
  if (Number.isFinite(parsedOrder)) {
    return parsedOrder
  }
  return orderMap[String(part.id || '')] ?? Number.MAX_SAFE_INTEGER
}

export function createMessageRepository(input: {
  getOrCreateSessionState: (sessionID: string) => SessionState
  messageSessionById: Ref<Record<string, string>>
  pendingLocalUserMessageIdsBySession: Ref<Record<string, string[]>>
}) {
  const { getOrCreateSessionState, messageSessionById, pendingLocalUserMessageIdsBySession } = input

  function upsertMessageInfo(sessionID: string, info: CodingAgentMessageInfo) {
    if (!sessionID || !info?.id) return
    const state = getOrCreateSessionState(sessionID)
    state.messagesById[info.id] = {
      ...(state.messagesById[info.id] || {}),
      ...info
    }
    messageSessionById.value[info.id] = sessionID
  }

  function upsertPart(sessionID: string, part: CodingAgentPart & { messageID?: string }) {
    const messageID = String(part.messageID || '')
    const partId = String(part.id || '')
    if (!sessionID || !messageID || !partId) return
    const state = getOrCreateSessionState(sessionID)
    if (!state.partsByMessageId[messageID]) {
      state.partsByMessageId[messageID] = {}
    }
    if (!state.partOrderByMessageId[messageID]) {
      state.partOrderByMessageId[messageID] = {}
    }
    if (state.partOrderByMessageId[messageID][partId] === undefined) {
      state.partOrderSeq += 1
      state.partOrderByMessageId[messageID][partId] = state.partOrderSeq
    }
    state.partsByMessageId[messageID][partId] = {
      ...(state.partsByMessageId[messageID][partId] || {}),
      ...part
    }
  }

  function appendPartDelta(
    sessionID: string,
    messageID: string,
    partID: string,
    field: string,
    delta: string,
    partType?: string
  ) {
    if (!sessionID || !messageID || !partID || !field || !delta) return
    const state = getOrCreateSessionState(sessionID)
    if (!state.partsByMessageId[messageID]) {
      state.partsByMessageId[messageID] = {}
    }
    if (!state.partOrderByMessageId[messageID]) {
      state.partOrderByMessageId[messageID] = {}
    }
    if (!state.partsByMessageId[messageID][partID]) {
      if (state.partOrderByMessageId[messageID][partID] === undefined) {
        state.partOrderSeq += 1
        state.partOrderByMessageId[messageID][partID] = state.partOrderSeq
      }
      state.partsByMessageId[messageID][partID] = {
        id: partID,
        type: partType || (field === 'text' ? 'text' : 'unknown'),
        messageID
      }
    }
    const existing = state.partsByMessageId[messageID][partID] as Record<string, unknown>
    if (partType && !existing.type) {
      existing.type = partType
    }
    const previous = typeof existing[field] === 'string' ? (existing[field] as string) : ''
    if (delta.length <= previous.length && previous.endsWith(delta)) {
      return
    }
    existing[field] = `${previous}${delta}`
  }

  function removePart(sessionID: string, messageID: string, partID: string) {
    if (!sessionID || !messageID || !partID) return
    const state = getOrCreateSessionState(sessionID)
    if (!state.partsByMessageId[messageID]) return
    delete state.partsByMessageId[messageID][partID]
    if (state.partOrderByMessageId[messageID]) {
      delete state.partOrderByMessageId[messageID][partID]
    }
  }

  function removeMessage(sessionID: string, messageID: string) {
    if (!sessionID || !messageID) return
    const state = getOrCreateSessionState(sessionID)
    delete state.messagesById[messageID]
    delete state.partsByMessageId[messageID]
    delete state.partOrderByMessageId[messageID]
    delete messageSessionById.value[messageID]
  }

  function appendSessionErrorMessage(sessionID: string, text: string, rawMessage: string) {
    if (!sessionID || !text) return
    const messageID = `msg_local_error_${Date.now()}`
    const partID = `part_local_error_${Date.now()}`
    upsertMessageInfo(sessionID, {
      id: messageID,
      role: 'assistant',
      sessionID,
      time: {
        created: new Date().toISOString(),
        completed: new Date().toISOString()
      },
      error: { message: rawMessage || text }
    } as CodingAgentMessageInfo)
    upsertPart(sessionID, {
      id: partID,
      type: 'text',
      messageID,
      text
    } as CodingAgentPart & { messageID: string })
  }

  function pushLocalUserEcho(sessionID: string, content: string) {
    if (!sessionID || !content) return
    const now = new Date().toISOString()
    const messageID = `msg_local_user_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const partID = `part_local_user_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    upsertMessageInfo(sessionID, {
      id: messageID,
      role: 'user',
      sessionID,
      time: {
        created: now
      }
    } as CodingAgentMessageInfo)
    upsertPart(sessionID, {
      id: partID,
      type: 'text',
      messageID,
      text: content
    } as CodingAgentPart & { messageID: string })
    if (!pendingLocalUserMessageIdsBySession.value[sessionID]) {
      pendingLocalUserMessageIdsBySession.value[sessionID] = []
    }
    pendingLocalUserMessageIdsBySession.value[sessionID].push(messageID)
  }

  function clearPendingLocalUserEchoes(sessionID: string) {
    const pending = pendingLocalUserMessageIdsBySession.value[sessionID] || []
    if (pending.length === 0) return
    for (const messageID of pending) {
      removeMessage(sessionID, messageID)
    }
    delete pendingLocalUserMessageIdsBySession.value[sessionID]
  }

  return {
    upsertMessageInfo,
    upsertPart,
    appendPartDelta,
    removePart,
    removeMessage,
    appendSessionErrorMessage,
    pushLocalUserEcho,
    clearPendingLocalUserEchoes
  }
}
