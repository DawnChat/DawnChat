import type { Ref } from 'vue'
import type {
  CodingAgentPermissionRequest,
  CodingAgentQuestionAnswer,
  EngineAdapter
} from '@/services/coding-agent/engineAdapter'
import { normalizePermissionPayload } from '@/features/coding-agent/store/permissionNormalizer'
import type { QuestionCard, SessionState } from '@/features/coding-agent/store/types'

interface PermissionQuestionServiceInput {
  getAdapter: () => EngineAdapter
  sessionStateById: Ref<Record<string, SessionState>>
  messageSessionById: Ref<Record<string, string>>
  activeSessionId: Ref<string>
  upsertQuestionCard: (sessionID: string, card: QuestionCard) => void
  clearQuestionsBySession: (sessionID: string) => void
  upsertPermissionCard: (sessionID: string, card: any) => void
  clearPermissionsBySession: (sessionID: string) => void
}

export function createPermissionQuestionService(input: PermissionQuestionServiceInput) {
  const {
    getAdapter,
    sessionStateById,
    messageSessionById,
    activeSessionId,
    upsertQuestionCard,
    clearQuestionsBySession,
    upsertPermissionCard,
    clearPermissionsBySession
  } = input

  function resolvePermissionTargetSessionID(item: Record<string, any>): string {
    const direct = String(item?.sessionID || item?.sessionId || '').trim()
    if (direct) return direct
    const toolSession = String(item?.tool?.sessionID || item?.tool?.sessionId || '').trim()
    if (toolSession) return toolSession
    const permissionLike = item?.permission && typeof item.permission === 'object' ? item.permission : null
    const fromPermission = String(permissionLike?.sessionID || permissionLike?.sessionId || '').trim()
    if (fromPermission) return fromPermission

    const messageID = String(
      item?.messageID ||
        item?.messageId ||
        item?.tool?.messageID ||
        item?.tool?.messageId ||
        permissionLike?.messageID ||
        permissionLike?.messageId ||
        ''
    ).trim()
    if (messageID && messageSessionById.value[messageID]) {
      return String(messageSessionById.value[messageID] || '').trim()
    }
    return ''
  }

  async function reconcileQuestions(targetSessionID?: string): Promise<void> {
    const adapter = getAdapter() as any
    if (typeof adapter.listQuestions !== 'function') {
      if (targetSessionID) {
        clearQuestionsBySession(targetSessionID)
      }
      return
    }
    const sessionID = String(targetSessionID || '').trim()
    const rows = await adapter.listQuestions(sessionID || undefined)
    const questions = Array.isArray(rows) ? rows : []
    if (sessionID) {
      clearQuestionsBySession(sessionID)
    } else {
      for (const id of Object.keys(sessionStateById.value)) {
        clearQuestionsBySession(id)
      }
    }
    for (const item of questions) {
      const target = String(item?.sessionID || '').trim()
      const requestID = String(item?.id || '').trim()
      if (!target || !requestID) continue
      upsertQuestionCard(target, {
        id: requestID,
        sessionID: target,
        messageID: String(item?.tool?.messageID || ''),
        questions: Array.isArray(item?.questions) ? item.questions : [],
        status: 'pending',
        toolCallID: String(item?.tool?.callID || '')
      })
    }
  }

  async function reconcilePermissions(targetSessionID?: string): Promise<void> {
    const adapter = getAdapter() as any
    if (typeof adapter.listPermissions !== 'function') {
      if (targetSessionID) {
        clearPermissionsBySession(targetSessionID)
      }
      return
    }
    const sessionID = String(targetSessionID || '').trim()
    const rows = (await adapter.listPermissions(sessionID || undefined)) as CodingAgentPermissionRequest[]
    const permissions = Array.isArray(rows) ? rows : []
    if (sessionID) {
      clearPermissionsBySession(sessionID)
    } else {
      for (const id of Object.keys(sessionStateById.value)) {
        clearPermissionsBySession(id)
      }
    }
    for (const item of permissions) {
      const target = resolvePermissionTargetSessionID(item as Record<string, any>)
      const permissionID = String(item?.id || '').trim()
      if (!target || !permissionID) continue
      const card = normalizePermissionPayload(item as Record<string, any>, 'permission.asked')
      if (!card) continue
      upsertPermissionCard(target, {
        ...card,
        sessionID: target
      })
    }
  }

  function findQuestionSessionID(requestID: string): string {
    const direct = activeSessionId.value
    if (direct) {
      const state = sessionStateById.value[direct]
      if (state?.questionCardsById[requestID]) {
        return direct
      }
    }
    for (const [sessionID, state] of Object.entries(sessionStateById.value)) {
      if (state.questionCardsById[requestID]) {
        return sessionID
      }
    }
    return ''
  }

  async function replyQuestion(requestID: string, answers: CodingAgentQuestionAnswer[]): Promise<boolean> {
    const adapter = getAdapter()
    if (typeof adapter.replyQuestion !== 'function') {
      throw new Error('当前引擎不支持问题答复')
    }
    const targetSessionID = findQuestionSessionID(requestID)
    if (!targetSessionID) {
      throw new Error('question not found')
    }
    const state = sessionStateById.value[targetSessionID]
    const snapshot = state?.questionCardsById[requestID]
    if (snapshot && state) {
      delete state.questionCardsById[requestID]
    }
    try {
      const ok = await adapter.replyQuestion(requestID, answers)
      return ok
    } catch (err) {
      if (snapshot && state) {
        state.questionCardsById[requestID] = snapshot
      }
      throw err
    }
  }

  async function rejectQuestion(requestID: string): Promise<boolean> {
    const adapter = getAdapter()
    if (typeof adapter.rejectQuestion !== 'function') {
      throw new Error('当前引擎不支持问题拒绝')
    }
    const targetSessionID = findQuestionSessionID(requestID)
    if (!targetSessionID) {
      throw new Error('question not found')
    }
    const state = sessionStateById.value[targetSessionID]
    const snapshot = state?.questionCardsById[requestID]
    if (snapshot && state) {
      delete state.questionCardsById[requestID]
    }
    try {
      const ok = await adapter.rejectQuestion(requestID)
      return ok
    } catch (err) {
      if (snapshot && state) {
        state.questionCardsById[requestID] = snapshot
      }
      throw err
    }
  }

  return {
    reconcileQuestions,
    reconcilePermissions,
    replyQuestion,
    rejectQuestion
  }
}
