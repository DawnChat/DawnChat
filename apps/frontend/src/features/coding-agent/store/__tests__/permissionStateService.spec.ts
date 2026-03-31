import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { createPermissionStateService } from '@/features/coding-agent/store/permissionStateService'
import { createEmptySessionState } from '@/features/coding-agent/store/sessionHelpers'
import type { SessionState } from '@/features/coding-agent/store/types'

describe('permissionStateService', () => {
  it('replyPermission 失败时会回滚本地 optimistic 状态', async () => {
    const activeSessionId = ref('s1')
    const sessionStateById: Record<string, SessionState> = {
      s1: createEmptySessionState()
    }
    sessionStateById.s1.permissionCardsById.p1 = {
      id: 'p1',
      sessionID: 's1',
      messageID: '',
      callID: '',
      tool: 'read',
      status: 'pending',
      response: '',
      detail: '等待用户确认权限'
    }

    const getOrCreateSessionState = (sessionID: string) => sessionStateById[sessionID]
    const replyPermission = vi.fn(async () => false)
    const service = createPermissionStateService({
      activeSessionId,
      getActiveAdapter: () => ({ replyPermission }),
      getOrCreateSessionState,
      findPermissionSessionID: () => 's1'
    })

    const ok = await service.replyPermission('p1', 'once')
    expect(ok).toBe(false)
    expect(sessionStateById.s1.permissionCardsById.p1.status).toBe('pending')
    expect(sessionStateById.s1.permissionCardsById.p1.response).toBe('')
  })

  it('upsertQuestionCard 与 clearQuestionsBySession 正常工作', () => {
    const activeSessionId = ref('s2')
    const sessionStateById: Record<string, SessionState> = {
      s2: createEmptySessionState()
    }
    const service = createPermissionStateService({
      activeSessionId,
      getActiveAdapter: () => ({
        replyPermission: async () => true
      }),
      getOrCreateSessionState: (sessionID: string) => sessionStateById[sessionID],
      findPermissionSessionID: () => ''
    })

    service.upsertQuestionCard('s2', {
      id: 'q1',
      sessionID: 's2',
      messageID: 'm1',
      questions: [],
      status: 'pending',
      toolCallID: 'c1'
    })
    expect(Object.keys(sessionStateById.s2.questionCardsById)).toEqual(['q1'])

    service.clearQuestionsBySession('s2')
    expect(Object.keys(sessionStateById.s2.questionCardsById)).toHaveLength(0)
  })

  it('permission.replied 只返回 requestID 时不会覆盖既有 tool/message/call', () => {
    const activeSessionId = ref('s3')
    const sessionStateById: Record<string, SessionState> = {
      s3: createEmptySessionState()
    }
    const service = createPermissionStateService({
      activeSessionId,
      getActiveAdapter: () => ({
        replyPermission: async () => true
      }),
      getOrCreateSessionState: (sessionID: string) => sessionStateById[sessionID],
      findPermissionSessionID: () => 's3'
    })

    service.upsertPermissionCard('s3', {
      id: 'p3',
      sessionID: 's3',
      messageID: 'msg_1',
      callID: 'call_1',
      tool: 'bash',
      status: 'pending',
      detail: '需要执行命令'
    })
    service.upsertPermissionCard('s3', {
      id: 'p3',
      status: 'approved',
      response: 'once',
      messageID: '',
      callID: '',
      tool: '',
      detail: ''
    })

    const card = sessionStateById.s3.permissionCardsById.p3
    expect(card.tool).toBe('bash')
    expect(card.messageID).toBe('msg_1')
    expect(card.callID).toBe('call_1')
    expect(card.status).toBe('approved')
  })
})

