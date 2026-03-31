import { buildBackendUrl } from '../../utils/backendUrl'

const API_BASE = () => buildBackendUrl('')

export interface MobilePublishPayload {
  supabase_access_token: string
  version?: string
}

export interface MobilePublishResult {
  plugin_id: string
  version: string
  bundle_key: string
  artifact_url: string
  expires_at: string
  payload_json: Record<string, any>
  payload_text: string
  zip_sha256?: string
  zip_size?: number
  build_command?: string
}

export interface MobilePublishTask {
  id: string
  plugin_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  stage: string
  progress: number
  message: string
  created_at: string
  updated_at: string
  requested_version?: string
  error?: {
    code?: string
    message?: string
  } | null
  result?: MobilePublishResult | null
}

export interface MobilePublishStatusResult {
  plugin_id: string
  local_version: string
  manifest_version: string
  package_version: string
  version_mismatch: boolean
  last_version?: string | null
  last_status?: string | null
  last_error?: string | null
  last_result?: MobilePublishResult | null
  active_task?: MobilePublishTask | null
  metadata?: Record<string, any>
}

export class MobilePublishApiError extends Error {
  status: number
  code: string | null
  detail: string | null
  payload: unknown

  constructor(options: {
    message: string
    status: number
    code?: string | null
    detail?: string | null
    payload?: unknown
  }) {
    super(options.message)
    this.name = 'MobilePublishApiError'
    this.status = options.status
    this.code = options.code ?? null
    this.detail = options.detail ?? null
    this.payload = options.payload ?? null
  }
}

const simplifyErrorText = (value: unknown): string => {
  const text = String(value || '').trim()
  if (!text) return '请求失败'
  if (text.startsWith('{') || text.startsWith('[')) {
    return '请求失败，请查看日志中的详细响应'
  }
  return text
}

async function parseJsonOrThrow(response: Response) {
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = simplifyErrorText(data?.detail || data?.message || response.statusText)
    throw new MobilePublishApiError({
      message: detail || 'Request failed',
      status: response.status,
      code: data?.code ? String(data.code) : null,
      detail: data?.detail ? String(data.detail) : null,
      payload: data,
    })
  }
  return data
}

export function normalizeMobilePublishError(error: unknown): {
  message: string
  logContext: Record<string, unknown>
} {
  if (error instanceof MobilePublishApiError) {
    const codeLabel = error.code ? `[${error.code}] ` : ''
    return {
      message: `${codeLabel}${error.message}`.trim(),
      logContext: {
        type: error.name,
        status: error.status,
        code: error.code,
        detail: error.detail,
        payload: error.payload,
      },
    }
  }
  if (error instanceof Error) {
    return {
      message: error.message || 'Request failed',
      logContext: {
        type: error.name || 'Error',
        message: error.message,
        stack: error.stack,
      },
    }
  }
  return {
    message: 'Request failed',
    logContext: {
      type: typeof error,
      value: error,
    },
  }
}

export async function publishMobilePlugin(pluginId: string, payload: MobilePublishPayload): Promise<MobilePublishTask> {
  const response = await fetch(`${API_BASE()}/api/mobile-publish/${encodeURIComponent(pluginId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await parseJsonOrThrow(response)
  return data.data as MobilePublishTask
}

export async function fetchMobilePublishStatus(pluginId: string): Promise<MobilePublishStatusResult> {
  const response = await fetch(`${API_BASE()}/api/mobile-publish/${encodeURIComponent(pluginId)}/status`)
  const data = await parseJsonOrThrow(response)
  return data.data as MobilePublishStatusResult
}

export async function fetchMobilePublishTask(pluginId: string, taskId: string): Promise<MobilePublishTask> {
  const response = await fetch(`${API_BASE()}/api/mobile-publish/${encodeURIComponent(pluginId)}/tasks/${encodeURIComponent(taskId)}`)
  const data = await parseJsonOrThrow(response)
  return data.data as MobilePublishTask
}

export async function refreshMobileShare(pluginId: string, accessToken: string): Promise<MobilePublishResult> {
  const response = await fetch(`${API_BASE()}/api/mobile-publish/${encodeURIComponent(pluginId)}/refresh-share`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ supabase_access_token: accessToken }),
  })
  const data = await parseJsonOrThrow(response)
  return data.data as MobilePublishResult
}
