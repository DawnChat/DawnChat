import type { CodingAgentPart } from '@/services/coding-agent/engineAdapter'
import type { SessionTodoItem, ToolDisplayMeta } from '@/features/coding-agent/store/types'

export function normalizeSessionTodos(input: any[]): SessionTodoItem[] {
  const order: string[] = []
  const byKey: Record<string, SessionTodoItem> = {}
  for (const raw of Array.isArray(input) ? input : []) {
    const content = String(raw?.content || '').trim()
    if (!content) continue
    const explicitId = String(raw?.id || '').trim()
    const normalizedContent = content.toLowerCase().replace(/\s+/g, ' ')
    const key = explicitId || `content:${normalizedContent}`
    if (!byKey[key]) {
      order.push(key)
    }
    byKey[key] = {
      id: explicitId || key,
      content,
      status: String(raw?.status || 'pending'),
      priority: String(raw?.priority || 'medium')
    }
  }
  return order.map((key) => byKey[key]).filter((item) => item.content.length > 0)
}

export function parseTimeOrZero(value: string): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  const raw = String(value || '').trim()
  if (!raw) return 0
  if (/^\d+$/.test(raw)) {
    const numeric = Number(raw)
    if (Number.isFinite(numeric)) return numeric
  }
  return Date.parse(raw) || 0
}

function tailText(text: string, max = 180): string {
  if (text.length <= max) return text
  return `...${text.slice(text.length - max)}`
}

function oneLinePreview(text: string, max = 84): string {
  const compact = String(text || '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!compact) return ''
  if (compact.length <= max) return compact
  return `${compact.slice(0, max)}...`
}

function stringifyUnknown(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function resolveToolRenderMode(input: {
  kind: ToolDisplayMeta['kind']
  hasDetails: boolean
  status: string
}): ToolDisplayMeta['renderMode'] {
  const kind = input.kind
  if (!input.hasDetails) return 'inline'
  if (kind === 'bash' && input.status !== 'error' && input.status !== 'failed') return 'inline'
  return 'collapsible'
}

function toDisplayFilename(pathWithRange: string): string {
  const value = String(pathWithRange || '').trim()
  if (!value) return ''
  const normalized = value.replace(/\\/g, '/')
  const lastSlash = normalized.lastIndexOf('/')
  const base = lastSlash >= 0 ? normalized.slice(lastSlash + 1) : normalized
  // Keep trailing :start or :start-end when present.
  const rangeMatch = normalized.match(/:(\d+)(-\d+)?$/)
  if (!rangeMatch) return base
  const rangeSuffix = normalized.slice(rangeMatch.index || normalized.length)
  const baseWithoutRange = base.replace(/:(\d+)(-\d+)?$/, '')
  return `${baseWithoutRange}${rangeSuffix}`
}

function inferLanguageHint(filePath: string): string {
  const lower = String(filePath || '').toLowerCase()
  if (!lower.includes('.')) return 'plaintext'
  if (lower.endsWith('.ts')) return 'typescript'
  if (lower.endsWith('.tsx')) return 'tsx'
  if (lower.endsWith('.js')) return 'javascript'
  if (lower.endsWith('.jsx')) return 'jsx'
  if (lower.endsWith('.vue')) return 'vue'
  if (lower.endsWith('.py')) return 'python'
  if (lower.endsWith('.rs')) return 'rust'
  if (lower.endsWith('.go')) return 'go'
  if (lower.endsWith('.java')) return 'java'
  if (lower.endsWith('.kt')) return 'kotlin'
  if (lower.endsWith('.swift')) return 'swift'
  if (lower.endsWith('.json')) return 'json'
  if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'yaml'
  if (lower.endsWith('.toml')) return 'toml'
  if (lower.endsWith('.md')) return 'markdown'
  if (lower.endsWith('.html')) return 'html'
  if (lower.endsWith('.css')) return 'css'
  if (lower.endsWith('.scss')) return 'scss'
  if (lower.endsWith('.sh')) return 'bash'
  return 'plaintext'
}

function extractReadContentBlock(output: string): string {
  const text = String(output || '')
  if (!text) return ''
  const matched = text.match(/<content>\s*([\s\S]*?)\s*<\/content>/i)
  if (matched && matched[1]) {
    return String(matched[1])
  }
  return text
}

function stripReadNoiseLines(content: string): string[] {
  const lines = String(content || '')
    .split('\n')
    .map((line) => line.replace(/\r$/, ''))
  const filtered: string[] = []
  let skipSystemReminder = false
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed === '<system-reminder>') {
      skipSystemReminder = true
      continue
    }
    if (trimmed === '</system-reminder>') {
      skipSystemReminder = false
      continue
    }
    if (skipSystemReminder) continue
    if (!trimmed) {
      filtered.push('')
      continue
    }
    if (/^\(End of file.*\)$/i.test(trimmed)) continue
    if (/^\(Showing lines .* of .*\)$/i.test(trimmed)) continue
    if (trimmed === '</content>' || trimmed === '<content>') continue
    filtered.push(line)
  }
  return filtered
}

