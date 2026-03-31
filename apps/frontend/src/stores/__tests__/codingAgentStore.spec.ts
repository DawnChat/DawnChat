import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useCodingAgentStore } from '@/features/coding-agent'
import type { CodingAgentEvent } from '@/services/coding-agent/engineAdapter'

const { mockAdapter } = vi.hoisted(() => {
  return {
    mockAdapter: {
      listSessions: vi.fn<(...args: any[]) => Promise<any[]>>(),
      getSession: vi.fn<(...args: any[]) => Promise<any>>(),
      createSession: vi.fn<(...args: any[]) => Promise<string>>(),
      updateSession: vi.fn<(...args: any[]) => Promise<any>>(),
      deleteSession: vi.fn<(...args: any[]) => Promise<boolean>>(),
      listMessages: vi.fn<(...args: any[]) => Promise<any[]>>(),
      prompt: vi.fn<(...args: any[]) => Promise<any>>(),
      promptAsync: vi.fn<(...args: any[]) => Promise<void>>(),
      interruptSession: vi.fn<(...args: any[]) => Promise<boolean>>(),
      injectContext: vi.fn<(...args: any[]) => Promise<void>>(),
      replyPermission: vi.fn<(...args: any[]) => Promise<boolean>>(),
      listPermissions: vi.fn<(...args: any[]) => Promise<any[]>>(),
      supportsQuestions: vi.fn<(...args: any[]) => boolean>(),
      listQuestions: vi.fn<(...args: any[]) => Promise<any[]>>(),
      replyQuestion: vi.fn<(...args: any[]) => Promise<boolean>>(),
      rejectQuestion: vi.fn<(...args: any[]) => Promise<boolean>>(),
      subscribeEvents: vi.fn<(...args: any[]) => Promise<() => void>>()
    }
  }
})

vi.mock('@/services/coding-agent/adapterRegistry', () => ({
  ENGINE_AGENTV3: 'agentv3',
  ENGINE_OPENCODE: 'opencode',
  isEngineId: (value: string) => ['opencode', 'agentv3'].includes(value),
  getEngineAdapter: () => mockAdapter
}))

function createFetchResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data)
  } as Response
}

