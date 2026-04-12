import { buildBackendUrl } from '../../utils/backendUrl'
import { logger } from '../../utils/logger'
import { createOpencodeClient } from '@opencode-ai/sdk/client'

type OpencodeSdkClient = ReturnType<typeof createOpencodeClient>
import type {
  CodingAgentEvent,
  CodingAgentMessage,
  CodingAgentPermissionRequest,
  CodingAgentQuestionAnswer,
  CodingAgentQuestionRequest,
  CodingAgentSession,
  EngineAdapter,
  PermissionDecision,
  PromptPayload,
  SessionQueryOptions
} from './engineAdapter'

interface OpenCodeHealthResponse {
  status: string
  data?: {
    base_url?: string
    healthy?: boolean
    status?: string
  }
}

export interface OpenCodeHealthSnapshot {
  baseUrl: string
  backendStatus: string
  healthy: boolean
}

const FULL_STREAM_LOG_KEY = 'codingAgent:opencode:logFullStream'
const STREAM_STALE_TIMEOUT_MS = 30000
const STREAM_STALE_CHECK_INTERVAL_MS = 5000

export async function fetchOpenCodeHealthSnapshot(): Promise<OpenCodeHealthSnapshot> {
  const healthUrl = buildBackendUrl('/api/opencode/health')
  const healthResp = await fetch(healthUrl)
  if (!healthResp.ok) {
    throw new Error(`OpenCode 健康检查失败: ${healthResp.status}`)
  }
  const healthJson = (await healthResp.json()) as OpenCodeHealthResponse
  const payload = healthJson?.data || {}
  const baseUrl = String(payload.base_url || '').trim()
  const backendStatus = String(payload.status || '').toLowerCase()
  const healthy = Boolean(payload.healthy)
  if (!baseUrl) {
    throw new Error('OpenCode base_url 缺失')
  }
  return {
    baseUrl,
    backendStatus,
    healthy
  }
}

class OpenCodeAdapter implements EngineAdapter {
  private baseUrl = ''
  private eventController: AbortController | null = null
  private sdkClient: OpencodeSdkClient | null = null
  private sdkBaseUrl = ''
  private eventDebugBudget = 20

  private shouldLogFullStream(): boolean {
    try {
      const value = localStorage.getItem(FULL_STREAM_LOG_KEY)
      if (value === null) {
        return false
      }
      return String(value || '').toLowerCase() !== 'false'
    } catch {
      return false
    }
  }

  private summarizeStreamEvent(raw: unknown, evt: CodingAgentEvent | null): Record<string, unknown> {
    const eventLike =
      evt ||
      (raw && typeof raw === 'object' && raw !== null && 'type' in raw && typeof (raw as { type?: unknown }).type === 'string'
        ? (raw as CodingAgentEvent)
        : null)
    const properties = (eventLike?.properties || {}) as Record<string, unknown>
    const partRaw = properties.part
    const part = partRaw && typeof partRaw === 'object' && partRaw !== null ? (partRaw as Record<string, unknown>) : {}
    const stateRaw = part.state
    const state = stateRaw && typeof stateRaw === 'object' && stateRaw !== null ? (stateRaw as Record<string, unknown>) : {}
    const delta = properties.delta
    const output = state.output
    const metadata = state.metadata
    const infoRaw = properties.info
    const infoId =
      infoRaw && typeof infoRaw === 'object' && infoRaw !== null && 'id' in infoRaw
        ? String((infoRaw as { id?: unknown }).id || '')
        : ''
    return {
      type: String(eventLike?.type || ''),
      sessionID: String(
        eventLike?.sessionID ||
          properties.sessionID ||
          properties.sessionId ||
          part.sessionID ||
          ''
      ),
      messageID: String(properties.messageID || part.messageID || infoId || ''),
      partID: String(properties.partID || part.id || ''),
      tool: String(part.tool || ''),
      toolStatus: String(state.status || ''),
      deltaLength: typeof delta === 'string' ? delta.length : 0,
      outputLength: typeof output === 'string' ? output.length : 0,
      metadataKeys: metadata && typeof metadata === 'object' ? Object.keys(metadata as object).slice(0, 8) : []
    }
  }

  private async ensureReady(): Promise<void> {
    await this.ensureServerHealthy()
  }

  private async ensureServerHealthy(): Promise<void> {
    const snapshot = await fetchOpenCodeHealthSnapshot()
    const healthBase = snapshot.baseUrl
    const backendState = snapshot.backendStatus
    const healthy = snapshot.healthy
    if (!healthy || !['running', 'starting'].includes(backendState)) {
      throw new Error('OpenCode 未就绪，请先初始化插件工作区')
    }
    this.baseUrl = healthBase
    if (this.sdkBaseUrl !== this.baseUrl) {
      this.sdkBaseUrl = this.baseUrl
      this.sdkClient = null
    }
  }

