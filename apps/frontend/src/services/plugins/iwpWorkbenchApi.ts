import { API_BASE } from '@/stores/plugin/api/client'

export interface IwpMarkdownFileMeta {
  path: string
  name: string
  size: number
  updated_at: string
}

export interface IwpFileListPayload {
  iwp_root: string
  files: IwpMarkdownFileMeta[]
}

export interface IwpReadFilePayload {
  iwp_root: string
  path: string
  content: string
  content_hash: string
  updated_at: string
}

export interface IwpSaveFilePayload {
  path: string
  content_hash: string
  updated_at: string
}

export interface IwpBuildTaskPayload {
  task_id: string
  plugin_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  stage: string
  message: string
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
  result: Record<string, unknown> | null
  error: string | null
}

const parseResponse = async <T>(res: Response): Promise<T> => {
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `Request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export const listIwpFiles = async (pluginId: string): Promise<IwpFileListPayload> => {
  const data = await parseResponse<{ status: string; iwp_root: string; files: IwpMarkdownFileMeta[] }>(
    await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(pluginId)}/iwp/files`)
  )
  return {
    iwp_root: String(data.iwp_root || 'InstructWare.iw'),
    files: Array.isArray(data.files) ? data.files : [],
  }
}

export const readIwpFile = async (pluginId: string, path: string): Promise<IwpReadFilePayload> => {
  const query = new URLSearchParams({ path }).toString()
  const data = await parseResponse<{
    status: string
    iwp_root: string
    path: string
    content: string
    content_hash: string
    updated_at: string
  }>(await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(pluginId)}/iwp/file?${query}`))
  return {
    iwp_root: String(data.iwp_root || 'InstructWare.iw'),
    path: String(data.path || path),
    content: String(data.content || ''),
    content_hash: String(data.content_hash || ''),
    updated_at: String(data.updated_at || ''),
  }
}

export const saveIwpFile = async (
  pluginId: string,
  payload: { path: string; content: string; expected_hash?: string }
): Promise<IwpSaveFilePayload> => {
  const data = await parseResponse<{ status: string; path: string; content_hash: string; updated_at: string }>(
    await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(pluginId)}/iwp/file`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: payload.path,
        content: payload.content,
        expected_hash: payload.expected_hash || '',
      }),
    })
  )
  return {
    path: String(data.path || payload.path),
    content_hash: String(data.content_hash || ''),
    updated_at: String(data.updated_at || ''),
  }
}

export const startIwpBuild = async (pluginId: string): Promise<{ task_id: string }> => {
  const data = await parseResponse<{ status: string; task_id: string }>(
    await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(pluginId)}/iwp/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'workbench_mvp_build' }),
    })
  )
  return { task_id: String(data.task_id || '') }
}

export const getIwpBuildTask = async (pluginId: string, taskId: string): Promise<IwpBuildTaskPayload> => {
  const data = await parseResponse<{ status: string; data: IwpBuildTaskPayload }>(
    await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(pluginId)}/iwp/build/${encodeURIComponent(taskId)}`)
  )
  return data.data
}
