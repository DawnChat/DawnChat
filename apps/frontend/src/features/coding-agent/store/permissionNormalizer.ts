import type { PermissionCard } from '@/features/coding-agent/store/types'

export function normalizeEventRef(value: unknown): string {
  return String(value || '').trim()
}

export function normalizePermissionPayload(properties: Record<string, any>, eventType: string): PermissionCard | null {
  const permissionLike = properties.permission && typeof properties.permission === 'object' ? properties.permission : null
  const requestLike = properties.request && typeof properties.request === 'object' ? properties.request : null
  const source = permissionLike || requestLike || properties
  const id = String(
    source?.id || source?.requestID || source?.permissionID || properties.requestID || properties.permissionID || ''
  ).trim()
  if (!id) return null
  const response = String(source?.response || source?.reply || properties.response || properties.reply || '')
  const statusRaw = String(source?.status || '').toLowerCase()
  const status: PermissionCard['status'] =
    statusRaw === 'approved' || statusRaw === 'always' || statusRaw === 'once'
      ? 'approved'
      : statusRaw === 'rejected' || statusRaw === 'reject'
        ? 'rejected'
        : eventType === 'permission.replied'
          ? String(response).toLowerCase() === 'reject'
            ? 'rejected'
            : 'approved'
          : 'pending'
  const toolNameFromPermission = typeof source?.permission === 'string' ? source.permission : ''
  const toolNameFromTool = typeof source?.tool === 'string' ? source.tool : ''
  const tool = String(toolNameFromTool || toolNameFromPermission || source?.type || properties.tool || '').trim()
  const metadata = source?.metadata && typeof source.metadata === 'object' ? source.metadata : {}
  const patterns = Array.isArray(source?.patterns)
    ? source.patterns.filter((item: unknown) => typeof item === 'string' && String(item).trim())
    : []
  const detailParts: string[] = []
  if (typeof source?.title === 'string' && source.title.trim()) {
    detailParts.push(source.title.trim())
  }
  if (typeof source?.message === 'string' && source.message.trim()) {
    detailParts.push(source.message.trim())
  }
  if (typeof source?.reason === 'string' && source.reason.trim()) {
    detailParts.push(source.reason.trim())
  }
  if (typeof metadata?.filepath === 'string' && metadata.filepath.trim()) {
    detailParts.push(`目标路径: ${metadata.filepath.trim()}`)
  } else if (typeof source?.input?.filePath === 'string' && source.input.filePath.trim()) {
    detailParts.push(`目标路径: ${source.input.filePath.trim()}`)
  } else if (typeof source?.input?.path === 'string' && source.input.path.trim()) {
    detailParts.push(`目标路径: ${source.input.path.trim()}`)
  }
  if (typeof source?.input?.command === 'string' && source.input.command.trim()) {
    detailParts.push(`命令: ${source.input.command.trim()}`)
  }
  if (patterns.length > 0) {
    detailParts.push(`匹配规则: ${patterns.join(', ')}`)
  } else if (typeof source?.pattern === 'string' && source.pattern.trim()) {
    detailParts.push(`匹配规则: ${source.pattern.trim()}`)
  }
  if (detailParts.length === 0 && typeof metadata?.parentDir === 'string' && metadata.parentDir.trim()) {
    detailParts.push(`目标目录: ${metadata.parentDir.trim()}`)
  }
  const detail = detailParts.length > 0 ? detailParts.join('\n') : ''
  return {
    id,
    sessionID: String(source?.sessionID || properties.sessionID || ''),
    messageID: normalizeEventRef(
      source?.messageID ||
        source?.messageId ||
        source?.tool?.messageID ||
        source?.tool?.messageId ||
        source?.toolRef?.messageID ||
        source?.toolRef?.messageId ||
        properties.messageID ||
        properties.messageId
    ),
    callID: normalizeEventRef(
      source?.callID ||
        source?.callId ||
        source?.tool?.callID ||
        source?.tool?.callId ||
        source?.toolRef?.callID ||
        source?.toolRef?.callId ||
        properties.callID ||
        properties.callId
    ),
    tool,
    status,
    response,
    detail,
    metadataDiff: typeof metadata?.diff === 'string' ? String(metadata.diff || '') : ''
  }
}

