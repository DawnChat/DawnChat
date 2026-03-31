import type { ContextPushPayload } from './messageProtocol'

export interface ContextPushComposerToken {
  preview: string
  fullText: string
}

export function contextPayloadToComposerText(payload: ContextPushPayload): string {
  const parts: string[] = []
  const metadata = payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : {}
  const preview = String((metadata as Record<string, unknown>).preview || '').trim()
  if (preview) {
    parts.push(preview)
  }
  for (const item of payload.items || []) {
    if (item.type === 'text' && item.text) {
      parts.push(String(item.text))
      continue
    }
    if (item.type === 'image') {
      const uri = String(item.uri || '').trim()
      if (!uri) continue
      parts.push(`![image](${uri})`)
    }
  }
  return parts.filter(Boolean).join('\n')
}

export function contextPayloadToComposerToken(payload: ContextPushPayload): ContextPushComposerToken | null {
  const preview = String((payload.metadata as Record<string, unknown> | undefined)?.preview || '').trim()
  const fullText = contextPayloadToComposerText(payload).trim()
  if (!fullText) return null
  return {
    preview: preview || fullText.split('\n')[0] || 'context',
    fullText
  }
}