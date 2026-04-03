import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import { createRuntimeOrchestrator } from '@/features/coding-agent/store/runtimeOrchestrator'
import { createEmptySessionState } from '@/features/coding-agent/store/sessionHelpers'

describe('runtimeOrchestrator', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  function createHarness(options?: {
    listMessages?: () => Promise<Array<{ info: any; parts: any[] }>>
  }) {
    const selectedEngine = ref<'opencode' | 'agentv3'>('opencode')
    const selectedAgent = ref('build')
    const selectedModel = ref(null)
    const selectedModelId = ref('')
    const availableModels = ref([])
    const isReady = ref(true)
    const boundWorkspaceTarget = ref({
      id: 'w1',
      kind: 'plugin-dev',
      displayName: 'w1',
      appType: 'desktop',
      workspacePath: '/tmp/w1',
      preferredEntry: '',
      preferredDirectories: [],
      hints: [],
      defaultAgent: 'build',
      sessionStrategy: 'multi'
    } as any)
    const workspaceProfile = ref(boundWorkspaceTarget.value)
    const boundWorkspaceId = computed(() => String(boundWorkspaceTarget.value?.id || ''))
    const sessions = ref([{ id: 's1', title: 'New Chat', createdAt: '', updatedAt: '' }])
    const activeSessionId = ref('s1')
    const sessionStateById = ref({ s1: createEmptySessionState() })
    const sessionTodosById = ref({})
    const messageSessionById = ref({})
    const globalError = ref<string | null>(null)
    const eventUnsubscribe = ref<(() => void) | null>(null)
    const ensureReadyPromise = ref<Promise<void> | null>(null)
    const pendingLocalUserMessageIdsBySession = ref({})
    const streamWatchdogs = ref({})
    const listMessages = vi.fn(options?.listMessages || (async () => []))
    const subscribeEvents = vi.fn(async () => vi.fn())
    const promptAsync = vi.fn(async () => {})
    const adapter = {
      subscribeEvents,
      listMessages,
      promptAsync,
      interruptSession: async () => true
    }
    const orchestrator = createRuntimeOrchestrator({
      selectedEngine: selectedEngine as any,
      selectedAgent,
      selectedModel: selectedModel as any,
      selectedModelId,
      availableModels: availableModels as any,
      isReady,
      boundWorkspaceTarget,
      workspaceProfile,
      boundWorkspaceId: boundWorkspaceId as any,
      sessions: sessions as any,
      activeSessionId,
      sessionStateById: sessionStateById as any,
      sessionTodosById: sessionTodosById as any,
      messageSessionById: messageSessionById as any,
      globalError,
      eventUnsubscribe,
      ensureReadyPromise,
      pendingLocalUserMessageIdsBySession: pendingLocalUserMessageIdsBySession as any,
      streamWatchdogs: streamWatchdogs as any,
      getActiveAdapter: () => adapter as any,
      loadRuntimeMeta: async () => {},
      loadWorkspaceProfile: async () => {},
      setAvailableAgents: () => {},
      activeSessionStorageKey: () => 'k',
      setActiveSession: () => {},
      createSession: async () => 's1',
      loadSessions: async () => {},
      buildWorkspaceSystemPrompt: () => '',
      tryRenameDefaultSessionAfterSend: () => {},
      getOrCreateSessionState: (sessionID: string) => {
        if (!sessionStateById.value[sessionID]) {
          ;(sessionStateById.value as any)[sessionID] = createEmptySessionState()
        }
        return sessionStateById.value[sessionID] as any
      },
      reconcileQuestions: async () => {},
      reconcilePermissions: async () => {},
      updateSessionTouch: () => {},
      pushLocalUserEcho: () => {},
      clearPendingLocalUserEchoes: () => {},
      applyEvent: () => {}
    })
    return {
      orchestrator,
      sessionStateById,
      workspaceTarget: boundWorkspaceTarget.value,
      selectedEngine,
      adapter,
      promptAsync
    }
  }

  it('ready 短路路径下若订阅缺失会自动重建订阅', async () => {
    const selectedEngine = ref<'opencode' | 'agentv3'>('opencode')
    const selectedAgent = ref('build')
    const selectedModel = ref(null)
    const selectedModelId = ref('')
    const availableModels = ref([])
    const isReady = ref(true)
    const boundWorkspaceTarget = ref({
      id: 'w1',
      kind: 'plugin-dev',
      displayName: 'w1',
      appType: 'desktop',
      workspacePath: '/tmp/w1',
      preferredEntry: '',
      preferredDirectories: [],
      hints: [],
      defaultAgent: 'build',
      sessionStrategy: 'multi'
    } as any)
    const workspaceProfile = ref(boundWorkspaceTarget.value)
    const boundWorkspaceId = computed(() => String(boundWorkspaceTarget.value?.id || ''))
    const sessions = ref([{ id: 's1', title: 'New Chat', createdAt: '', updatedAt: '' }])
    const activeSessionId = ref('s1')
    const sessionStateById = ref({ s1: createEmptySessionState() })
    const sessionTodosById = ref({})
    const messageSessionById = ref({})
    const globalError = ref<string | null>(null)
    const eventUnsubscribe = ref<(() => void) | null>(null)
    const ensureReadyPromise = ref<Promise<void> | null>(null)
    const pendingLocalUserMessageIdsBySession = ref({})
    const streamWatchdogs = ref({})
    const unsubscribe = vi.fn()
    const subscribeEvents = vi.fn(async () => unsubscribe)

    const adapter = {
      subscribeEvents,
      listMessages: async () => [],
      promptAsync: async () => {},
      interruptSession: async () => true
    }

    const orchestrator = createRuntimeOrchestrator({
      selectedEngine: selectedEngine as any,
      selectedAgent,
      selectedModel: selectedModel as any,
      selectedModelId,
      availableModels: availableModels as any,
      isReady,
      boundWorkspaceTarget,
      workspaceProfile,
      boundWorkspaceId: boundWorkspaceId as any,
      sessions: sessions as any,
      activeSessionId,
      sessionStateById: sessionStateById as any,
      sessionTodosById: sessionTodosById as any,
      messageSessionById: messageSessionById as any,
      globalError,
      eventUnsubscribe,
      ensureReadyPromise,
      pendingLocalUserMessageIdsBySession: pendingLocalUserMessageIdsBySession as any,
      streamWatchdogs: streamWatchdogs as any,
      getActiveAdapter: () => adapter as any,
      loadRuntimeMeta: async () => {},
      loadWorkspaceProfile: async () => {},
      setAvailableAgents: () => {},
      activeSessionStorageKey: () => 'k',
      setActiveSession: () => {},
      createSession: async () => 's1',
      loadSessions: async () => {},
      buildWorkspaceSystemPrompt: () => '',
      tryRenameDefaultSessionAfterSend: () => {},
      getOrCreateSessionState: (sessionID: string) => {
        if (!sessionStateById.value[sessionID]) {
          ;(sessionStateById.value as any)[sessionID] = createEmptySessionState()
        }
        return sessionStateById.value[sessionID] as any
      },
      reconcileQuestions: async () => {},
      reconcilePermissions: async () => {},
      updateSessionTouch: () => {},
      pushLocalUserEcho: () => {},
      clearPendingLocalUserEchoes: () => {},
      applyEvent: () => {}
    })

    await orchestrator.ensureReadyWithWorkspace({
      workspaceTarget: boundWorkspaceTarget.value
    })

    expect(subscribeEvents).toHaveBeenCalledTimes(1)
    expect(typeof eventUnsubscribe.value).toBe('function')
  })

  it('权限等待期间标记 waiting_permission，且不会误触发 run_stalled 对账', async () => {
    vi.useFakeTimers()
    const selectedEngine = ref<'opencode' | 'agentv3'>('opencode')
    const selectedAgent = ref('build')
    const selectedModel = ref(null)
    const selectedModelId = ref('')
    const availableModels = ref([])
    const isReady = ref(true)
    const boundWorkspaceTarget = ref({
      id: 'w1',
      kind: 'plugin-dev',
      displayName: 'w1',
      appType: 'desktop',
      workspacePath: '/tmp/w1',
      preferredEntry: '',
      preferredDirectories: [],
      hints: [],
      defaultAgent: 'build',
      sessionStrategy: 'multi'
    } as any)
    const workspaceProfile = ref(boundWorkspaceTarget.value)
    const boundWorkspaceId = computed(() => String(boundWorkspaceTarget.value?.id || ''))
    const sessions = ref([{ id: 's1', title: 'New Chat', createdAt: '', updatedAt: '' }])
    const activeSessionId = ref('s1')
    const sessionStateById = ref({ s1: createEmptySessionState() })
    const sessionTodosById = ref({})
    const messageSessionById = ref({})
    const globalError = ref<string | null>(null)
    const eventUnsubscribe = ref<(() => void) | null>(null)
    const ensureReadyPromise = ref<Promise<void> | null>(null)
    const pendingLocalUserMessageIdsBySession = ref({})
    const streamWatchdogs = ref({})
    let onEvent: ((evt: any) => void) | null = null
    const listMessages = vi.fn(async () => [])
    const subscribeEvents = vi.fn(async (handler: (evt: any) => void) => {
      onEvent = handler
      return vi.fn()
    })

    const adapter = {
      subscribeEvents,
      listMessages,
      promptAsync: async () => {},
      interruptSession: async () => true
    }

    const orchestrator = createRuntimeOrchestrator({
      selectedEngine: selectedEngine as any,
      selectedAgent,
      selectedModel: selectedModel as any,
      selectedModelId,
      availableModels: availableModels as any,
      isReady,
      boundWorkspaceTarget,
      workspaceProfile,
      boundWorkspaceId: boundWorkspaceId as any,
      sessions: sessions as any,
      activeSessionId,
      sessionStateById: sessionStateById as any,
      sessionTodosById: sessionTodosById as any,
      messageSessionById: messageSessionById as any,
      globalError,
      eventUnsubscribe,
      ensureReadyPromise,
      pendingLocalUserMessageIdsBySession: pendingLocalUserMessageIdsBySession as any,
      streamWatchdogs: streamWatchdogs as any,
      getActiveAdapter: () => adapter as any,
      loadRuntimeMeta: async () => {},
      loadWorkspaceProfile: async () => {},
      setAvailableAgents: () => {},
      activeSessionStorageKey: () => 'k',
      setActiveSession: () => {},
      createSession: async () => 's1',
      loadSessions: async () => {},
      buildWorkspaceSystemPrompt: () => '',
      tryRenameDefaultSessionAfterSend: () => {},
      getOrCreateSessionState: (sessionID: string) => {
        if (!sessionStateById.value[sessionID]) {
          ;(sessionStateById.value as any)[sessionID] = createEmptySessionState()
        }
        return sessionStateById.value[sessionID] as any
      },
      reconcileQuestions: async () => {},
      reconcilePermissions: async () => {},
      updateSessionTouch: () => {},
      pushLocalUserEcho: () => {},
      clearPendingLocalUserEchoes: () => {},
      applyEvent: (evt: any) => {
        const state = sessionStateById.value.s1 as any
        const type = String(evt?.type || '')
        if (type !== 'server.heartbeat') {
          state.lastNonHeartbeatEventAt = Date.now()
        }
        if (type === 'permission.asked') {
          state.permissionCardsById.p1 = {
            id: 'p1',
            sessionID: 's1',
            messageID: 'm1',
            callID: 'c1',
            tool: 'bash',
            status: 'pending',
            detail: 'waiting'
          }
        }
        if (type === 'permission.replied') {
          state.permissionCardsById.p1 = {
            ...state.permissionCardsById.p1,
            status: 'approved',
            response: 'once'
          }
        }
        if (type === 'session.idle') {
          state.isStreaming = false
          state.sessionRunStatus = 'idle'
        }
      }
    })

    await orchestrator.ensureReadyWithWorkspace({
      workspaceTarget: boundWorkspaceTarget.value
    })
    await orchestrator.sendText('hello', { workspaceTarget: boundWorkspaceTarget.value })
    const baselineListCalls = listMessages.mock.calls.length
    onEvent?.({
      type: 'permission.asked',
      properties: {
        sessionID: 's1',
        id: 'p1'
      }
    })

    await vi.advanceTimersByTimeAsync(5200)
    expect(sessionStateById.value.s1.runWaitReason).toBe('waiting_permission')

    for (let i = 0; i < 12; i += 1) {
      onEvent?.({ type: 'server.heartbeat', properties: {} })
      await vi.advanceTimersByTimeAsync(5000)
    }
    expect(listMessages.mock.calls.length).toBeLessThanOrEqual(baselineListCalls + 1)

    onEvent?.({
      type: 'permission.replied',
      properties: {
        sessionID: 's1',
        requestID: 'p1',
        reply: 'once'
      }
    })
    await vi.advanceTimersByTimeAsync(5200)
    expect(sessionStateById.value.s1.runWaitReason).toBe('generating')

    onEvent?.({
      type: 'session.idle',
      properties: {
        sessionID: 's1'
      }
    })
    expect(sessionStateById.value.s1.runWaitReason).toBe('')
    orchestrator.dispose()
  })

  it('reconcileMessages 能在终态快照下兜底结束 streaming', async () => {
    const { orchestrator, sessionStateById, workspaceTarget } = createHarness({
      listMessages: async () => [
        {
          info: {
            id: 'm_assistant',
            role: 'assistant',
            time: { created: 1000, completed: 1200 }
          },
          parts: [
            {
              id: 'p_text',
              type: 'text',
              text: 'done'
            }
          ]
        }
      ]
    })
    await orchestrator.ensureReadyWithWorkspace({ workspaceTarget })
    const state = sessionStateById.value.s1 as any
    state.isStreaming = true
    state.sessionRunStatus = 'running'
    state.runWaitReason = 'stalled'

    await orchestrator.reconcileMessages('s1')

    expect(state.isStreaming).toBe(false)
    expect(state.sessionRunStatus).toBe('idle')
    expect(state.runWaitReason).toBe('')
    orchestrator.dispose()
  })

  it('reconcileMessages 在存在未完成信号时不会提前结束 streaming', async () => {
    const harness = createHarness({
      listMessages: async () => [
        {
          info: {
            id: 'm_assistant',
            role: 'assistant',
            time: { created: 1000, completed: 1200 }
          },
          parts: [
            {
              id: 'p_tool',
              type: 'tool',
              tool: 'bash',
              state: { status: 'running' }
            }
          ]
        }
      ]
    })
    await harness.orchestrator.ensureReadyWithWorkspace({ workspaceTarget: harness.workspaceTarget })
    const state = harness.sessionStateById.value.s1 as any
    state.isStreaming = true
    state.sessionRunStatus = 'running'
    await harness.orchestrator.reconcileMessages('s1')
    expect(state.isStreaming).toBe(true)

    const harnessNoCompleted = createHarness({
      listMessages: async () => [
        {
          info: {
            id: 'm_assistant_2',
            role: 'assistant',
            time: { created: 2000 }
          },
          parts: [{ id: 'p_text_2', type: 'text', text: 'still typing' }]
        }
      ]
    })
    await harnessNoCompleted.orchestrator.ensureReadyWithWorkspace({ workspaceTarget: harnessNoCompleted.workspaceTarget })
    const stateNoCompleted = harnessNoCompleted.sessionStateById.value.s1 as any
    stateNoCompleted.isStreaming = true
    stateNoCompleted.sessionRunStatus = 'running'
    await harnessNoCompleted.orchestrator.reconcileMessages('s1')
    expect(stateNoCompleted.isStreaming).toBe(true)

    harness.orchestrator.dispose()
    harnessNoCompleted.orchestrator.dispose()
  })

  it('sendPromptParts 会透传图片 part 给 OpenCode', async () => {
    const harness = createHarness()
    await harness.orchestrator.ensureReadyWithWorkspace({ workspaceTarget: harness.workspaceTarget })
    await harness.orchestrator.sendPromptParts(
      [
        { type: 'text', text: 'describe image' },
        { type: 'file', mime: 'image/png', url: 'data:image/png;base64,AAAA', filename: 'shot.png' }
      ],
      { workspaceTarget: harness.workspaceTarget }
    )
    expect(harness.promptAsync).toHaveBeenCalledTimes(1)
    const payload = harness.promptAsync.mock.calls[0]?.[1] as { parts?: Array<{ type: string }> }
    expect(payload.parts?.some((item) => item.type === 'file')).toBe(true)
    harness.orchestrator.dispose()
  })

  it('sendPromptParts 在 AgentV3 下拒绝图片 part', async () => {
    const harness = createHarness()
    harness.selectedEngine.value = 'agentv3'
    await harness.orchestrator.ensureReadyWithWorkspace({ workspaceTarget: harness.workspaceTarget })
    await expect(
      harness.orchestrator.sendPromptParts(
        [{ type: 'file', mime: 'image/png', url: 'data:image/png;base64,BBBB', filename: 'clip.png' }],
        { workspaceTarget: harness.workspaceTarget }
      )
    ).rejects.toThrow('当前引擎暂不支持图片输入')
    expect(harness.promptAsync).not.toHaveBeenCalled()
    harness.orchestrator.dispose()
  })
})
