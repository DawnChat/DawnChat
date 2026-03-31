import { buildBackendUrl } from '../../utils/backendUrl'
import { logger } from '../../utils/logger'
import { startSseClient } from './sseClient'
import type {
  AgentOption,
  CodingAgentEvent,
  CodingAgentMessage,
  CodingAgentQuestionAnswer,
  CodingAgentQuestionRequest,
  ModelOption,
  CodingAgentSession,
  EngineAdapter,
  PermissionDecision,
  PromptPayload,
  SessionQueryOptions
} from './engineAdapter'

export interface AgentV3HealthSnapshot {
  healthy: boolean
  payload: Record<string, unknown>
}

export async function fetchAgentV3HealthSnapshot(): Promise<AgentV3HealthSnapshot> {
  const resp = await fetch(buildBackendUrl('/api/agentv3/engine/meta'))
  if (!resp.ok) {
    throw new Error(`AgentV3 未就绪: ${resp.status}`)
  }
  const payload = (await resp.json()) as Record<string, unknown>
  return {
    healthy: true,
    payload
  }
}

class AgentV3Adapter implements EngineAdapter {
  private eventController: AbortController | null = null

  private async ensureReady(): Promise<void> {
    await fetchAgentV3HealthSnapshot()
  }

  async listSessions(_options?: SessionQueryOptions): Promise<CodingAgentSession[]> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl('/api/agentv3/session'))
    if (!resp.ok) {
      throw new Error(`读取会话列表失败: ${resp.status}`)
    }
    const rows = (await resp.json()) as CodingAgentSession[]
    return Array.isArray(rows) ? rows : []
  }

  async getSession(sessionId: string): Promise<CodingAgentSession | null> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl(`/api/agentv3/session/${encodeURIComponent(sessionId)}`))
    if (!resp.ok) {
      if (resp.status === 404) return null
      throw new Error(`读取会话失败: ${resp.status}`)
    }
    return (await resp.json()) as CodingAgentSession
  }

  async createSession(title?: string, options?: SessionQueryOptions): Promise<string> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl('/api/agentv3/session'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...(title ? { title } : {}),
        ...(options?.workspacePath ? { workspace_path: options.workspacePath } : {}),
        ...(options?.workspaceKind ? { workspace_kind: options.workspaceKind } : {}),
        ...(options?.pluginId ? { plugin_id: options.pluginId } : {}),
        ...(options?.projectId ? { project_id: options.projectId } : {})
      })
    })
    if (!resp.ok) {
      throw new Error(`创建会话失败: ${resp.status}`)
    }
    const data = await resp.json()
    const id = data?.id
    if (!id) {
      throw new Error('创建会话失败：未返回 session id')
    }
    return String(id)
  }

  async updateSession(sessionId: string, patch: { title?: string }): Promise<CodingAgentSession | null> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl(`/api/agentv3/session/${encodeURIComponent(sessionId)}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch || {})
    })
    if (!resp.ok) {
      if (resp.status === 404) return null
      throw new Error(`更新会话失败: ${resp.status}`)
    }
    return (await resp.json()) as CodingAgentSession
  }

  async deleteSession(sessionId: string): Promise<boolean> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl(`/api/agentv3/session/${encodeURIComponent(sessionId)}`), {
      method: 'DELETE'
    })
    if (!resp.ok) {
      if (resp.status === 404) return false
      throw new Error(`删除会话失败: ${resp.status}`)
    }
    return true
  }

  async listMessages(sessionId: string): Promise<CodingAgentMessage[]> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl(`/api/agentv3/session/${encodeURIComponent(sessionId)}/message`))
    if (!resp.ok) {
      throw new Error(`读取消息失败: ${resp.status}`)
    }
    const rows = (await resp.json()) as CodingAgentMessage[]
    return Array.isArray(rows) ? rows : []
  }

  async listAgents(): Promise<AgentOption[]> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl('/api/agentv3/agents'))
    if (!resp.ok) {
      throw new Error(`读取 Agent 列表失败: ${resp.status}`)
    }
    const rows = (await resp.json()) as AgentOption[]
    return Array.isArray(rows) ? rows : []
  }

  async listModels(): Promise<ModelOption[]> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl('/api/agentv3/models'))
    if (!resp.ok) {
      throw new Error(`读取模型列表失败: ${resp.status}`)
    }
    const rows = (await resp.json()) as ModelOption[]
    return Array.isArray(rows) ? rows : []
  }

  async updateSessionConfig(
    sessionId: string,
    patch: {
      agent?: string
      model?: {
        providerID: string
        modelID: string
      }
    }
  ): Promise<CodingAgentSession | null> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl(`/api/agentv3/session/${encodeURIComponent(sessionId)}/config`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch || {})
    })
    if (!resp.ok) {
      if (resp.status === 404) return null
      throw new Error(`更新会话配置失败: ${resp.status}`)
    }
    return (await resp.json()) as CodingAgentSession
  }

  async prompt(sessionId: string, payload: PromptPayload): Promise<CodingAgentMessage | null> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl(`/api/agentv3/session/${encodeURIComponent(sessionId)}/message`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!resp.ok) {
      throw new Error(`发送消息失败: ${resp.status}`)
    }
    return (await resp.json()) as CodingAgentMessage
  }

  async promptAsync(sessionId: string, payload: PromptPayload): Promise<void> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl(`/api/agentv3/session/${encodeURIComponent(sessionId)}/prompt_async`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!resp.ok) {
      throw new Error(`异步发送消息失败: ${resp.status}`)
    }
  }

  async interruptSession(sessionId: string): Promise<boolean> {
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl(`/api/agentv3/session/${encodeURIComponent(sessionId)}/interrupt`), {
      method: 'POST'
    })
    if (!resp.ok) {
      if (resp.status === 404) return false
      throw new Error(`中断会话失败: ${resp.status}`)
    }
    const data = await resp.json().catch(() => true)
    return typeof data === 'boolean' ? data : true
  }

  async injectContext(sessionId: string, text: string): Promise<void> {
    const content = String(text || '').trim()
    if (!content) return
    await this.ensureReady()
    const resp = await fetch(buildBackendUrl(`/api/agentv3/session/${encodeURIComponent(sessionId)}/message`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        noReply: true,
        parts: [{ type: 'text', text: content }]
      })
    })
    if (!resp.ok) {
      throw new Error(`注入上下文失败: ${resp.status}`)
    }
  }

  async replyPermission(
    sessionId: string,
    permissionId: string,
    response: PermissionDecision,
    remember?: boolean
  ): Promise<boolean> {
    await this.ensureReady()
    const resp = await fetch(
      buildBackendUrl(
        `/api/agentv3/session/${encodeURIComponent(sessionId)}/permissions/${encodeURIComponent(permissionId)}`
      ),
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ response, ...(remember === undefined ? {} : { remember }) })
      }
    )
    if (!resp.ok) {
      throw new Error(`权限响应失败: ${resp.status}`)
    }
    return true
  }

  supportsQuestions(): boolean {
    return false
  }

  // Contract placeholder: keep method signatures aligned with OpenCode adapter so
  // AgentV3 can be enabled later without changing UI/store call sites.
  async listQuestions(): Promise<CodingAgentQuestionRequest[]> {
    return []
  }

  async replyQuestion(_requestId: string, _answers: CodingAgentQuestionAnswer[]): Promise<boolean> {
    throw new Error('AgentV3 暂不支持 question 交互')
  }

  async rejectQuestion(_requestId: string): Promise<boolean> {
    throw new Error('AgentV3 暂不支持 question 交互')
  }

  async subscribeEvents(onEvent: (evt: CodingAgentEvent) => void): Promise<() => void> {
    await this.ensureReady()
    this.eventController?.abort()
    this.eventController = new AbortController()
    let cancelled = false

    ;(async () => {
      await startSseClient({
        url: buildBackendUrl('/api/agentv3/event'),
        signal: this.eventController?.signal as AbortSignal,
        initialRetryDelayMs: 1000,
        maxRetryDelayMs: 30000,
        onStatus: (status, meta) => {
          if (cancelled) return
          onEvent({
            type: 'stream.status',
            properties: {
              status,
              ...meta
            }
          })
        },
        onEvent: (event, meta) => {
          if (cancelled) return
          try {
            const evt = JSON.parse(event.data) as CodingAgentEvent & { eventID?: number | string }
            const eventId = String(evt.eventID ?? event.id ?? '').trim()
            if (eventId && evt.eventID === undefined) {
              const parsed = Number(eventId)
              ;(evt as CodingAgentEvent & { eventID?: number }).eventID = Number.isFinite(parsed) ? parsed : undefined
            }
            onEvent(evt)
          } catch (err) {
            logger.warn('[AgentV3Adapter] invalid event payload', { payload: event.data, err, meta })
          }
        },
        onError: (err, meta) => {
          logger.warn('[AgentV3Adapter] event stream interrupted, retrying', { err, ...meta })
        }
      })
    })().catch((err) => logger.error('[AgentV3Adapter] event loop failed', err))

    return () => {
      cancelled = true
      this.eventController?.abort()
    }
  }
}

export const agentV3Adapter: EngineAdapter = new AgentV3Adapter()

