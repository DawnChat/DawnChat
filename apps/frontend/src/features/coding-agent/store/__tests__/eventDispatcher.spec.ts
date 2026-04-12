import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { ENGINE_AGENTV3, ENGINE_OPENCODE } from '@/services/coding-agent/adapterRegistry'
import { createEventDispatcher } from '@/features/coding-agent/store/eventDispatcher'
import { createEmptySessionState } from '@/features/coding-agent/store/sessionHelpers'
import type { PermissionCard, SessionMeta, SessionState, SessionTodoItem, WorkspaceTarget } from '@/features/coding-agent/store/types'
import type { CodingAgentEvent, CodingAgentSession } from '@/services/coding-agent/engineAdapter'
import * as permissionNormalizer from '@/features/coding-agent/store/permissionNormalizer'

function baseWorkspace(overrides: Partial<WorkspaceTarget> = {}): WorkspaceTarget {
  return {
    id: 'w1',
    kind: 'plugin-dev',
    displayName: 'Test',
    appType: 'test',
    workspacePath: '/proj/ws',
    preferredEntry: '',
    preferredDirectories: [],
    hints: [],
    defaultAgent: 'build',
    sessionStrategy: 'multi',
    ...overrides
  }
}

function createHarness(options?: {
  selectedEngine?: string
  workspaceProfile?: WorkspaceTarget | null
  sessions?: SessionMeta[]
  activeSessionId?: string
  messageSessionById?: Record<string, string>
}) {
  const selectedEngine = ref(options?.selectedEngine ?? ENGINE_AGENTV3)
  const workspaceProfile = ref<WorkspaceTarget | null>(options?.workspaceProfile ?? baseWorkspace())
  const activeSessionId = ref(options?.activeSessionId ?? 's1')
  const sessions = ref<SessionMeta[]>(options?.sessions ?? [])
  const sessionTodosById = ref<Record<string, SessionTodoItem[]>>({})
  const messageSessionById = ref<Record<string, string>>(options?.messageSessionById ?? {})
  const globalError = ref<string | null>(null)
  const selectedAgent = ref('build')
  const selectedModelId = ref('')

  const sessionStateById: Record<string, SessionState> = {}

  const getOrCreateSessionState = (sessionID: string) => {
    if (!sessionStateById[sessionID]) {
      sessionStateById[sessionID] = createEmptySessionState()
    }
    return sessionStateById[sessionID]
  }

  const upsertMessageInfo = vi.fn()
  const upsertPart = vi.fn()
  const appendPartDelta = vi.fn()
  const upsertSessionMeta = vi.fn()
  const upsertPermissionCard = vi.fn()
  const removeQuestionCard = vi.fn()
  const reconcileMessages = vi.fn(async () => {})

  const dispatcher = createEventDispatcher({
    selectedEngine,
    workspaceProfile,
    activeSessionId,
    sessions,
    sessionTodosById,
    messageSessionById,
    globalError,
    selectedAgent,
    selectedModelId,
    getOrCreateSessionState,
    findPermissionSessionID: () => '',
    normalizeSessionMeta: (raw: CodingAgentSession) => ({
      id: String(raw.id),
      title: String(raw.title || ''),
      directory: String(raw.directory || ''),
      workspace_path: String(raw.workspace_path || ''),
      workspace_kind: String(raw.workspace_kind || ''),
      plugin_id: raw.plugin_id ? String(raw.plugin_id) : undefined,
      project_id: raw.project_id ? String(raw.project_id) : undefined,
      time: raw.time
        ? {
            created: raw.time.created ? String(raw.time.created) : undefined,
            updated: raw.time.updated ? String(raw.time.updated) : undefined
          }
        : undefined
    }),
    extractSessionErrorRawMessage: (payload: unknown) => String((payload as { message?: string })?.message || ''),
    toReadableSessionError: (raw: string) => raw,
    upsertSessionMeta,
    updateSessionTouch: vi.fn(),
    clearPendingLocalUserEchoes: vi.fn(),
    upsertMessageInfo,
    upsertPart,
    appendPartDelta,
    removePart: vi.fn(),
    removeMessage: vi.fn(),
    upsertPermissionCard,
    upsertQuestionCard: vi.fn(),
    removeQuestionCard,
    appendSessionErrorMessage: vi.fn(),
    reconcileMessages
  })

  return {
    dispatcher,
    sessionStateById,
    upsertMessageInfo,
    upsertPart,
    appendPartDelta,
    upsertSessionMeta,
    upsertPermissionCard,
    removeQuestionCard,
    getOrCreateSessionState,
    activeSessionId
  }
}