function extractPathWithRange(input: Record<string, unknown>): string {
  const path = String(input.filePath || input.file_path || input.path || input.filename || '').trim()
  if (!path) return ''
  const startLine = Number(input.startLine || input.start_line || input.lineStart || input.line_start || 0)
  const endLine = Number(input.endLine || input.end_line || input.lineEnd || input.line_end || 0)
  if (Number.isFinite(startLine) && startLine > 0) {
    if (Number.isFinite(endLine) && endLine > startLine) {
      return `${path}:${startLine}-${endLine}`
    }
    return `${path}:${startLine}`
  }
  return path
}

function extractDiffStat(patch: string): string {
  let plus = 0
  let minus = 0
  for (const line of String(patch || '').split('\n')) {
    if (!line) continue
    if (line.startsWith('+++') || line.startsWith('---')) continue
    if (line.startsWith('+')) plus += 1
    if (line.startsWith('-')) minus += 1
  }
  if (plus === 0 && minus === 0) return ''
  return `+${plus} -${minus}`
}

function normalizePatchText(raw: string): string {
  return String(raw || '')
    .replace(/\r\n/g, '\n')
    .trim()
}

function parseToolRawArguments(rawArguments: string): Record<string, unknown> {
  const raw = String(rawArguments || '').trim()
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

export function summarizeToolPart(part: CodingAgentPart): ToolDisplayMeta {
  const toolName = String(part.tool || 'tool').trim() || 'tool'
  const lowerTool = toolName.toLowerCase()
  const state = (part.state || {}) as Record<string, unknown>
  const status = String(state.status || '').toLowerCase()
  const input = (state.input || parseToolRawArguments(String(state.rawArguments || state.raw || ''))) as Record<string, unknown>
  const outputText = String(state.output || '')
  const errorText = stringifyUnknown(state.error || '')
  const rawArgsText = String(state.rawArguments || state.raw || '').trim()
  const command = String(input.command || input.cmd || '').trim()
  const path = extractPathWithRange(input)
  const pattern = String(input.pattern || '').trim()
  const query = String(input.query || input.keyword || '').trim()
  const displayPath = toDisplayFilename(path)
  const argsSeed = displayPath || command || pattern || query || rawArgsText
  const argsText = oneLinePreview(argsSeed, 180)
  let kind: ToolDisplayMeta['kind'] = 'other'
  if (lowerTool === 'read') kind = 'read'
  else if (lowerTool === 'write' || lowerTool === 'edit' || lowerTool === 'apply_patch') kind = 'write'
  else if (lowerTool === 'search' || lowerTool === 'grep') kind = 'search'
  else if (lowerTool === 'bash' || lowerTool === 'run_terminal_cmd') kind = 'bash'

  let summary = ''
  let detailsText = ''
  let outputTail = ''
  let diffStat = ''
  let patchPreview = ''
  let codeLines: string[] = []
  let previewLineCount = kind === 'write' ? 4 : 6
  let languageHint = 'plaintext'

  const fullInputText = (() => {
    const normalizedInput = stringifyUnknown(input).trim()
    if (normalizedInput && normalizedInput !== '{}') return normalizedInput
    return rawArgsText
  })()
  const fullOutputText = outputText
  const fullErrorText = errorText
  const hasInput = Boolean(fullInputText.trim())
  const hasOutput = Boolean(fullOutputText.trim())
  const hasError = Boolean(fullErrorText.trim()) || status === 'error' || status === 'failed'

  if (kind === 'read') {
    const readPath = path || String(input.filepath || input.file_path || '').trim()
    const readDisplayPath = toDisplayFilename(readPath)
    const contentBlock = extractReadContentBlock(outputText)
    const cleanedLinesRaw = stripReadNoiseLines(contentBlock).map((line) => line.replace(/^\s*\d+:\s?/, ''))
    const cleanedLines = cleanedLinesRaw.some((line) => line.trim().length > 0) ? cleanedLinesRaw : []
    codeLines = cleanedLines
    detailsText = cleanedLines.join('\n').trim()
    summary = readDisplayPath ? `read ${readDisplayPath}` : 'read file'
    languageHint = inferLanguageHint(readPath)
  } else if (kind === 'write') {
    const writePath = path || String(input.filepath || input.file_path || '').trim()
    const writeDisplayPath = toDisplayFilename(writePath)
    const patchCandidate = normalizePatchText(
      String(state.patch || state.diff || state.outputPatch || (state.input as any)?.patch || '')
    )
    patchPreview = patchCandidate
    diffStat = extractDiffStat(patchCandidate)
    codeLines = patchCandidate
      ? patchCandidate.split('\n').map((line) => line.replace(/\r$/, ''))
      : []
    summary = writeDisplayPath ? `write ${writeDisplayPath}` : 'write file'
    if (diffStat) {
      summary = `${summary} ${diffStat}`.trim()
    }
    detailsText = patchPreview
    languageHint = inferLanguageHint(writePath)
  } else if (kind === 'search') {
    const subject = pattern || query || path || argsText
    summary = subject ? `${toolName} ${subject}` : toolName
    outputTail = tailText(outputText, 220)
    detailsText = outputText
  } else if (lowerTool === 'glob') {
    const globPattern = String(input.pattern || '').trim()
    const globPath = toDisplayFilename(String(input.path || '').trim()) || String(input.path || '').trim()
    summary = `glob 匹配文件: ${globPattern || '(empty-pattern)'}${globPath ? ` in ${globPath}` : ''}`
    detailsText = outputText
  } else if (kind === 'bash') {
    summary = command ? `bash ${command}` : toolName
    outputTail = tailText(outputText, 280)
    detailsText = outputText
  } else {
    summary = argsText ? `${toolName} ${argsText}` : toolName
    outputTail = tailText(outputText, 280)
    detailsText = outputText
  }

  if (hasError) {
    detailsText = fullErrorText || 'Tool call failed without error details.'
  } else if (!detailsText && fullOutputText) {
    detailsText = fullOutputText
  }

  if (detailsText && detailsText.trim() === summary.trim()) {
    detailsText = ''
  }

  const hasDetails = Boolean(detailsText || fullOutputText || fullErrorText || patchPreview || diffStat || codeLines.length)
  const renderMode = resolveToolRenderMode({ kind, hasDetails, status })
  const argsPreview = oneLinePreview(argsText, 92)
  const hiddenLineCount = Math.max(0, codeLines.length - previewLineCount)

  return {
    kind,
    renderMode,
    toolName,
    argsText,
    argsPreview,
    fullInputText,
    fullOutputText,
    fullErrorText,
    hasInput,
    hasOutput,
    hasError,
    hasDetails,
    title: summary || toolName,
    summary,
    detailBody: detailsText,
    detailsText,
    command,
    outputTail,
    diffStat,
    patchPreview,
    languageHint,
    codeLines,
    previewLineCount,
    hiddenLineCount
  }
}

export function summarizeStepPart(part: CodingAgentPart): string {
  const stepType = String(part.type || '').toLowerCase()
  const reason = String((part as any)?.reason || '').trim()
  const lowered = reason.toLowerCase()
  const noisy = new Set([
    '',
    'tool-calls',
    '开始执行步骤',
    '步骤执行完成',
    '步骤开始执行',
    '步骤完成',
    'start step',
    'step started',
    'step finished',
    'finish step'
  ])
  if (!noisy.has(lowered) && reason) {
    return reason
  }
  if (stepType === 'step-finish' && lowered.includes('终止')) {
    return reason
  }
  return ''
}

export function summarizeUnknownPart(part: CodingAgentPart): string {
  const type = String(part.type || 'unknown')
  const text = typeof (part as any)?.text === 'string' ? String((part as any).text) : ''
  if (text) {
    return `${type}: ${text.slice(0, 160)}`
  }
  return `系统消息: ${type}`
}

export function parseToolRawArgumentsSafe(rawArguments: string): Record<string, unknown> {
  return parseToolRawArguments(rawArguments)
}