describe('codingAgentStore', () => {
  let capturedEventHandler: ((evt: CodingAgentEvent) => void) | null = null

  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    capturedEventHandler = null

    mockAdapter.listSessions.mockResolvedValue([])
    mockAdapter.getSession.mockResolvedValue(null)
    mockAdapter.createSession.mockResolvedValue('ses_test_1')
    mockAdapter.updateSession.mockResolvedValue(null)
    mockAdapter.deleteSession.mockResolvedValue(true)
    mockAdapter.listMessages.mockResolvedValue([])
    mockAdapter.injectContext.mockResolvedValue()
    mockAdapter.prompt.mockResolvedValue(null)
    mockAdapter.promptAsync.mockResolvedValue()
    mockAdapter.interruptSession.mockResolvedValue(true)
    mockAdapter.replyPermission.mockResolvedValue(true)
    mockAdapter.listPermissions.mockResolvedValue([])
    mockAdapter.supportsQuestions.mockReturnValue(true)
    mockAdapter.listQuestions.mockResolvedValue([])
    mockAdapter.replyQuestion.mockResolvedValue(true)
    mockAdapter.rejectQuestion.mockResolvedValue(true)
    mockAdapter.subscribeEvents.mockImplementation(async (handler: (evt: CodingAgentEvent) => void) => {
      capturedEventHandler = handler
      return () => {}
    })

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (/\/api\/plugins\//.test(url)) {
          const isWeb = url.includes('com.dawnchat.web-starter')
          return createFetchResponse({
            status: 'success',
            plugin: {
              id: isWeb ? 'com.dawnchat.web-starter' : 'com.dawnchat.hello-world-vue',
              app_type: isWeb ? 'web' : 'desktop',
              plugin_path: isWeb ? '/tmp/web-plugin' : '/tmp/desktop-plugin'
            }
          })
        }
        if (url.includes('/api/workbench/projects/proj_1')) {
          return createFetchResponse({
            status: 'success',
            data: {
              id: 'proj_1',
              name: 'Workbench Project',
              project_type: 'chat',
              workspace_path: '/tmp/workbench/proj_1',
              created_at: '2026-01-01T00:00:00.000Z',
              updated_at: '2026-01-02T00:00:00.000Z'
            }
          })
        }
        if (url.includes('/api/opencode/start_with_workspace')) {
          const requestBody = String(init?.body || '')
          const isWorkbench = requestBody.includes('"workspace_kind":"workbench-general"')
          const isWebPlugin = requestBody.includes('"plugin_id":"com.dawnchat.web-starter"')
          return createFetchResponse({
            status: 'success',
            data: {
              status: 'running',
              healthy: true,
              base_url: 'http://127.0.0.1:4096',
              workspace_profile: isWorkbench
                ? {
                    id: 'workbench:proj_1',
                    kind: 'workbench-general',
                    display_name: 'Workbench Project',
                    app_type: 'chat',
                    workspace_path: '/tmp/workbench/proj_1',
                    preferred_entry: '',
                    preferred_directories: [],
                    hints: [],
                    default_agent: 'general',
                    session_strategy: 'single',
                    project_id: 'proj_1'
                  }
                : isWebPlugin
                  ? {
                      plugin_id: 'com.dawnchat.web-starter',
                      app_type: 'web',
                      workspace_path: '/tmp/web-plugin',
                      preferred_entry: 'web-src/src/App.vue',
                      preferred_directories: [
                        'web-src/src',
                        'web-src/src/components',
                        'web-src/src/views',
                        'web-src/src/composables',
                        'web-src/src/stores'
                      ],
                      hints: [
                        '这是纯前端 web 插件，请优先修改 web-src 下的 Vue 代码。',
                        '不要假设项目中存在 Python 后端或桌面端入口。'
                      ],
                      default_agent: 'build',
                      session_strategy: 'multi'
                    }
                  : {
                    app_type: 'desktop',
                    workspace_path: '/tmp/desktop-plugin',
                    preferred_entry: 'src/main.py',
                    preferred_directories: ['src'],
                    hints: [],
                    default_agent: 'build',
                    session_strategy: 'multi'
                  }
            }
          })
        }
        if (url.includes('/api/opencode/config/providers')) {
          return createFetchResponse({
            status: 'success',
            data: {
              providers: [
                {
                  id: 'google',
                  configured: false,
                  available: false,
                  models: { 'gemini-3-flash-preview': { name: 'Gemini 3 Flash Preview' } }
                },
                {
                  id: 'dawnchat-local',
                  configured: true,
                  available: true,
                  models: { 'qwen2.5-coder': { name: 'Qwen2.5 Coder' } }
                }
              ]
            }
          })
        }
        if (url.includes('/api/opencode/agents')) {
          return createFetchResponse({
            status: 'success',
            data: [{ id: 'build' }, { id: 'plan' }]
          })
        }
        if (url.includes('/api/opencode/rules')) {
          return createFetchResponse({
            status: 'success',
            data: {
              enabled: true,
              current_version: '1.0.0'
            }
          })
        }
        if (url.includes('/api/opencode/config')) {
          return createFetchResponse({ status: 'success' })
        }
        if (url.includes('/api/opencode/diagnostics')) {
          return createFetchResponse({ status: 'success', data: {} })
        }
        throw new Error(`unexpected fetch: ${url}`)
      })
    )
  })

  it('引擎选项仅包含 OpenCode 与 AgentV3', () => {
    const store = useCodingAgentStore()
    expect(store.engineOptions.map((item) => item.id)).toEqual(['opencode', 'agentv3'])
  })

  it('使用 workspace 初始化时不会触发 /api/opencode/start 回退', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })

    const fetchMock = vi.mocked(globalThis.fetch)
    const allUrls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(allUrls.some((url) => url.includes('/api/opencode/start_with_workspace'))).toBe(true)
    expect(allUrls.some((url) => /\/api\/opencode\/start(?:\?|$)/.test(url))).toBe(false)
    expect(store.selectedModelId).toBe('dawnchat-local/qwen2.5-coder')
    expect(store.activeSessionId).toBe('ses_test_1')
  })

  it('新建会话失败时会写入可见错误', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    mockAdapter.createSession.mockRejectedValueOnce(new Error('boom'))

    await expect(store.createSession('New Chat', false)).rejects.toThrow('boom')
    expect(store.lastError).toContain('创建会话失败')
  })

  it('能从嵌套 session.error payload 中提取可读错误', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'session.error',
      properties: {
        sessionID: 'ses_test_1',
        error: {
          error: {
            message: 'Google Generative AI API key is missing'
          }
        }
      }
    })

    expect(store.lastError).toBe('Google Generative AI API key is missing')
  })

  it('能从 error.data.message 提取连接失败细节', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'session.error',
      properties: {
        sessionID: 'ses_test_1',
        error: {
          name: 'UnknownError',
          data: {
            message: 'Error: Unable to connect. Is the computer able to access the url?'
          }
        }
      }
    })

    expect(store.lastError).toBe('Error: Unable to connect. Is the computer able to access the url?')
  })

  it('session.error 会生成可见 assistant 错误消息', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'session.error',
      properties: {
        sessionID: 'ses_test_1',
        message: 'unknown: Unable to convert openai tool calls to gemini tool calls'
      }
    })

    expect(store.lastError).toContain('参数格式不兼容')
    const visibleTextItems = store.chatRows.flatMap((row) => row.items).filter((item) => item.type === 'text')
    expect(visibleTextItems.some((item) => String(item.text || '').includes('参数格式不兼容'))).toBe(true)
  })

  it('能处理 permission 事件并发起权限响应', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'permission.asked',
      properties: {
        sessionID: 'ses_test_1',
        permission: {
          id: 'perm_1',
          tool: 'edit',
          message: '允许编辑 src/App.vue'
        }
      }
    })

    expect(store.permissionCards.length).toBe(1)
    expect(store.permissionCards[0].id).toBe('perm_1')
    expect(store.permissionCards[0].status).toBe('pending')

    await store.replyPermission('perm_1', 'once')
    expect(mockAdapter.replyPermission).toHaveBeenCalledWith('ses_test_1', 'perm_1', 'once', undefined)
  })

  it('能处理 OpenCode 扁平 permission 事件并映射回复状态', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'permission.asked',
      properties: {
        id: 'per_flat_1',
        sessionID: 'ses_test_1',
        permission: 'external_directory',
        patterns: ['/tmp/*'],
        metadata: { filepath: '/tmp/demo.txt' }
      }
    })

    expect(store.permissionCards.length).toBe(1)
    expect(store.permissionCards[0].tool).toBe('external_directory')
    expect(store.permissionCards[0].detail).toContain('/tmp/demo.txt')
    expect(store.permissionCards[0].status).toBe('pending')

    capturedEventHandler?.({
      type: 'permission.replied',
      properties: {
        requestID: 'per_flat_1',
        reply: 'reject'
      }
    })

    expect(store.permissionCards[0].status).toBe('rejected')
    expect(store.permissionCards[0].response).toBe('reject')
  })

  it('reconcileMessages 后会恢复 pending permission 卡片', async () => {
    mockAdapter.listPermissions.mockResolvedValue([
      {
        id: 'per_reconcile_1',
        sessionID: 'ses_test_1',
        permission: 'external_directory',
        patterns: ['/Users/demo/*'],
        metadata: { filepath: '/Users/demo/notes.txt' }
      }
    ])
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })

    expect(store.permissionCards.length).toBe(1)
    expect(store.permissionCards[0].id).toBe('per_reconcile_1')
    expect(store.permissionCards[0].tool).toBe('external_directory')
  })

  it('能处理 question 事件并发起答复/拒绝', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'question.asked',
      properties: {
        id: 'que_1',
        sessionID: 'ses_test_1',
        questions: [
          {
            header: 'Q1',
            question: '选择一个',
            options: [{ label: 'A', description: '选项A' }]
          }
        ]
      }
    })

    expect(store.questionCards.length).toBe(1)
    expect(store.questionCards[0].id).toBe('que_1')

    await store.replyQuestion('que_1', [['A']])
    expect(mockAdapter.replyQuestion).toHaveBeenCalledWith('que_1', [['A']])

    capturedEventHandler?.({
      type: 'question.asked',
      properties: {
        id: 'que_2',
        sessionID: 'ses_test_1',
        questions: [
          {
            header: 'Q2',
            question: '是否继续',
            options: [{ label: '继续', description: '' }]
          }
        ]
      }
    })

    await store.rejectQuestion('que_2')
    expect(mockAdapter.rejectQuestion).toHaveBeenCalledWith('que_2')
  })

  it('会按 sessionID 路由事件并避免串会话', async () => {
    const store = useCodingAgentStore()
    mockAdapter.listSessions.mockResolvedValueOnce([
      {
        id: 'ses_a',
        title: 'A',
        time: { created: '2026-01-01T00:00:00.000Z', updated: '2026-01-01T00:00:00.000Z' }
      },
      {
        id: 'ses_b',
        title: 'B',
        time: { created: '2026-01-02T00:00:00.000Z', updated: '2026-01-02T00:00:00.000Z' }
      }
    ])
    mockAdapter.listMessages.mockImplementation(async (sessionId: string) => {
      if (sessionId === 'ses_a') {
        return [
          {
            info: {
              id: 'msg_a_1',
              role: 'assistant',
              time: { created: '2026-01-03T00:00:00.000Z' }
            },
            parts: [{ id: 'part_a_1', messageID: 'msg_a_1', type: 'text', text: 'A message' }]
          }
        ]
      }
      return []
    })

    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(store.activeSessionId).toBe('ses_b')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_a',
        info: {
          id: 'msg_a_1',
          role: 'assistant',
          time: { created: '2026-01-03T00:00:00.000Z' }
        }
      }
    })

    expect(store.chatRows.length).toBe(0)

    await store.switchSession('ses_a')
    expect(store.activeSessionId).toBe('ses_a')
    expect(store.chatRows.length).toBe(1)
  })

  it('切换插件预览时只展示当前工作区的 opencode sessions', async () => {
    const store = useCodingAgentStore()
    mockAdapter.listSessions.mockImplementation(
      async (options?: {
        directory?: string
      }) => {
        expect(options?.directory).toBeTruthy()
        return [
          {
            id: 'ses_plugin_a_1',
            title: 'Plugin A 1',
            directory: '/tmp/desktop-plugin',
            time: { created: '2026-01-01T00:00:00.000Z', updated: '2026-01-01T00:00:00.000Z' }
          },
          {
            id: 'ses_plugin_a_2',
            title: 'Plugin A 2',
            directory: '/tmp/desktop-plugin',
            time: { created: '2026-01-02T00:00:00.000Z', updated: '2026-01-02T00:00:00.000Z' }
          },
          {
            id: 'ses_plugin_b_1',
            title: 'Plugin B 1',
            directory: '/tmp/web-plugin',
            time: { created: '2026-01-03T00:00:00.000Z', updated: '2026-01-03T00:00:00.000Z' }
          }
        ]
      }
    )

    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(store.sessions.map((item) => item.id)).toEqual(['ses_plugin_a_2', 'ses_plugin_a_1'])
    expect(store.activeSessionId).toBe('ses_plugin_a_2')

    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.web-starter' })
    expect(store.sessions.map((item) => item.id)).toEqual(['ses_plugin_b_1'])
    expect(store.activeSessionId).toBe('ses_plugin_b_1')

    const directoryCalls = mockAdapter.listSessions.mock.calls.map((call) => call[0]?.directory || '')
    expect(directoryCalls).toContain('/tmp/desktop-plugin')
    expect(directoryCalls).toContain('/tmp/web-plugin')
    expect(directoryCalls.at(-1)).toBe('/tmp/web-plugin')
  })

  it('切换引擎会重置状态并持久化 selectedEngine', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(store.isReady).toBe(true)

    store.selectEngine('agentv3')

    expect(store.selectedEngine).toBe('agentv3')
    expect(store.isReady).toBe(false)
    expect(localStorage.getItem('codingAgent:selectedEngine')).toBe('agentv3')
  })

  it('收到 session.updated 事件后会覆盖默认 New Chat 标题', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    expect(store.sessions.find((item) => item.id === 'ses_test_1')?.title).toBe('New Chat')

    capturedEventHandler?.({
      type: 'session.updated',
      properties: {
        session: {
          id: 'ses_test_1',
          title: 'Refactor plugin toolbar',
          time: {
            created: '2026-01-01T00:00:00.000Z',
            updated: '2026-01-01T00:05:00.000Z'
          }
        }
      }
    })

    expect(store.sessions.find((item) => item.id === 'ses_test_1')?.title).toBe('Refactor plugin toolbar')
  })

  it('opencode 会忽略来自其他工作区的 session.updated 事件', async () => {
    const store = useCodingAgentStore()
    mockAdapter.listSessions.mockResolvedValueOnce([
      {
        id: 'ses_plugin_a',
        title: 'Plugin A',
        directory: '/tmp/desktop-plugin',
        time: { created: '2026-01-01T00:00:00.000Z', updated: '2026-01-01T00:00:00.000Z' }
      }
    ])

    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(store.sessions.map((item) => item.id)).toEqual(['ses_plugin_a'])

    capturedEventHandler?.({
      type: 'session.updated',
      properties: {
        session: {
          id: 'ses_plugin_b',
          title: 'Plugin B',
          directory: '/tmp/web-plugin',
          time: {
            created: '2026-01-01T00:00:00.000Z',
            updated: '2026-01-01T00:05:00.000Z'
          }
        }
      }
    })

    expect(store.sessions.map((item) => item.id)).toEqual(['ses_plugin_a'])
  })

  it('agentv3 发送消息时会携带 plugin_id', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    await store.sendText('hello v3', { pluginId: 'com.dawnchat.hello-world-vue' })

    expect(mockAdapter.promptAsync).toHaveBeenCalled()
    const [, payload] = mockAdapter.promptAsync.mock.calls.at(-1) || []
    expect(payload?.plugin_id).toBe('com.dawnchat.hello-world-vue')
    expect(typeof payload?.system).toBe('string')
    expect(String(payload?.system || '')).toContain('当前插件开发目标: com.dawnchat.hello-world-vue')
  })

  it('workbench-general 初始化会走独立 project 链路并绑定 projectId', async () => {
    const store = useCodingAgentStore()
    mockAdapter.listSessions.mockResolvedValueOnce([
      {
        id: 'ses_workbench_1',
        title: 'Workbench Session',
        workspace_path: '/tmp/workbench/proj_1',
        workspace_kind: 'workbench-general',
        project_id: 'proj_1',
        time: { created: '2026-01-01T00:00:00.000Z', updated: '2026-01-02T00:00:00.000Z' }
      }
    ])

    await store.ensureReadyWithWorkspace({
      workspaceTarget: {
        id: 'workbench:proj_1',
        kind: 'workbench-general',
        displayName: 'Workbench Project',
        appType: 'chat',
        workspacePath: '/tmp/workbench/proj_1',
        preferredEntry: '',
        preferredDirectories: [],
        hints: [],
        defaultAgent: 'general',
        sessionStrategy: 'single',
        projectId: 'proj_1'
      }
    })

    const fetchMock = vi.mocked(globalThis.fetch)
    const startCall = fetchMock.mock.calls.find((call) => String(call[0]).includes('/api/opencode/start_with_workspace'))
    expect(startCall).toBeTruthy()
    const body = startCall?.[1] && 'body' in startCall[1] ? String(startCall[1].body || '') : ''
    expect(body).toContain('"workspace_kind":"workbench-general"')
    expect(body).toContain('"project_id":"proj_1"')
    expect(store.boundWorkspaceTarget?.projectId).toBe('proj_1')
    expect(store.boundWorkspaceTarget?.kind).toBe('workbench-general')
  })

  it('agentv3 在 workbench-general 下发送消息时会携带 project 绑定字段', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({
      workspaceTarget: {
        id: 'workbench:proj_1',
        kind: 'workbench-general',
        displayName: 'Workbench Project',
        appType: 'chat',
        workspacePath: '/tmp/workbench/proj_1',
        preferredEntry: '',
        preferredDirectories: [],
        hints: [],
        defaultAgent: 'general',
        sessionStrategy: 'single',
        projectId: 'proj_1'
      }
    })
    await store.sendText('hello workbench', {
      workspaceTarget: {
        id: 'workbench:proj_1',
        kind: 'workbench-general',
        displayName: 'Workbench Project',
        appType: 'chat',
        workspacePath: '/tmp/workbench/proj_1',
        preferredEntry: '',
        preferredDirectories: [],
        hints: [],
        defaultAgent: 'general',
        sessionStrategy: 'single',
        projectId: 'proj_1'
      }
    })

    const [, payload] = mockAdapter.promptAsync.mock.calls.at(-1) || []
    expect(payload?.project_id).toBe('proj_1')
    expect(payload?.workspace_kind).toBe('workbench-general')
    expect(payload?.workspace_path).toBe('/tmp/workbench/proj_1')
  })

  it('web 插件会注入偏向 web-src 的系统提示词', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.web-starter' })
    await store.sendText('update hero section', { pluginId: 'com.dawnchat.web-starter' })

    const [, payload] = mockAdapter.promptAsync.mock.calls.at(-1) || []
    expect(String(payload?.system || '')).toContain('插件类型: web')
    expect(String(payload?.system || '')).toContain('web-src/src/App.vue')
    expect(String(payload?.system || '')).toContain('纯前端 web 插件')
    expect(String(payload?.system || '')).not.toContain('src/main.py')
  })

  it('能归并 reasoning delta 并对重复 delta 做最小幂等处理', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_reasoning_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-03T00:00:00.000Z' }
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.delta',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_reasoning_1',
        partID: 'part_reasoning_1',
        partType: 'reasoning',
        field: 'text',
        delta: 'thinking...',
        trace_id: 'trace_a',
        run_id: 'run_a',
        step: 1
      }
    })
    capturedEventHandler?.({
      type: 'message.part.delta',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_reasoning_1',
        partID: 'part_reasoning_1',
        partType: 'reasoning',
        field: 'text',
        delta: 'thinking...'
      }
    })

    const row = store.chatRows.find((item) => item.info.id === 'msg_reasoning_1')
    const reasoning = row?.items.find((item) => item.id === 'part_reasoning_1')
    expect(reasoning?.type).toBe('reasoning')
    expect(reasoning?.text).toBe('thinking...')
  })

  it('session.error 包含工具序列异常时会展示可读提示且允许继续发送', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'session.error',
      properties: {
        sessionID: 'ses_test_1',
        message: 'unknown: Missing corresponding tool call for tool response message'
      }
    })

    expect(store.lastError).toContain('模型工具调用序列异常')

    await store.sendText('retry request', { pluginId: 'com.dawnchat.hello-world-vue' })
    expect(mockAdapter.promptAsync).toHaveBeenCalled()
  })

  it('能展示 step-start/step-finish 并保持与文本 part 的顺序稳定', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_step_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-04T00:00:00.000Z' }
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_step_start_1',
          type: 'step-start',
          messageID: 'msg_step_1',
          reason: '开始探索工程结构'
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.delta',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_step_1',
        partID: 'part_text_1',
        partType: 'text',
        field: 'text',
        delta: 'hello'
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_step_finish_1',
          type: 'step-finish',
          messageID: 'msg_step_1',
          reason: '完成探索工程结构'
        }
      }
    })

    const row = store.chatRows.find((item) => item.info.id === 'msg_step_1')
    expect(row).toBeTruthy()
    expect(row?.items.map((item) => item.type)).toEqual(['step', 'text', 'step'])
    expect(row?.items[1]?.text).toBe('hello')
  })

  it('会过滤无信息量的 step 文案，减少消息噪声', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_step_noise_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-05T10:00:00.000Z' }
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_step_noise_start_1',
          type: 'step-start',
          messageID: 'msg_step_noise_1',
          reason: '步骤开始执行'
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_step_noise_finish_1',
          type: 'step-finish',
          messageID: 'msg_step_noise_1',
          reason: 'tool-calls'
        }
      }
    })

    const row = store.chatRows.find((item) => item.info.id === 'msg_step_noise_1')
    expect(row).toBeTruthy()
    expect((row?.items || []).every((item) => item.type !== 'step')).toBe(true)
  })

  it('会保留带错误细节的 step 结果', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_step_error_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-05T11:00:00.000Z' }
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_step_error_finish_1',
          type: 'step-finish',
          messageID: 'msg_step_error_1',
          reason: '步骤终止: stream_error'
        }
      }
    })

    const row = store.chatRows.find((item) => item.info.id === 'msg_step_error_1')
    expect(row).toBeTruthy()
    expect(row?.items.some((item) => item.type === 'step' && String(item.text || '').includes('步骤终止'))).toBe(true)
  })

  it('能将 tool.input.start/delta/end 渲染为可见工具项并展示参数预览', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_tool_input_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-05T00:00:00.000Z' }
        }
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.start',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_input_1',
        partID: 'part_tool_input_1',
        callID: 'call_123'
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.delta',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_input_1',
        partID: 'part_tool_input_1',
        callID: 'call_123',
        toolName: 'read',
        rawArguments: '{"file_path":"src/App.vue"}'
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.end',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_input_1',
        partID: 'part_tool_input_1',
        callID: 'call_123',
        toolName: 'read',
        rawArguments: '{"file_path":"src/App.vue"}'
      }
    })

    const row = store.chatRows.find((item) => item.info.id === 'msg_tool_input_1')
    const toolItem = row?.items.find((item) => item.id === 'part_tool_input_1')
    expect(toolItem?.type).toBe('tool')
    expect(toolItem?.tool).toBe('read')
    expect(String(toolItem?.toolDisplay?.title || '')).toContain('read')
    expect(String(toolItem?.toolDisplay?.title || '')).toContain('App.vue')
    expect(toolItem?.toolDisplay?.renderMode).toBe('inline')
  })

  it('glob 工具在仅有参数预览时按 inline 展示，并保留可读标题', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_tool_glob_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-05T12:00:00.000Z' }
        }
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.start',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_glob_1',
        partID: 'part_tool_glob_1',
        callID: 'call_glob_1'
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.delta',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_glob_1',
        partID: 'part_tool_glob_1',
        callID: 'call_glob_1',
        toolName: 'glob',
        rawArguments: '{"pattern":"**/*.spec.ts","path":"apps/frontend/src"}'
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.end',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_glob_1',
        partID: 'part_tool_glob_1',
        callID: 'call_glob_1',
        toolName: 'glob',
        rawArguments: '{"pattern":"**/*.spec.ts","path":"apps/frontend/src"}'
      }
    })

    const row = store.chatRows.find((item) => item.info.id === 'msg_tool_glob_1')
    const toolItem = row?.items.find((item) => item.id === 'part_tool_glob_1')
    expect(toolItem?.type).toBe('tool')
    expect(toolItem?.toolDisplay?.renderMode).toBe('inline')
    expect(String(toolItem?.toolDisplay?.summary || '')).toContain('glob 匹配文件')
  })

  it('read 参数展示在 opencode/agentv3 下都使用文件名而非绝对路径', async () => {
    for (const engine of ['opencode', 'agentv3'] as const) {
      const store = useCodingAgentStore()
      store.selectEngine(engine)
      await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
      expect(capturedEventHandler).toBeTypeOf('function')

      capturedEventHandler?.({
        type: 'message.updated',
        properties: {
          sessionID: 'ses_test_1',
          info: {
            id: `msg_tool_read_${engine}`,
            role: 'assistant',
            sessionID: 'ses_test_1',
            time: { created: '2026-01-05T12:16:00.000Z' }
          }
        }
      })
      capturedEventHandler?.({
        type: 'message.part.updated',
        properties: {
          sessionID: 'ses_test_1',
          part: {
            id: `part_tool_read_${engine}`,
            messageID: `msg_tool_read_${engine}`,
            type: 'tool',
            tool: 'read',
            state: {
              status: 'completed',
              input: { filePath: '/Users/zhutao/Cursor/ZenMind/apps/frontend/src/App.vue', startLine: 10, endLine: 24 },
              output: '<content>\n10:<template>\n11:<div>ok</div>\n</content>'
            }
          }
        }
      })

      const row = store.chatRows.find((item) => item.info.id === `msg_tool_read_${engine}`)
      const toolItem = row?.items.find((item) => item.id === `part_tool_read_${engine}`)
      expect(toolItem?.toolDisplay?.argsPreview).toContain('App.vue:10-24')
      expect(String(toolItem?.toolDisplay?.argsPreview || '')).not.toContain('/Users/zhutao/')
      expect(String(toolItem?.toolDisplay?.summary || '')).toContain('read App.vue:10-24')
    }
  })

  it('search/read/write 在存在更多信息时会转为可折叠展示', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_tool_search_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-05T12:10:00.000Z' }
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_tool_search_1',
          messageID: 'msg_tool_search_1',
          type: 'tool',
          tool: 'search',
          state: {
            status: 'completed',
            input: { pattern: 'PluginDev' },
            output: 'found 12 matches in 3 files'
          }
        }
      }
    })

    const row = store.chatRows.find((item) => item.info.id === 'msg_tool_search_1')
    const toolItem = row?.items.find((item) => item.id === 'part_tool_search_1')
    expect(toolItem?.type).toBe('tool')
    expect(toolItem?.toolDisplay?.kind).toBe('search')
    expect(toolItem?.toolDisplay?.hasDetails).toBe(true)
    expect(toolItem?.toolDisplay?.renderMode).toBe('collapsible')
  })

  it('read 工具会清洗 <content> 包裹与 eof 噪声，并提供 codeLines', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_tool_read_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-05T12:15:00.000Z' }
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_tool_read_1',
          messageID: 'msg_tool_read_1',
          type: 'tool',
          tool: 'read',
          state: {
            status: 'completed',
            input: { filePath: 'src/App.vue' },
            output:
              '<path>/tmp/src/App.vue</path>\n<type>file</type>\n<content>\n1: <template>\n2:   <div>ok</div>\n\n(End of file - total 2 lines)\n</content>'
          }
        }
      }
    })

    const row = store.chatRows.find((item) => item.info.id === 'msg_tool_read_1')
    const toolItem = row?.items.find((item) => item.id === 'part_tool_read_1')
    expect(toolItem?.toolDisplay?.kind).toBe('read')
    expect(toolItem?.toolDisplay?.detailsText).not.toContain('</content>')
    expect(toolItem?.toolDisplay?.detailsText).not.toContain('End of file')
    expect(Array.isArray(toolItem?.toolDisplay?.codeLines)).toBe(true)
    expect(toolItem?.toolDisplay?.codeLines?.[0]).toContain('<template>')
  })

  it('write 工具与 permission 解耦后，permission 仅以独立卡片展示', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_tool_write_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-05T12:20:00.000Z' }
        }
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.start',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_write_1',
        partID: 'part_tool_write_1',
        callID: 'call_write_1'
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.delta',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_write_1',
        partID: 'part_tool_write_1',
        callID: 'call_write_1',
        toolName: 'write',
        rawArguments: '{"filePath":"src/App.vue","content":"next"}'
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.end',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_write_1',
        partID: 'part_tool_write_1',
        callID: 'call_write_1',
        toolName: 'write',
        rawArguments: '{"filePath":"src/App.vue","content":"next"}'
      }
    })
    capturedEventHandler?.({
      type: 'permission.asked',
      properties: {
        sessionID: 'ses_test_1',
        permission: {
          id: 'perm_write_1',
          tool: 'edit',
          metadata: {
            filepath: 'src/App.vue',
            diff: '@@\n-old line\n+new line'
          },
          toolRef: {
            messageID: 'msg_tool_write_1',
            callID: 'call_write_1'
          },
          messageID: 'msg_tool_write_1',
          callID: 'call_write_1'
        }
      }
    })

    const timelineTool = store.timelineItems.find(
      (item) => item.kind === 'part' && item.item.id === 'part_tool_write_1'
    )
    const display = timelineTool && timelineTool.kind === 'part' ? timelineTool.item.toolDisplay : undefined
    expect(String(display?.diffStat || '')).toBe('')
    const standalonePermission = store.timelineItems.find(
      (item) => item.kind === 'permission' && item.permission.id === 'perm_write_1'
    )
    expect(standalonePermission).toBeTruthy()
  })

  it('permission 仅有 callId 时也保持独立卡片展示', async () => {
    const store = useCodingAgentStore()
    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_tool_bash_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-05T12:21:00.000Z' }
        }
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.start',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_bash_1',
        partID: 'part_tool_bash_1',
        callID: 'call_bash_1'
      }
    })
    capturedEventHandler?.({
      type: 'tool.input.end',
      properties: {
        sessionID: 'ses_test_1',
        messageID: 'msg_tool_bash_1',
        partID: 'part_tool_bash_1',
        callID: 'call_bash_1',
        toolName: 'bash',
        rawArguments: '{"command":"ls -la"}'
      }
    })
    capturedEventHandler?.({
      type: 'permission.asked',
      properties: {
        sessionID: 'ses_test_1',
        permission: {
          id: 'perm_bash_1',
          permission: 'bash',
          callId: 'call_bash_1',
          message: '需要执行命令',
          patterns: ['ls -la']
        }
      }
    })

    const standalonePermission = store.timelineItems.find(
      (item) => item.kind === 'permission' && item.permission.id === 'perm_bash_1'
    )
    expect(standalonePermission).toBeTruthy()
  })

  it('permission 无法关联 tool 时也必须以独立卡片展示', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'permission.asked',
      properties: {
        sessionID: 'ses_test_1',
        permission: {
          id: 'perm_orphan_1',
          permission: 'bash',
          message: '需要执行命令'
        }
      }
    })

    const standalonePermission = store.timelineItems.find(
      (item) => item.kind === 'permission' && item.permission.id === 'perm_orphan_1'
    )
    expect(standalonePermission).toBeTruthy()
  })

  it('运行中长时间静默不会再由 watchdog 误触发 reconcile', async () => {
    vi.useFakeTimers()
    try {
      const store = useCodingAgentStore()
      store.selectEngine('agentv3')
      await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
      await store.sendText('keep streaming', { pluginId: 'com.dawnchat.hello-world-vue' })
      const baselineCalls = mockAdapter.listMessages.mock.calls.length

      vi.advanceTimersByTime(20000)
      capturedEventHandler?.({
        type: 'run.progress',
        properties: {
          sessionID: 'ses_test_1',
          detail: 'still running'
        }
      })
      await Promise.resolve()
      vi.advanceTimersByTime(10000)
      await Promise.resolve()
      expect(mockAdapter.listMessages.mock.calls.length).toBe(baselineCalls)

      vi.advanceTimersByTime(26000)
      await Promise.resolve()
      expect(mockAdapter.listMessages.mock.calls.length).toBe(baselineCalls)
    } finally {
      vi.useRealTimers()
    }
  })

  it('sendText 会通过 payload.system 发送工作区规则上下文，且不再调用 injectContext', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    mockAdapter.injectContext.mockClear()
    mockAdapter.promptAsync.mockClear()

    await store.sendText('hello', { pluginId: 'com.dawnchat.hello-world-vue' })

    expect(mockAdapter.injectContext).not.toHaveBeenCalled()
    const payload = mockAdapter.promptAsync.mock.calls.at(-1)?.[1]
    expect(typeof payload?.system).toBe('string')
    expect(String(payload?.system || '')).toContain('当前插件开发目标: com.dawnchat.hello-world-vue')
  })

  it('sendText 后会先本地回显用户消息，随后被服务端 user message 替换', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(store.chatRows.length).toBe(0)

    await store.sendText('optimistic echo', { pluginId: 'com.dawnchat.hello-world-vue' })
    const localUserRow = store.chatRows.find((row) => row.info.role === 'user')
    expect(localUserRow).toBeTruthy()
    expect(localUserRow?.items.some((item) => item.type === 'text' && item.text === 'optimistic echo')).toBe(true)

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_remote_user_1',
          role: 'user',
          sessionID: 'ses_test_1',
          time: { created: 1772508188147 }
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_remote_user_1',
          type: 'text',
          messageID: 'msg_remote_user_1',
          text: 'optimistic echo'
        }
      }
    })

    const userRows = store.chatRows.filter((row) => row.info.role === 'user')
    expect(userRows.length).toBe(1)
    expect(userRows[0].info.id).toBe('msg_remote_user_1')
  })

  it('数字时间戳也能参与消息排序', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_num_2',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: 1772508190000 }
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_num_1',
          role: 'assistant',
          sessionID: 'ses_test_1',
          time: { created: 1772508180000 }
        }
      }
    })

    expect(store.orderedMessages[0].info.id).toBe('msg_num_1')
    expect(store.orderedMessages[1].info.id).toBe('msg_num_2')
  })

  it('stream.status 从 reconnecting 切回 streaming 不再触发业务对账', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')
    const baselineCalls = mockAdapter.listMessages.mock.calls.length

    capturedEventHandler?.({
      type: 'stream.status',
      properties: {
        sessionID: 'ses_test_1',
        status: 'reconnecting'
      }
    })
    capturedEventHandler?.({
      type: 'stream.status',
      properties: {
        sessionID: 'ses_test_1',
        status: 'streaming'
      }
    })
    await Promise.resolve()
    await Promise.resolve()

    expect(mockAdapter.listMessages.mock.calls.length).toBe(baselineCalls)
    expect(store.transportStatus).toBe('streaming')
  })

  it('非活跃会话的 stream.status 只更新传输态，不触发对账', async () => {
    const store = useCodingAgentStore()
    mockAdapter.listSessions.mockResolvedValueOnce([
      {
        id: 'ses_a',
        title: 'A',
        time: { created: '2026-01-01T00:00:00.000Z', updated: '2026-01-01T00:00:00.000Z' }
      },
      {
        id: 'ses_b',
        title: 'B',
        time: { created: '2026-01-02T00:00:00.000Z', updated: '2026-01-02T00:00:00.000Z' }
      }
    ])
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(store.activeSessionId).toBe('ses_b')
    const baselineCalls = mockAdapter.listMessages.mock.calls.length
    capturedEventHandler?.({
      type: 'stream.status',
      properties: {
        sessionID: 'ses_a',
        status: 'reconnecting'
      }
    })
    capturedEventHandler?.({
      type: 'stream.status',
      properties: {
        sessionID: 'ses_a',
        status: 'streaming'
      }
    })
    await Promise.resolve()
    await Promise.resolve()
    expect(mockAdapter.listMessages.mock.calls.length).toBe(baselineCalls)
  })

  it('session.status 与 stream.status 分层维护，不会互相覆盖', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'stream.status',
      properties: {
        sessionID: 'ses_test_1',
        status: 'reconnecting',
        error: 'network jitter'
      }
    })
    capturedEventHandler?.({
      type: 'session.status',
      properties: {
        sessionID: 'ses_test_1',
        status: 'running'
      }
    })

    expect(store.transportStatus).toBe('reconnecting')
    expect(store.sessionRunStatus).toBe('running')
    expect(store.isStreaming).toBe(true)
  })

  it('server.connected 到达时会对当前活跃会话执行一次 reconcile', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')
    const baselineCalls = mockAdapter.listMessages.mock.calls.length

    capturedEventHandler?.({
      type: 'server.connected',
      properties: {}
    })
    await Promise.resolve()
    await Promise.resolve()

    expect(mockAdapter.listMessages.mock.calls.length).toBeGreaterThan(baselineCalls)
  })

  it('plan 回合结束且存在工具链路时，canSwitchPlanToBuild 为 true', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    store.selectAgent('plan')
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_plan_1',
          role: 'assistant',
          agent: 'plan',
          mode: 'plan',
          sessionID: 'ses_test_1',
          time: {
            created: '2026-01-06T00:00:00.000Z',
            completed: '2026-01-06T00:00:01.000Z'
          },
          finish: 'tool-calls'
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_plan_1',
          type: 'step-finish',
          messageID: 'msg_plan_1',
          reason: 'tool-calls'
        }
      }
    })

    expect(store.canSwitchPlanToBuild).toBe(true)
  })

  it('todo.updated 会更新 activeSessionTodos', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'todo.updated',
      properties: {
        sessionID: 'ses_test_1',
        todos: [
          { id: 'todo_1', content: 'write plan', status: 'completed', priority: 'high' },
          { id: 'todo_2', content: 'apply changes', status: 'in_progress', priority: 'medium' }
        ]
      }
    })

    expect(store.activeSessionTodos.length).toBe(2)
    expect(store.activeSessionTodos[0].id).toBe('todo_1')
    expect(store.activeSessionTodos[1].status).toBe('in_progress')
  })

  it('todo 缺少 id 时使用 content+index 生成稳定 key', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'todo.updated',
      properties: {
        sessionID: 'ses_test_1',
        todos: [{ content: 'write plan', status: 'pending', priority: 'high' }]
      }
    })

    expect(store.activeSessionTodos[0].id).toBe('content:write plan')
  })

  it('todo.updated 重复内容会被合并并保留最新状态', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'todo.updated',
      properties: {
        sessionID: 'ses_test_1',
        todos: [
          { content: 'write plan', status: 'pending', priority: 'high' },
          { content: 'write plan', status: 'completed', priority: 'high' }
        ]
      }
    })

    expect(store.activeSessionTodos.length).toBe(1)
    expect(store.activeSessionTodos[0].status).toBe('completed')
  })

  it('最后一条 plan 为 stop，但此前已有 tool-calls 时也可切换 Build', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    store.selectAgent('plan')
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_plan_prev',
          role: 'assistant',
          agent: 'plan',
          mode: 'plan',
          sessionID: 'ses_test_1',
          time: {
            created: '2026-01-06T00:00:00.000Z',
            completed: '2026-01-06T00:00:01.000Z'
          },
          finish: 'tool-calls'
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_plan_prev',
          type: 'step-finish',
          messageID: 'msg_plan_prev',
          reason: 'tool-calls'
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_plan_latest',
          role: 'assistant',
          agent: 'plan',
          mode: 'plan',
          sessionID: 'ses_test_1',
          time: {
            created: '2026-01-06T00:00:02.000Z',
            completed: '2026-01-06T00:00:03.000Z'
          },
          finish: 'stop'
        }
      }
    })

    expect(store.canSwitchPlanToBuild).toBe(true)
  })

  it('plan assistant 未完成时，canSwitchPlanToBuild 为 false', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    store.selectAgent('plan')
    expect(capturedEventHandler).toBeTypeOf('function')

    capturedEventHandler?.({
      type: 'message.updated',
      properties: {
        sessionID: 'ses_test_1',
        info: {
          id: 'msg_plan_3',
          role: 'assistant',
          agent: 'plan',
          mode: 'plan',
          sessionID: 'ses_test_1',
          time: { created: '2026-01-06T00:00:00.000Z' },
          finish: 'tool-calls'
        }
      }
    })
    capturedEventHandler?.({
      type: 'message.part.updated',
      properties: {
        sessionID: 'ses_test_1',
        part: {
          id: 'part_plan_4',
          type: 'step-finish',
          messageID: 'msg_plan_3',
          reason: 'tool-calls'
        }
      }
    })

    expect(store.canSwitchPlanToBuild).toBe(false)
  })

  it('Facade 对外契约保持稳定（关键方法仍可调用）', async () => {
    const store = useCodingAgentStore()
    expect(typeof store.ensureReadyWithWorkspace).toBe('function')
    expect(typeof store.reconcileMessages).toBe('function')
    expect(typeof store.sendText).toBe('function')
    expect(typeof store.selectEngine).toBe('function')
    expect(typeof store.selectAgent).toBe('function')
    expect(typeof store.selectModel).toBe('function')
    expect(typeof store.dispose).toBe('function')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(store.activeSessionId).toBe('ses_test_1')
  })

  it('同一 tool 事件序列在 opencode/agentv3 下输出一致的 timeline 结构', async () => {
    const store = useCodingAgentStore()
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    expect(capturedEventHandler).toBeTypeOf('function')

    const emitToolSequence = (sessionID: string) => {
      capturedEventHandler?.({
        type: 'message.updated',
        properties: {
          sessionID,
          info: {
            id: 'msg_tool_same',
            role: 'assistant',
            sessionID,
            time: {
              created: '2026-01-07T00:00:00.000Z',
              completed: '2026-01-07T00:00:01.000Z'
            }
          }
        }
      })
      capturedEventHandler?.({
        type: 'message.part.updated',
        properties: {
          sessionID,
          part: {
            id: 'part_tool_same',
            type: 'tool',
            messageID: 'msg_tool_same',
            tool: 'read',
            state: {
              status: 'completed',
              input: {
                filePath: '/abs/path/src/App.vue'
              },
              output: '<content>\nline 1\nline 2\n</content>'
            }
          }
        }
      })
    }

    emitToolSequence('ses_test_1')
    const opencodeSignature = store.timelineItems.map((item) => {
      if (item.kind !== 'part') return item.kind
      const base = `${item.kind}:${item.item.type}`
      if (item.item.type !== 'tool') return base
      return `${base}:${item.item.toolDisplay?.argsPreview || ''}`
    })

    store.selectEngine('agentv3')
    await store.ensureReadyWithWorkspace({ pluginId: 'com.dawnchat.hello-world-vue' })
    emitToolSequence('ses_test_1')
    const agentV3Signature = store.timelineItems.map((item) => {
      if (item.kind !== 'part') return item.kind
      const base = `${item.kind}:${item.item.type}`
      if (item.item.type !== 'tool') return base
      return `${base}:${item.item.toolDisplay?.argsPreview || ''}`
    })

    expect(agentV3Signature).toEqual(opencodeSignature)
  })
})