  private getSdkClient(): OpencodeSdkClient {
    if (this.sdkClient && this.sdkBaseUrl === this.baseUrl) {
      return this.sdkClient
    }
    this.sdkBaseUrl = this.baseUrl
    this.sdkClient = createOpencodeClient({
      baseUrl: this.baseUrl,
      throwOnError: true
    })
    return this.sdkClient
  }

  private static toEvent(raw: unknown): CodingAgentEvent | null {
    if (raw && typeof raw === 'object' && raw !== null && 'type' in raw && typeof (raw as { type?: unknown }).type === 'string') {
      return raw as CodingAgentEvent
    }
    if (
      raw &&
      typeof raw === 'object' &&
      raw !== null &&
      'data' in raw &&
      (raw as { data?: unknown }).data &&
      typeof (raw as { data: { type?: unknown } }).data === 'object' &&
      typeof (raw as { data: { type?: unknown } }).data.type === 'string'
    ) {
      return (raw as { data: CodingAgentEvent }).data
    }
    return null
  }

  private buildSessionUrl(path = '', options?: SessionQueryOptions): string {
    const url = new URL(`${this.baseUrl}/session${path}`)
    const directory = String(options?.directory || '').trim()
    if (directory) {
      url.searchParams.set('directory', directory)
    }
    return url.toString()
  }

  async listSessions(options?: SessionQueryOptions): Promise<CodingAgentSession[]> {
    await this.ensureReady()
    const resp = await fetch(this.buildSessionUrl('', options))
    if (!resp.ok) {
      throw new Error(`读取会话列表失败: ${resp.status}`)
    }
    const rows = (await resp.json()) as CodingAgentSession[]
    return Array.isArray(rows) ? rows : []
  }

  async getSession(sessionId: string): Promise<CodingAgentSession | null> {
    await this.ensureReady()
    const resp = await fetch(`${this.baseUrl}/session/${encodeURIComponent(sessionId)}`)
    if (!resp.ok) {
      if (resp.status === 404) return null
      throw new Error(`读取会话失败: ${resp.status}`)
    }
    return (await resp.json()) as CodingAgentSession
  }

