import type { Ref } from 'vue'
import { logger } from '@/utils/logger'
import { ENGINE_AGENTV3 } from '@/services/coding-agent/adapterRegistry'
import type { CodingAgentSession, EngineAdapter } from '@/services/coding-agent/engineAdapter'
import type { ModelOption, SessionMeta, SessionState, SessionTodoItem, WorkspaceTarget } from '@/features/coding-agent/store/types'
import { DEFAULT_SESSION_TITLE, isDefaultSessionTitle, normalizeSessionMeta, summarizePromptAsTitle } from '@/features/coding-agent/store/sessionHelpers'

export function createSessionCrud(input: {
  getAdapter: () => EngineAdapter
  selectedEngine: Ref<string>
  selectedAgent: Ref<string>
  selectedModel: Ref<ModelOption | null>
  sessions: Ref<SessionMeta[]>
  activeSessionId: Ref<string>
  sessionStateById: Ref<Record<string, SessionState>>
  sessionTodosById: Ref<Record<string, SessionTodoItem[]>>
  messageSessionById: Ref<Record<string, string>>
  boundWorkspaceTarget: Ref<WorkspaceTarget | null>
  workspaceProfile: Ref<WorkspaceTarget | null>
  globalError: Ref<string | null>
  setActiveSession: (id: string) => void
  sortSessions: () => void
  upsertSessionMeta: (meta: SessionMeta) => void
  getOrCreateSessionState: (sessionID: string) => SessionState
  patchAgentV3SessionConfig: (payload: {
    agent?: string
    model?: { providerID: string; modelID: string }
  }) => Promise<void>
  reconcileMessages: (targetSessionID?: string) => Promise<void>
}) {
  const {
    getAdapter,
    selectedEngine,
    selectedAgent,
    selectedModel,
    sessions,
    activeSessionId,
    sessionStateById,
    sessionTodosById,
    messageSessionById,
    boundWorkspaceTarget,
    workspaceProfile,
    globalError,
    setActiveSession,
    sortSessions,
    upsertSessionMeta,
    getOrCreateSessionState,
    patchAgentV3SessionConfig,
    reconcileMessages
  } = input

  function normalizeDirectory(value: unknown): string {
    const normalized = String(value || '')
      .trim()
      .replace(/\\/g, '/')
    if (!normalized) return ''
    if (normalized === '/') return normalized
    return normalized.replace(/\/+$/, '')
  }

  function resolveWorkspaceDirectory(): string {
    return normalizeDirectory(workspaceProfile.value?.workspacePath)
  }

  function resolveSessionQueryOptions() {
    const target = boundWorkspaceTarget.value || workspaceProfile.value
    const directory = resolveWorkspaceDirectory()
    return {
      ...(directory ? { directory, workspacePath: directory } : {}),
      ...(target?.kind ? { workspaceKind: target.kind } : {}),
      ...(target?.pluginId ? { pluginId: target.pluginId } : {}),
      ...(target?.projectId ? { projectId: target.projectId } : {})
    }
  }

  function getSessionDirectory(row: CodingAgentSession): string {
    const directory = normalizeDirectory(row.directory)
    if (directory) return directory
    return normalizeDirectory((row as { cwd?: unknown }).cwd)
  }

  function filterWorkspaceSessions(rows: CodingAgentSession[]): CodingAgentSession[] {
    const workspaceDirectory = resolveWorkspaceDirectory()
    const target = boundWorkspaceTarget.value || workspaceProfile.value
    const projectId = String(target?.projectId || '').trim()
    const pluginId = String(target?.pluginId || '').trim()
    const workspaceKind = String(target?.kind || '').trim()
    if (!workspaceDirectory && !projectId && !pluginId && !workspaceKind) return rows
    const hasAgentV3Metadata = rows.some((row) => {
      return Boolean(row.workspace_path || row.project_id || row.plugin_id || row.workspace_kind)
    })
    if (hasAgentV3Metadata) {
      return rows.filter((row) => {
        if (projectId && String(row.project_id || '').trim() !== projectId) return false
        if (pluginId && String(row.plugin_id || '').trim() !== pluginId) return false
        if (workspaceKind && String(row.workspace_kind || '').trim() && String(row.workspace_kind || '').trim() !== workspaceKind) {
          return false
        }
        if (workspaceDirectory) {
          const rowWorkspacePath = normalizeDirectory(row.workspace_path)
          if (rowWorkspacePath && rowWorkspacePath !== workspaceDirectory) return false
        }
        return true
      })
    }
    if (!workspaceDirectory) return rows
    const hasDirectoryMetadata = rows.some((row) => Boolean(getSessionDirectory(row)))
    if (!hasDirectoryMetadata) return rows
    return rows.filter((row) => getSessionDirectory(row) === workspaceDirectory)
  }

  async function loadSessions() {
    const rows = await getAdapter().listSessions(resolveSessionQueryOptions())
    const metas = filterWorkspaceSessions(rows)
      .map((row) => normalizeSessionMeta(row))
      .filter((row) => row.id)
    sessions.value = metas
    sortSessions()
    for (const item of sessions.value) {
      getOrCreateSessionState(item.id)
    }
  }

  function buildWorkspaceSystemPrompt(pluginId: string): string {
    const profile = workspaceProfile.value
    const appType = String(profile?.appType || 'desktop')
    const isPluginDev = profile?.kind === 'plugin-dev'
    const lines = isPluginDev
      ? [
          `当前插件开发目标: ${pluginId}`,
          `插件类型: ${appType}`,
          '你正在 DawnChat 插件开发模式中工作。',
          '共享 OpenCode 规则已由 DawnChat 自动注入，请优先遵循并保持改动最小化。'
        ]
      : [
          `当前 Workbench 工作区: ${profile?.displayName || pluginId || 'Untitled Workspace'}`,
          `工作区类型: ${appType}`,
          '你正在 DawnChat Workbench 通用聊天模式中工作。',
          '请优先基于当前工作区上下文给出通用协助，并保持响应清晰、稳健。'
        ]
    if (profile?.workspacePath) {
      lines.push(`工作区根目录: ${profile.workspacePath}`)
    }
    if (profile?.preferredEntry) {
      lines.push(`优先入口文件: ${profile.preferredEntry}`)
    }
    if (profile?.preferredDirectories?.length) {
      lines.push(`优先修改目录: ${profile.preferredDirectories.join(', ')}`)
    }
    if (isPluginDev && appType === 'web') {
      lines.push('这是纯前端 web 插件，不要假设存在 Python 后端、pyproject.toml 或桌面端入口。')
      lines.push('优先在 web-src/src 下完成页面、组件、样式和状态管理相关改动。')
      lines.push('如果需要拆分结构，请优先使用 Vue 组件、composables、stores 等常见最佳实践。')
    } else if (isPluginDev) {
      lines.push('如涉及前后端联动，请分别检查 Python 后端与 Vue 前端改动范围。')
    }
    if (profile?.hints?.length) {
      lines.push(...profile.hints)
    }
    lines.push('修改代码后请尽量给出可验证步骤，并保持改动最小化。')
    return lines.join('\n')
  }

  async function createSession(title = DEFAULT_SESSION_TITLE, injectContext = true): Promise<string> {
    const adapter = getAdapter()
    globalError.value = null
    let id = ''
    try {
      id = await adapter.createSession(title, resolveSessionQueryOptions())
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      globalError.value = `创建会话失败: ${message}`
      throw err
    }
    const session = await adapter.getSession(id).catch(() => null)
    const meta = session
      ? normalizeSessionMeta(session)
      : {
          id,
          title,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString()
        }
    upsertSessionMeta(meta)
    getOrCreateSessionState(id)
    setActiveSession(id)
    if (selectedEngine.value === ENGINE_AGENTV3 && adapter.updateSessionConfig) {
      const selected = selectedModel.value
      try {
        await patchAgentV3SessionConfig({
          agent: selectedAgent.value,
          model: selected
            ? {
                providerID: selected.providerID,
                modelID: selected.modelID
              }
            : undefined
        })
      } catch (err) {
        logger.warn('[codingAgentStore] createSession patch config failed', err)
        globalError.value = '会话已创建，但初始化配置失败，后续消息会自动重试。'
      }
    }
    if (injectContext) {
      // no-op
    }
    try {
      await loadSessions()
      if (!sessions.value.some((item) => item.id === id)) {
        upsertSessionMeta(meta)
      }
      await reconcileMessages(id)
    } catch (err) {
      logger.warn('[codingAgentStore] createSession consistency reconcile failed', err)
      globalError.value = '会话已创建，正在同步最新状态...'
    }
    return id
  }

  async function switchSession(id: string): Promise<void> {
    const sessionID = String(id || '').trim()
    if (!sessionID) return
    if (!sessions.value.some((item) => item.id === sessionID)) {
      const remote = await getAdapter().getSession(sessionID)
      if (!remote) {
        throw new Error(`session not found: ${sessionID}`)
      }
      upsertSessionMeta(normalizeSessionMeta(remote))
    }
    setActiveSession(sessionID)
    await reconcileMessages(sessionID)
  }

  async function renameSession(sessionID: string, title: string): Promise<void> {
    const id = String(sessionID || '').trim()
    const nextTitle = String(title || '').trim()
    if (!id || !nextTitle) return
    const updated = await getAdapter().updateSession(id, { title: nextTitle })
    if (updated) {
      upsertSessionMeta(normalizeSessionMeta(updated))
      return
    }
    const current = sessions.value.find((item) => item.id === id)
    if (current) {
      current.title = nextTitle
      current.updatedAt = new Date().toISOString()
      sortSessions()
    }
  }

  async function deleteSession(sessionID: string): Promise<void> {
    const id = String(sessionID || '').trim()
    if (!id) return
    await getAdapter().deleteSession(id)
    sessions.value = sessions.value.filter((item) => item.id !== id)
    delete sessionStateById.value[id]
    delete sessionTodosById.value[id]

    const messageIds = Object.entries(messageSessionById.value)
      .filter(([, sid]) => sid === id)
      .map(([messageID]) => messageID)
    for (const messageID of messageIds) {
      delete messageSessionById.value[messageID]
    }

    if (activeSessionId.value === id) {
      const fallback = sessions.value[0]?.id || ''
      if (fallback) {
        setActiveSession(fallback)
        await reconcileMessages(fallback)
      } else if (boundWorkspaceTarget.value?.id) {
        await createSession(DEFAULT_SESSION_TITLE, true)
      } else {
        activeSessionId.value = ''
      }
    }
  }

  function tryRenameDefaultSessionAfterSend(targetSessionID: string, content: string) {
    const activeMeta = sessions.value.find((item) => item.id === targetSessionID)
    if (!(activeMeta && isDefaultSessionTitle(activeMeta.title))) return
    const fallbackTitle = summarizePromptAsTitle(content)
    window.setTimeout(() => {
      const latest = sessions.value.find((item) => item.id === targetSessionID)
      if (!latest || !isDefaultSessionTitle(latest.title)) return
      renameSession(targetSessionID, fallbackTitle).catch((err) => {
        logger.warn('[codingAgentStore] fallback rename session failed', { sessionID: targetSessionID, err })
      })
    }, 1600)
  }

  return {
    loadSessions,
    buildWorkspaceSystemPrompt,
    createSession,
    switchSession,
    renameSession,
    deleteSession,
    tryRenameDefaultSessionAfterSend
  }
}
