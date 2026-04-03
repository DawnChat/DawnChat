import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { createChatProjectionService } from '@/features/coding-agent/store/chatProjectionService'
import { createEmptySessionState } from '@/features/coding-agent/store/sessionHelpers'
import type { SessionState } from '@/features/coding-agent/store/types'

describe('chatProjectionService', () => {
  it('按时间与 part 顺序输出 chatRows，并能识别流式 reasoning', () => {
    const activeSessionId = ref('s1')
    const state: SessionState = createEmptySessionState()
    state.messagesById.m1 = {
      id: 'm1',
      role: 'assistant',
      time: {
        created: '2026-01-01T00:00:00.000Z'
      }
    }
    state.partsByMessageId.m1 = {
      p2: { id: 'p2', type: 'reasoning', messageID: 'm1', text: 'thinking' },
      p1: { id: 'p1', type: 'text', messageID: 'm1', text: 'hello' }
    } as any
    state.partOrderByMessageId.m1 = {
      p1: 1,
      p2: 2
    }

    const sessionStateById = ref<Record<string, SessionState>>({ s1: state })
    const selectedAgent = ref('build')
    const svc = createChatProjectionService({
      activeSessionId,
      sessionStateById,
      selectedAgent
    })

    expect(svc.orderedMessages.value).toHaveLength(1)
    expect(svc.chatRows.value[0].items.map((item) => item.id)).toEqual(['p1', 'p2'])
    expect(svc.activeReasoningItemId.value).toBe('p2')
  })

  it('plan 模式下，latest finish 为 stop 且此前存在 tool-calls 时可切换 build', () => {
    const activeSessionId = ref('s2')
    const state: SessionState = createEmptySessionState()
    state.messagesById.m1 = {
      id: 'm1',
      role: 'assistant',
      mode: 'plan',
      finish: 'tool-calls',
      time: {
        created: '2026-01-01T00:00:00.000Z',
        completed: '2026-01-01T00:00:01.000Z'
      }
    } as any
    state.messagesById.m2 = {
      id: 'm2',
      role: 'assistant',
      mode: 'plan',
      finish: 'stop',
      time: {
        created: '2026-01-01T00:00:02.000Z',
        completed: '2026-01-01T00:00:03.000Z'
      }
    } as any
    state.partsByMessageId.m1 = {
      t1: { id: 't1', type: 'tool', messageID: 'm1', tool: 'read' }
    } as any
    state.partOrderByMessageId.m1 = { t1: 1 }

    const sessionStateById = ref<Record<string, SessionState>>({ s2: state })
    const selectedAgent = ref('plan')
    const svc = createChatProjectionService({
      activeSessionId,
      sessionStateById,
      selectedAgent
    })

    expect(svc.canSwitchPlanToBuild.value).toBe(true)
  })

  it('tool error 场景映射完整 input 与 error 字段', () => {
    const activeSessionId = ref('s3')
    const state: SessionState = createEmptySessionState()
    state.messagesById.m1 = {
      id: 'm1',
      role: 'assistant',
      time: {
        created: '2026-01-01T00:00:00.000Z'
      }
    }
    state.partsByMessageId.m1 = {
      t1: {
        id: 't1',
        type: 'tool',
        messageID: 'm1',
        tool: 'bash',
        state: {
          status: 'error',
          input: {
            command: 'ls -la'
          },
          error: 'permission denied',
          output: 'this output should not override error'
        }
      }
    } as any
    state.partOrderByMessageId.m1 = { t1: 1 }

    const sessionStateById = ref<Record<string, SessionState>>({ s3: state })
    const selectedAgent = ref('build')
    const svc = createChatProjectionService({
      activeSessionId,
      sessionStateById,
      selectedAgent
    })
    const toolItem = svc.chatRows.value[0]?.items[0]
    expect(toolItem?.type).toBe('tool')
    expect(toolItem?.toolDisplay?.hasInput).toBe(true)
    expect(toolItem?.toolDisplay?.hasError).toBe(true)
    expect(toolItem?.toolDisplay?.fullErrorText).toContain('permission denied')
    expect(toolItem?.toolDisplay?.detailsText).toContain('permission denied')
  })
})

