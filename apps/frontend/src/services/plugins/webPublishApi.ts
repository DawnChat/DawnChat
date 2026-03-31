import { buildBackendUrl } from '../../utils/backendUrl'

const API_BASE = () => buildBackendUrl('')

export interface WebPublishPayload {
  supabase_access_token: string
  slug?: string
  title?: string
  description?: string
  version?: string
  initial_visibility?: 'private' | 'public' | 'unlisted'
}

export interface WebPublishResult {
  plugin_id: string
  web_app: {
    id: string
    plugin_id: string
    slug: string
    public_slug?: string | null
    title: string
    description: string
    framework: string
    visibility: string
    status: string
  }
  release: {
    id: string
    web_app_id: string
    version: string
    status: string
    published_at: string
  }
  runtime_url?: string
  artifact_count: number
  local_version?: string
  remote_latest_version?: string
}

export interface WebPublishTask {
  id: string
  plugin_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  stage: string
  progress: number
  message: string
  created_at: string
  updated_at: string
  requested_slug?: string
  requested_version?: string
  error?: {
    code?: string
    message?: string
  } | null
  result?: WebPublishResult | null
}

export interface WebPublishStatusResult {
  plugin_id: string
  local_version: string
  manifest_version: string
  package_version: string
  version_mismatch: boolean
  remote_latest_version?: string | null
  remote_release_status?: string | null
  current_status: string
  current_slug?: string
  visibility?: 'private' | 'public' | 'unlisted' | null
  public_slug?: string | null
  private_runtime_url?: string
  public_runtime_url?: string
  runtime_url?: string
  last_published_at?: string | null
  active_task?: WebPublishTask | null
  metadata?: Record<string, any>
  remote_error?: {
    code?: string
    message?: string
  } | null
}

export class WebPublishApiError extends Error {
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
    this.name = 'WebPublishApiError'
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
    throw new WebPublishApiError({
      message: detail || 'Request failed',
      status: response.status,
      code: data?.code ? String(data.code) : null,
      detail: data?.detail ? String(data.detail) : null,
      payload: data,
    })
  }
  return data
}

function buildAuthHeaders(accessToken?: string): HeadersInit | undefined {
  const token = String(accessToken || '').trim()
  if (!token) return undefined
  return {
    Authorization: `Bearer ${token}`,
  }
}

export function normalizeWebPublishError(error: unknown): {
  message: string
  logContext: Record<string, unknown>
} {
  if (error instanceof WebPublishApiError) {
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

export async function publishWebPlugin(pluginId: string, payload: WebPublishPayload): Promise<WebPublishTask> {
  const response = await fetch(`${API_BASE()}/api/web-publish/${encodeURIComponent(pluginId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await parseJsonOrThrow(response)
  return data.data as WebPublishTask
}

export async function fetchWebPublishStatus(pluginId: string, accessToken?: string): Promise<WebPublishStatusResult> {
  const response = await fetch(`${API_BASE()}/api/web-publish/${encodeURIComponent(pluginId)}/status`, {
    headers: buildAuthHeaders(accessToken),
  })
  const data = await parseJsonOrThrow(response)
  return data.data as WebPublishStatusResult
}

export async function fetchWebPublishTask(pluginId: string, taskId: string): Promise<WebPublishTask> {
  const response = await fetch(`${API_BASE()}/api/web-publish/${encodeURIComponent(pluginId)}/tasks/${encodeURIComponent(taskId)}`)
  const data = await parseJsonOrThrow(response)
  return data.data as WebPublishTask
}
