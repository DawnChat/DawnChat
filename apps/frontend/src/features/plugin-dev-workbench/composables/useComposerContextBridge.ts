import { ref, type Ref } from 'vue'
import { logger } from '@/utils/logger'
import type { InspectorSelectPayload } from '@/types/inspector'
import type { ContextPushPayload } from '@/services/plugin-ui-bridge/messageProtocol'
import { contextPayloadToComposerToken } from '@/services/plugin-ui-bridge/contextInbox'
import { encodeContextToken } from '@/services/plugin-ui-bridge/contextToken'

interface UseComposerContextBridgeOptions {
  chatInput: Ref<string>
}

export const useComposerContextBridge = (options: UseComposerContextBridgeOptions) => {
  const composerSelection = ref<{ start: number; end: number; focused: boolean }>({
    start: 0,
    end: 0,
    focused: false
  })

  const shortFileName = (raw: string) => {
    const normalized = String(raw || '').replace(/\\/g, '/').trim()
    if (!normalized) return 'unknown'
    const chunks = normalized.split('/').filter(Boolean)
    return chunks[chunks.length - 1] || normalized
  }

  const buildInspectorTag = (payload: InspectorSelectPayload) => {
    const file = shortFileName(payload.fileRelative || payload.file)
    const start = payload.range.start
    return `${file}(L${start.line}:C${start.column})`
  }

  const buildInspectorFullText = (payload: InspectorSelectPayload) => {
    const snippet = String(payload.textSnippet || payload.htmlSnippet || '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 160)
    if (!snippet) {
      return ''
    }
    return `${snippet}\n`
  }

  const insertTextAtSelection = (inserted: string) => {
    const base = options.chatInput.value
    const start = Math.max(0, Number(composerSelection.value.start || 0))
    const end = Math.max(start, Number(composerSelection.value.end || start))
    if (composerSelection.value.focused) {
      options.chatInput.value = `${base.slice(0, start)}${inserted}${base.slice(end)}`
      return
    }
    if (!base.trim()) {
      options.chatInput.value = inserted
      return
    }
    options.chatInput.value = `${base}${base.endsWith('\n') ? '' : '\n'}${inserted}`
  }

  const handleComposerSelectionChange = (payload: { start: number; end: number; focused: boolean }) => {
    composerSelection.value = {
      start: Number(payload.start || 0),
      end: Number(payload.end || 0),
      focused: Boolean(payload.focused)
    }
  }

  const handleInspectorSelect = (payload: InspectorSelectPayload) => {
    const preview = buildInspectorTag(payload)
    const fullText = buildInspectorFullText(payload)
    const rawToken = encodeContextToken(preview, fullText)
    insertTextAtSelection(rawToken)
    logger.info('plugin_inspector_selected', {
      pluginId: payload.pluginId,
      file: payload.file,
      line: payload.range.start.line
    })
  }

  const handleContextPush = (payload: ContextPushPayload) => {
    const token = contextPayloadToComposerToken(payload)
    if (!token) return
    const rawToken = encodeContextToken(token.preview, token.fullText)
    insertTextAtSelection(rawToken)
  }

  return {
    handleComposerSelectionChange,
    handleInspectorSelect,
    handleContextPush,
  }
}