  async createSession(title?: string, options?: SessionQueryOptions): Promise<string> {
    await this.ensureReady()
    const resp = await fetch(this.buildSessionUrl('', options), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(title ? { title } : {})
    })
    if (!resp.ok) {
      throw new Error(`创建会话失败: ${resp.status}`)
    }
    const json = await resp.json()
    const id = json?.id
    if (!id) {
      throw new Error('创建会话失败：未返回 session id')
    }
    return String(id)
  }

  async updateSession(sessionId: string, patch: { title?: string }): Promise<CodingAgentSession | null> {
    await this.ensureReady()
    const resp = await fetch(`${this.baseUrl}/session/${encodeURIComponent(sessionId)}`, {
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
    const resp = await fetch(`${this.baseUrl}/session/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE'
    })
    if (!resp.ok) {
      if (resp.status === 404) return false
      throw new Error(`删除会话失败: ${resp.status}`)
    }
    const data = await resp.json().catch(() => true)
    return typeof data === 'boolean' ? data : true
  }

  async listMessages(sessionId: string): Promise<CodingAgentMessage[]> {
    await this.ensureReady()
    const resp = await fetch(`${this.baseUrl}/session/${encodeURIComponent(sessionId)}/message`)
    if (!resp.ok) {
      throw new Error(`读取消息失败: ${resp.status}`)
    }
    const rows = (await resp.json()) as CodingAgentMessage[]
    return Array.isArray(rows) ? rows : []
  }

  async getSessionTodos(
    sessionId: string
  ): Promise<Array<{ id?: string; content?: string; status?: string; priority?: string }>> {
    await this.ensureReady()
    const resp = await fetch(`${this.baseUrl}/session/${encodeURIComponent(sessionId)}/todo`)
    if (!resp.ok) {
      if (resp.status === 404) return []
      throw new Error(`读取待办失败: ${resp.status}`)
    }
    const rows = (await resp.json()) as Array<{ id?: string; content?: string; status?: string; priority?: string }>
    return Array.isArray(rows) ? rows : []
  }

  async prompt(sessionId: string, payload: PromptPayload): Promise<CodingAgentMessage | null> {
    await this.ensureReady()
    const resp = await fetch(`${this.baseUrl}/session/${encodeURIComponent(sessionId)}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!resp.ok) {
      throw new Error(`发送消息失败: ${resp.status}`)
    }
    const data = (await resp.json()) as CodingAgentMessage
    return data
  }

  async promptAsync(sessionId: string, payload: PromptPayload): Promise<void> {
    await this.ensureReady()
    const resp = await fetch(`${this.baseUrl}/session/${encodeURIComponent(sessionId)}/prompt_async`, {
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
    const resp = await fetch(`${this.baseUrl}/session/${encodeURIComponent(sessionId)}/abort`, {
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
    const resp = await fetch(`${this.baseUrl}/session/${encodeURIComponent(sessionId)}/message`, {
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
      `${this.baseUrl}/session/${encodeURIComponent(sessionId)}/permissions/${encodeURIComponent(permissionId)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          response,
          ...(remember === undefined ? {} : { remember })
        })
      }
    )
    if (!resp.ok) {
      if (resp.status === 404) {
        throw new Error('权限请求不存在或已失效，请刷新会话后重试')
      }
      throw new Error(`权限响应失败: ${resp.status}`)
    }
    const data = await resp.json().catch(() => true)
    return typeof data === 'boolean' ? data : true
  }

  supportsQuestions(): boolean {
    return true
  }

  async listQuestions(sessionId?: string): Promise<CodingAgentQuestionRequest[]> {
    await this.ensureReady()
    const resp = await fetch(`${this.baseUrl}/question`)
    if (!resp.ok) {
      throw new Error(`读取问题列表失败: ${resp.status}`)
    }
    const rows = (await resp.json()) as CodingAgentQuestionRequest[]
    const all = Array.isArray(rows) ? rows : []
    const targetSessionId = String(sessionId || '').trim()
    if (!targetSessionId) {
      return all
    }
    return all.filter((item) => String(item?.sessionID || '').trim() === targetSessionId)
  }

  async replyQuestion(requestId: string, answers: CodingAgentQuestionAnswer[]): Promise<boolean> {
    await this.ensureReady()
    const resp = await fetch(`${this.baseUrl}/question/${encodeURIComponent(requestId)}/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers })
    })
    if (!resp.ok) {
      throw new Error(`问题答复失败: ${resp.status}`)
    }
    const data = await resp.json().catch(() => true)
    return typeof data === 'boolean' ? data : true
  }

  async rejectQuestion(requestId: string): Promise<boolean> {
    await this.ensureReady()
    const resp = await fetch(`${this.baseUrl}/question/${encodeURIComponent(requestId)}/reject`, {
      method: 'POST'
    })
    if (!resp.ok) {
      throw new Error(`问题拒绝失败: ${resp.status}`)
    }
    const data = await resp.json().catch(() => true)
    return typeof data === 'boolean' ? data : true
  }

  async listPermissions(sessionId?: string): Promise<CodingAgentPermissionRequest[]> {
    await this.ensureReady()
    const resp = await fetch(`${this.baseUrl}/permission`)
    if (!resp.ok) {
      throw new Error(`读取权限列表失败: ${resp.status}`)
    }
    const payload: unknown = await resp.json().catch(() => [])
    const payloadObj = payload && typeof payload === 'object' && payload !== null ? (payload as { data?: unknown }) : null
    const usedDataField = !Array.isArray(payload) && Array.isArray(payloadObj?.data)
    const rows = Array.isArray(payload) ? payload : usedDataField ? (payloadObj?.data as unknown[]) : []
    if (usedDataField) {
      logger.debug('[OpenCodeAdapter] listPermissions parsed from data field')
    }
    const all = rows.filter((item: unknown) => item && typeof item === 'object') as CodingAgentPermissionRequest[]
    const targetSessionId = String(sessionId || '').trim()
    if (!targetSessionId) {
      return all
    }
    return all.filter((item) => {
      const direct = String(item?.sessionID || '').trim()
      if (direct) return direct === targetSessionId
      const tool = item.tool
      const toolSession =
        tool && typeof tool === 'object' && tool !== null && 'sessionID' in tool
          ? String((tool as { sessionID?: unknown }).sessionID || '').trim()
          : ''
      return toolSession === targetSessionId
    })
  }

  async subscribeEvents(onEvent: (evt: CodingAgentEvent) => void): Promise<() => void> {
    await this.ensureReady()
    this.eventController?.abort()
    this.eventController = new AbortController()
    this.eventDebugBudget = 20
    const fullStreamLogEnabled = this.shouldLogFullStream()
    logger.info('[OpenCodeAdapter] subscribe start', {
      baseUrl: this.baseUrl,
      fullStreamLogEnabled
    })
    let cancelled = false
    let staleTriggered = false
    let staleMonitor: number | null = null
    let lastEventAt = Date.now()
    const transportInstanceId = `opencode-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`

    ;(async () => {
      const clearStaleMonitor = () => {
        if (staleMonitor !== null) {
          window.clearInterval(staleMonitor)
          staleMonitor = null
        }
      }
      const touchEventAt = () => {
        lastEventAt = Date.now()
        staleTriggered = false
      }
      const emitStatus = (
        status: 'connecting' | 'reconnecting' | 'streaming' | 'closed',
        extra?: Record<string, unknown>
      ) => {
        onEvent({
          type: 'stream.status',
          properties: {
            status,
            transport_instance_id: transportInstanceId,
            last_event_at: new Date(lastEventAt).toISOString(),
            ...(extra || {})
          }
        })
      }

      try {
        emitStatus('connecting')
        staleMonitor = window.setInterval(() => {
          if (cancelled || staleTriggered) return
          const staleDurationMs = Date.now() - lastEventAt
          if (staleDurationMs < STREAM_STALE_TIMEOUT_MS) return
          staleTriggered = true
          logger.warn('[OpenCodeAdapter] stream stale detected, forcing resubscribe', {
            transport_instance_id: transportInstanceId,
            stale_duration_ms: staleDurationMs,
            last_event_at: new Date(lastEventAt).toISOString(),
            recover_reason: 'stale_timeout'
          })
          emitStatus('reconnecting', {
            error: 'SSE stream quiet timeout',
            stale_duration_ms: staleDurationMs,
            recover_reason: 'stale_timeout'
          })
          this.eventController?.abort()
        }, STREAM_STALE_CHECK_INTERVAL_MS)
        // Refresh client per subscription to avoid stale SSE handlers after reconnect/restart.
        this.sdkClient = null
        const client = this.getSdkClient()
        const streamResp = await client.event.subscribe({
          signal: this.eventController?.signal,
          onSseError: (err: unknown) => {
            if (cancelled) return
            // The SDK already retries SSE internally. We only surface the transport
            // state for diagnostics and UI hints instead of driving recovery here.
            logger.warn('[OpenCodeAdapter] onSseError', {
              error: err instanceof Error ? err.message : String(err)
            })
            emitStatus('reconnecting', {
              error: err instanceof Error ? err.message : String(err),
              recover_reason: 'sdk_sse_error'
            })
          }
        })
        logger.info('[OpenCodeAdapter] subscribe established')
        emitStatus('streaming')
        for await (const raw of streamResp.stream as AsyncIterable<unknown>) {
          if (cancelled) break
          touchEventAt()
          const evt = OpenCodeAdapter.toEvent(raw)
          if (fullStreamLogEnabled) {
            logger.info('[OpenCodeAdapter] stream event full', this.summarizeStreamEvent(raw, evt))
          }
          if (evt) {
            if (this.eventDebugBudget > 0) {
              this.eventDebugBudget -= 1
              logger.debug('[OpenCodeAdapter] stream event', {
                type: String(evt.type || ''),
                sessionID: String(evt.sessionID || evt.properties?.sessionID || ''),
                hasPart: Boolean(evt.properties?.part),
                hasDelta: typeof evt.properties?.delta === 'string'
              })
            }
            if (String(evt.type || '') === 'message.part.delta') {
              const delta = String(evt.properties?.delta ?? '').toLowerCase()
              if (
                delta.includes('plan mode is active') ||
                delta.includes('operational mode has changed from plan to build') ||
                delta.includes('a plan file exists at')
              ) {
                const p = evt.properties || {}
                logger.info('[OpenCodeAdapter] plan-like delta observed', {
                  sessionID: String(evt.sessionID || p.sessionID || ''),
                  messageID: String(p.messageID || ''),
                  partID: String(p.partID || '')
                })
              }
            }
            onEvent(evt)
            continue
          }
          logger.warn('[OpenCodeAdapter] invalid event payload from sdk stream', { raw })
        }
      } catch (err) {
        if (!cancelled) {
          const errorText = err instanceof Error ? err.message : String(err)
          if (staleTriggered) {
            logger.warn('[OpenCodeAdapter] event stream aborted for stale recovery', {
              transport_instance_id: transportInstanceId,
              error: errorText,
              recover_reason: 'stale_timeout'
            })
          } else {
            logger.error('[OpenCodeAdapter] event stream stopped', err)
          }
        }
      } finally {
        clearStaleMonitor()
        logger.info('[OpenCodeAdapter] subscribe closed')
        emitStatus('closed', {
          recover_reason: staleTriggered ? 'stale_timeout' : 'stream_closed'
        })
      }
    })().catch((err) => {
      logger.error('[OpenCodeAdapter] event loop failed', err)
      if (!cancelled) {
        onEvent({
          type: 'stream.status',
          properties: {
            status: 'closed',
            error: err instanceof Error ? err.message : String(err)
          }
        })
      }
    })

    return () => {
      cancelled = true
      this.eventController?.abort()
    }
  }
}

export const openCodeAdapter: EngineAdapter = new OpenCodeAdapter()
