import type { CodingAgentSession } from '@/services/coding-agent/engineAdapter'
import type { SessionMeta, SessionState } from '@/features/coding-agent/store/types'

export const DEFAULT_SESSION_TITLE = 'New Chat'

export function createEmptySessionState(): SessionState {
  return {
    messagesById: {},
    partsByMessageId: {},
    partOrderByMessageId: {},
    permissionCardsById: {},
    questionCardsById: {},
    partOrderSeq: 0,
    isStreaming: false,
    transportStatus: '',
    sessionRunStatus: '',
    lastError: null,
    lastErrorRaw: null,
    transportError: null,
    runWaitReason: '',
    lastNonHeartbeatEventAt: 0,
    seenEventIDs: {}
  }
}

export function normalizeSessionMeta(raw: CodingAgentSession): SessionMeta {
  const id = String(raw?.id || '').trim()
  const title = String(raw?.title || '').trim()
  const createdAt = String((raw as any)?.time?.created || (raw as any)?.createdAt || '')
  const updatedAt = String((raw as any)?.time?.updated || (raw as any)?.updatedAt || createdAt || '')
  return {
    id,
    title: title || DEFAULT_SESSION_TITLE,
    createdAt,
    updatedAt
  }
}

export function isDefaultSessionTitle(title: string): boolean {
  return String(title || '').trim().toLowerCase() === DEFAULT_SESSION_TITLE.toLowerCase()
}

export function summarizePromptAsTitle(content: string): string {
  const normalized = String(content || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return DEFAULT_SESSION_TITLE
  const maxLength = 40
  if (normalized.length <= maxLength) {
    return normalized
  }
  return `${normalized.slice(0, maxLength)}...`
}

export function toReadableSessionError(raw: string): string {
  const text = String(raw || '').trim()
  if (!text) return 'session error'
  if (text.includes('Unable to convert openai tool calls') || text.includes('the JSON object must be str')) {
    return '模型工具调用参数格式不兼容，本轮已中断。请直接重试；若仍失败，建议切换模型后继续。'
  }
  if (text.includes('Missing corresponding tool call') || text.includes('last_message_with_tool_calls')) {
    return '模型工具调用序列异常，已中断本轮。请重试，或先发送一条简短文本让会话恢复。'
  }
  if (text.includes('file_not_found')) {
    return '工具返回 file_not_found。请先确认目标文件路径，建议先使用 read/search 定位真实路径。'
  }
  if (text.length > 280) {
    return `${text.slice(0, 280)}...`
  }
  return text
}

export function extractSessionErrorRawMessage(payload: unknown): string {
  const queue: unknown[] = [payload]
  const visited = new Set<unknown>()
  let fallback = ''
  while (queue.length > 0) {
    const current = queue.shift()
    if (!current) continue
    if (typeof current === 'string') {
      const text = current.trim()
      if (!fallback && text) {
        fallback = text
      }
      continue
    }
    if (typeof current !== 'object') continue
    if (visited.has(current)) continue
    visited.add(current)
    const record = current as Record<string, unknown>
    const message = typeof record.message === 'string' ? record.message.trim() : ''
    if (message) return message
    if (!fallback) {
      const reason = typeof record.reason === 'string' ? record.reason.trim() : ''
      if (reason) {
        fallback = reason
      }
    }
    queue.push(record.error, record.data, record.cause, record.details, record.payload)
  }
  return fallback
}
