import type { PermissionCard } from '@/features/coding-agent/store/types'

export function normalizeEventRef(value: unknown): string {
  return String(value || '').trim()
}

function asObjectRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

export function normalizePermissionPayload(properties: Record<string, unknown>, eventType: string): PermissionCard | null {
  const permissionLike = asObjectRecord(properties.permission)
  const requestLike = asObjectRecord(properties.request)
  const source = permissionLike || requestLike || properties
  const toolNested = asObjectRecord(source.tool)
  const toolRefNested = asObjectRecord(source.toolRef)
  const inputNested = asObjectRecord(source.input)
  const metadata =
    source.metadata && typeof source.metadata === 'object' && !Array.isArray(source.metadata)
      ? (source.metadata as Record<string, unknown>)
      : {}
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
  } else if (typeof inputNested?.filePath === 'string' && inputNested.filePath.trim()) {
    detailParts.push(`目标路径: ${String(inputNested.filePath).trim()}`)
  } else if (typeof inputNested?.path === 'string' && inputNested.path.trim()) {
    detailParts.push(`目标路径: ${String(inputNested.path).trim()}`)
  }
  if (typeof inputNested?.command === 'string' && inputNested.command.trim()) {
    detailParts.push(`命令: ${String(inputNested.command).trim()}`)
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
      source.messageID ||
        source.messageId ||
        toolNested?.messageID ||
        toolNested?.messageId ||
        toolRefNested?.messageID ||
        toolRefNested?.messageId ||
        properties.messageID ||
        properties.messageId
    ),
    callID: normalizeEventRef(
      source.callID ||
        source.callId ||
        toolNested?.callID ||
        toolNested?.callId ||
        toolRefNested?.callID ||
        toolRefNested?.callId ||
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