describe('createEventDispatcher', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('同一 eventID 第二次 applyEvent 不会再次调用 upsertMessageInfo / upsertPart', () => {
    const { dispatcher, upsertMessageInfo, upsertPart } = createHarness()
    const evtBase: CodingAgentEvent = {
      type: 'message.updated',
      sessionID: 's1',
      eventID: 9001,
      properties: {
        info: { id: 'm1', role: 'assistant' }
      }
    }
    dispatcher.applyEvent(evtBase)
    dispatcher.applyEvent(evtBase)
    expect(upsertMessageInfo).toHaveBeenCalledTimes(1)
    expect(upsertPart).not.toHaveBeenCalled()

    const partEvt: CodingAgentEvent = {
      type: 'message.part.updated',
      sessionID: 's1',
      eventID: 9002,
      properties: {
        part: { id: 'p1', type: 'text', messageID: 'm1', text: 'hi' }
      }
    }
    dispatcher.applyEvent(partEvt)
    dispatcher.applyEvent(partEvt)
    expect(upsertPart).toHaveBeenCalledTimes(1)
  })

  it('OpenCode：session 目录与 workspace 不一致时不 upsertSessionMeta；一致时 upsert', () => {
    const wsPath = '/proj/ws'
    const { dispatcher, upsertSessionMeta } = createHarness({
      selectedEngine: ENGINE_OPENCODE,
      workspaceProfile: baseWorkspace({ workspacePath: wsPath }),
      sessions: []
    })

    dispatcher.applyEvent({
      type: 'session.created',
      properties: {
        session: { id: 'sess-other', directory: '/other/path', title: 'x' } as CodingAgentSession
      }
    })
    expect(upsertSessionMeta).not.toHaveBeenCalled()

    dispatcher.applyEvent({
      type: 'session.created',
      properties: {
        session: { id: 'sess-ok', directory: wsPath, title: 'ok' } as CodingAgentSession
      }
    })
    expect(upsertSessionMeta).toHaveBeenCalledTimes(1)
    expect(upsertSessionMeta.mock.calls[0][0].id).toBe('sess-ok')
  })

  it('resolveSessionIDForEvent：顶层 sessionID、properties.sessionID、仅 messageID + 映射', () => {
    const { dispatcher, activeSessionId } = createHarness({
      activeSessionId: 'fallback-session',
      messageSessionById: { mOnly: 'mapped-session' }
    })

    expect(
      dispatcher.resolveSessionIDForEvent({
        type: 'x',
        sessionID: 'top-sid'
      })
    ).toBe('top-sid')

    expect(
      dispatcher.resolveSessionIDForEvent({
        type: 'x',
        properties: { sessionID: 'prop-sid' }
      })
    ).toBe('prop-sid')

    expect(
      dispatcher.resolveSessionIDForEvent({
        type: 'x',
        properties: { messageID: 'mOnly' }
      })
    ).toBe('mapped-session')

    activeSessionId.value = 'active-fallback'
    expect(
      dispatcher.resolveSessionIDForEvent({
        type: 'x',
        properties: {}
      })
    ).toBe('active-fallback')
  })

  it('stream.status：streaming / closed 影响 transportStatus 与 transportError', () => {
    const { dispatcher, getOrCreateSessionState } = createHarness()
    getOrCreateSessionState('s1')

    dispatcher.applyEvent({
      type: 'stream.status',
      sessionID: 's1',
      properties: { status: 'streaming' }
    })
    expect(getOrCreateSessionState('s1').transportStatus).toBe('streaming')
    expect(getOrCreateSessionState('s1').transportError).toBeNull()

    dispatcher.applyEvent({
      type: 'stream.status',
      sessionID: 's1',
      properties: { status: 'closed', error: 'gone' }
    })
    expect(getOrCreateSessionState('s1').transportStatus).toBe('closed')
    expect(getOrCreateSessionState('s1').transportError).toBe('gone')
  })

  it('message.part.delta：无嵌套 part 时走 appendPartDelta', () => {
    const { dispatcher, appendPartDelta } = createHarness()
    dispatcher.applyEvent({
      type: 'message.part.delta',
      sessionID: 's1',
      properties: {
        messageID: 'm1',
        partID: 'p1',
        field: 'text',
        delta: 'abc'
      }
    })
    expect(appendPartDelta).toHaveBeenCalledWith('s1', 'm1', 'p1', 'text', 'abc', undefined)
  })

  it('permission.asked：normalizePermissionPayload 与 upsertPermissionCard 被调用', () => {
    const card: PermissionCard = {
      id: 'perm-1',
      sessionID: 's1',
      messageID: 'm1',
      callID: 'c1',
      tool: 'bash',
      status: 'pending',
      detail: 'need ok',
      response: ''
    }
    const normalizeSpy = vi.spyOn(permissionNormalizer, 'normalizePermissionPayload').mockReturnValue(card)

    const { dispatcher, upsertPermissionCard } = createHarness()
    const props = { permission: { id: 'perm-1', sessionID: 's1' } }
    dispatcher.applyEvent({
      type: 'permission.asked',
      sessionID: 's1',
      properties: props
    })

    expect(normalizeSpy).toHaveBeenCalledWith(props, 'permission.asked')
    expect(upsertPermissionCard).toHaveBeenCalledWith(
      's1',
      expect.objectContaining({
        id: 'perm-1',
        sessionID: 's1'
      })
    )
  })

  it('question.replied：根据 requestID 调用 removeQuestionCard', () => {
    const { dispatcher, removeQuestionCard } = createHarness()
    dispatcher.applyEvent({
      type: 'question.replied',
      sessionID: 's1',
      properties: { requestID: 'req-9' }
    })
    expect(removeQuestionCard).toHaveBeenCalledWith('s1', 'req-9')
  })
})
