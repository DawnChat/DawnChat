import type { Ref } from 'vue'
import { logger } from '@/utils/logger'
import type { PermissionDecision } from '@/services/coding-agent/engineAdapter'
import type { PermissionCard, QuestionCard, SessionState } from '@/features/coding-agent/store/types'

export function createPermissionStateService(input: {
  activeSessionId: Ref<string>
  getActiveAdapter: () => {
    replyPermission: (
      sessionId: string,
      permissionId: string,
      response: PermissionDecision,
      remember?: boolean
    ) => Promise<boolean>
  }
  getOrCreateSessionState: (sessionID: string) => SessionState
  findPermissionSessionID: (permissionID: string) => string
}) {
  const { activeSessionId, getActiveAdapter, getOrCreateSessionState, findPermissionSessionID } = input

  function upsertPermissionCard(sessionID: string, card: Partial<PermissionCard> & { id: string }) {
    const id = String(card.id || '').trim()
    if (!sessionID || !id) return
    const state = getOrCreateSessionState(sessionID)
    const previous = state.permissionCardsById[id]
    state.permissionCardsById[id] = {
      id,
      sessionID: String(card.sessionID || previous?.sessionID || sessionID),
      messageID: String(card.messageID || previous?.messageID || ''),
      callID: String(card.callID || previous?.callID || ''),
      tool: String(card.tool || previous?.tool || 'tool'),
      status: (card.status || previous?.status || 'pending') as PermissionCard['status'],
      response: String(card.response || previous?.response || ''),
      detail: String(card.detail || previous?.detail || '等待用户确认权限'),
      metadataDiff: String(card.metadataDiff || previous?.metadataDiff || '')
    }
    logger.info('[codingAgentStore] permission_card_upserted', {
      sessionID,
      id,
      messageID: state.permissionCardsById[id].messageID,
      callID: state.permissionCardsById[id].callID,
      tool: state.permissionCardsById[id].tool,
      status: state.permissionCardsById[id].status
    })
  }

  function clearPermissionsBySession(sessionID: string) {
    const state = getOrCreateSessionState(sessionID)
    state.permissionCardsById = {}
  }

  function upsertQuestionCard(sessionID: string, card: QuestionCard) {
    const id = String(card.id || '').trim()
    if (!sessionID || !id) return
    const state = getOrCreateSessionState(sessionID)
    state.questionCardsById[id] = {
      ...(state.questionCardsById[id] || {}),
      ...card,
      id,
      sessionID
    }
  }

  function removeQuestionCard(sessionID: string, requestID: string) {
    const id = String(requestID || '').trim()
    if (!sessionID || !id) return
    const state = getOrCreateSessionState(sessionID)
    delete state.questionCardsById[id]
  }

  function clearQuestionsBySession(sessionID: string) {
    const state = getOrCreateSessionState(sessionID)
    state.questionCardsById = {}
  }

  async function replyPermission(
    permissionId: string,
    response: PermissionDecision,
    remember?: boolean
  ): Promise<boolean> {
    const targetSessionID = findPermissionSessionID(permissionId) || activeSessionId.value
    if (!targetSessionID) {
      throw new Error('session not ready')
    }
    const state = getOrCreateSessionState(targetSessionID)
    const permission = state.permissionCardsById[permissionId]
    const snapshot = permission
      ? {
          status: permission.status,
          response: permission.response
        }
      : null
    if (permission) {
      permission.status = response === 'reject' ? 'rejected' : 'approved'
      permission.response = response
    }
    try {
      const ok = await getActiveAdapter().replyPermission(targetSessionID, permissionId, response, remember)
      if (!ok && permission && snapshot) {
        permission.status = snapshot.status
        permission.response = snapshot.response
      }
      return ok
    } catch (err) {
      if (permission && snapshot) {
        permission.status = snapshot.status
        permission.response = snapshot.response
      }
      throw err
    }
  }

  return {
    upsertPermissionCard,
    clearPermissionsBySession,
    upsertQuestionCard,
    removeQuestionCard,
    clearQuestionsBySession,
    replyPermission
  }
}

