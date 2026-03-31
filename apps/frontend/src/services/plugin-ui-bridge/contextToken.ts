const TOKEN_PREFIX = '[[dc_ctx:'
const TOKEN_SUFFIX = ']]'
const TOKEN_RE = /\[\[dc_ctx:([A-Za-z0-9+/=_-]+):([A-Za-z0-9+/=_-]+)\]\]/g

export interface ContextTokenData {
  raw: string
  preview: string
  fullText: string
}

function encodeBase64(input: string): string {
  return btoa(unescape(encodeURIComponent(input)))
}

function decodeBase64(input: string): string {
  try {
    return decodeURIComponent(escape(atob(input)))
  } catch {
    return ''
  }
}

export function encodeContextToken(preview: string, fullText: string): string {
  const normalizedPreview = String(preview || '').trim()
  const normalizedFullText = String(fullText || '').trim()
  return `${TOKEN_PREFIX}${encodeBase64(normalizedPreview)}:${encodeBase64(normalizedFullText)}${TOKEN_SUFFIX}`
}

export function parseContextTokens(input: string): Array<{ type: 'text'; text: string } | { type: 'token'; data: ContextTokenData }> {
  const text = String(input || '')
  const segments: Array<{ type: 'text'; text: string } | { type: 'token'; data: ContextTokenData }> = []
  let lastIndex = 0
  let match: RegExpExecArray | null
  TOKEN_RE.lastIndex = 0
  while ((match = TOKEN_RE.exec(text))) {
    const [raw, previewB64, fullB64] = match
    const start = match.index
    if (start > lastIndex) {
      segments.push({ type: 'text', text: text.slice(lastIndex, start) })
    }
    segments.push({
      type: 'token',
      data: {
        raw,
        preview: decodeBase64(previewB64),
        fullText: decodeBase64(fullB64)
      }
    })
    lastIndex = start + raw.length
  }
  if (lastIndex < text.length) {
    segments.push({ type: 'text', text: text.slice(lastIndex) })
  }
  if (segments.length === 0) {
    segments.push({ type: 'text', text: '' })
  }
  return segments
}

export function expandContextTokens(input: string): string {
  return String(input || '').replace(TOKEN_RE, (_raw, previewB64, fullB64) => {
    const preview = decodeBase64(String(previewB64 || ''))
    const fullText = decodeBase64(String(fullB64 || ''))
    const parts = [preview, fullText].map((part) => String(part || '').trim()).filter(Boolean)
    return parts.join('\n')
  })
}

export function hasContextToken(input: string): boolean {
  return TOKEN_RE.test(String(input || ''))
}
