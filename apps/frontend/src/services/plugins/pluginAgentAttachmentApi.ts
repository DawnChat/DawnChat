import { API_BASE } from '@/stores/plugin/api/client'

export interface PluginAgentAttachmentPayload {
  plugin_id: string
  filename: string
  stored_path: string
  size_bytes: number
}

const parseUploadError = async (res: Response): Promise<string> => {
  try {
    const data = (await res.json()) as { detail?: string }
    const detail = String(data?.detail || '').trim()
    if (detail) return detail
  } catch {
    // noop
  }
  const fallback = await res.text().catch(() => '')
  return fallback || `Request failed: ${res.status}`
}

export const uploadPluginAgentAttachment = async (
  pluginId: string,
  file: File
): Promise<PluginAgentAttachmentPayload> => {
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${API_BASE()}/api/plugins/${encodeURIComponent(pluginId)}/agent-attachments`, {
    method: 'POST',
    body: formData
  })
  if (!res.ok) {
    throw new Error(await parseUploadError(res))
  }
  const data = (await res.json()) as {
    status: string
    plugin_id: string
    filename: string
    stored_path: string
    size_bytes: number
  }
  return {
    plugin_id: String(data.plugin_id || pluginId),
    filename: String(data.filename || file.name),
    stored_path: String(data.stored_path || ''),
    size_bytes: Number(data.size_bytes || 0)
  }
}
