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

  it('tool state.title 优先作为展示标题，缺失时回退 summary/toolName', () => {
    const activeSessionId = ref('s4')
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
          status: 'completed',
          title: '查看当前工作路径',
          input: {
            command: 'pwd'
          },
          output: '/tmp/workspace',
          metadata: {},
          time: {
            start: 1,
            end: 2
          }
        }
      },
      t2: {
        id: 't2',
        type: 'tool',
        messageID: 'm1',
        tool: 'glob',
        state: {
          status: 'completed',
          input: {
            pattern: '**/*.spec.ts'
          },
          output: '/a.spec.ts\n/b.spec.ts',
          metadata: {},
          time: {
            start: 1,
            end: 2
          }
        }
      }
    } as any
    state.partOrderByMessageId.m1 = { t1: 1, t2: 2 }

    const sessionStateById = ref<Record<string, SessionState>>({ s4: state })
    const selectedAgent = ref('build')
    const svc = createChatProjectionService({
      activeSessionId,
      sessionStateById,
      selectedAgent
    })

    const first = svc.chatRows.value[0]?.items[0]
    const second = svc.chatRows.value[0]?.items[1]
    expect(first?.toolDisplay?.title).toBe('查看当前工作路径')
    expect(second?.toolDisplay?.title).toBe('glob 匹配文件: **/*.spec.ts')
  })

  it('当 state.title 为空时，优先使用 MCP output 中的 display.title', () => {
    const activeSessionId = ref('s5')
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
        tool: 'dawnchat_ui_bridge_dawnchat_ui_runtime_refresh',
        state: {
          status: 'completed',
          input: {
            plugin_id: 'com.demo.plugin'
          },
          output: JSON.stringify({
            ok: true,
            display: {
              title: '刷新预览并确认 UI 已更新'
            }
          }),
          metadata: {},
          time: {
            start: 1,
            end: 2
          }
        }
      }
    } as any
    state.partOrderByMessageId.m1 = { t1: 1 }

    const sessionStateById = ref<Record<string, SessionState>>({ s5: state })
    const selectedAgent = ref('build')
    const svc = createChatProjectionService({
      activeSessionId,
      sessionStateById,
      selectedAgent
    })

    const tool = svc.chatRows.value[0]?.items[0]
    expect(tool?.toolDisplay?.title).toBe('刷新预览并确认 UI 已更新')
  })
})

