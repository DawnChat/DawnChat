import { computed, type Ref } from 'vue'
import type { CodingAgentMessage } from '@/services/coding-agent/engineAdapter'
import type { ChatRenderItem, ChatRenderRow, SessionState } from '@/features/coding-agent/store/types'
import { resolvePartOrder } from '@/features/coding-agent/store/messageRepository'
import { parseTimeOrZero, summarizeStepPart, summarizeToolPart, summarizeUnknownPart } from '@/features/coding-agent/store/toolDisplay'

export function createChatProjectionService(input: {
  activeSessionId: Ref<string>
  sessionStateById: Ref<Record<string, SessionState>>
  selectedAgent: Ref<string>
}) {
  const { activeSessionId, sessionStateById, selectedAgent } = input

  const activeSessionState = computed<SessionState | null>(() => {
    const id = activeSessionId.value
    if (!id) return null
    return sessionStateById.value[id] || null
  })

  const orderedMessages = computed<CodingAgentMessage[]>(() => {
    const state = activeSessionState.value
    if (!state) return []
    const rows = Object.values(state.messagesById)
      .sort((a, b) => {
        const ta = parseTimeOrZero(a.time?.created || '')
        const tb = parseTimeOrZero(b.time?.created || '')
        return ta - tb
      })
      .map((info) => {
        const partsMap = state.partsByMessageId[info.id] || {}
        const orderMap = state.partOrderByMessageId[info.id] || {}
        const parts = Object.values(partsMap).sort((a, b) => {
          const orderA = resolvePartOrder(a, orderMap)
          const orderB = resolvePartOrder(b, orderMap)
          return orderA - orderB
        })
        return { info, parts }
      })
    return rows
  })

  const chatRows = computed<ChatRenderRow[]>(() => {
    return orderedMessages.value.map(({ info, parts }) => {
      const isMessageStreaming = !info.time?.completed
      const messageID = String(info.id || '')
      const items: ChatRenderItem[] = []
      for (const part of parts) {
        const partType = String(part.type || 'unknown')
        const status = String(part.state?.status || '')
        const partID = String(part.id || '')
        const isPartStreaming =
          isMessageStreaming ||
          status === 'pending' ||
          status === 'running' ||
          (partType === 'reasoning' && !(part as any)?.time?.end)
        if (partType === 'text') {
          items.push({
            id: partID,
            type: 'text',
            text: String(part.text || ''),
            messageID,
            callID: String((part as any)?.callID || (part as any)?.callId || ''),
            raw: part,
            isStreaming: isPartStreaming
          })
          continue
        }
        if (partType === 'reasoning') {
          items.push({
            id: partID,
            type: 'reasoning',
            text: String(part.text || ''),
            messageID,
            callID: String((part as any)?.callID || (part as any)?.callId || ''),
            raw: part,
            isStreaming: isPartStreaming
          })
          continue
        }
        if (partType === 'file') {
          const mime = String((part as any)?.mime || (part as any)?.mediaType || '').toLowerCase()
          const filename = String((part as any)?.filename || '').trim()
          const label = mime.startsWith('image/') ? '图片附件' : '文件附件'
          items.push({
            id: partID,
            type: 'text',
            text: filename ? `[${label}] ${filename}` : `[${label}]`,
            messageID,
            callID: String((part as any)?.callID || (part as any)?.callId || ''),
            raw: part,
            isStreaming: false
          })
          continue
        }
        if (partType === 'tool') {
          const toolDisplay = summarizeToolPart(part)
          items.push({
            id: partID,
            type: 'tool',
            tool: String(part.tool || 'tool'),
            status: status || 'pending',
            text: toolDisplay.summary,
            toolDisplay,
            messageID,
            callID: String((part as any)?.callID || (part as any)?.callId || ''),
            raw: part,
            isStreaming: isPartStreaming
          })
          continue
        }
        if (partType === 'step-start' || partType === 'step-finish') {
          const text = summarizeStepPart(part)
          if (!text) continue
          items.push({
            id: partID,
            type: 'step',
            status: partType === 'step-start' ? 'running' : 'completed',
            reason: String((part as any)?.reason || ''),
            text,
            messageID,
            callID: String((part as any)?.callID || (part as any)?.callId || ''),
            raw: part,
            isStreaming: partType === 'step-start'
          })
          continue
        }
        items.push({
          id: partID,
          type: 'unknown',
          text: summarizeUnknownPart(part),
          messageID,
          callID: String((part as any)?.callID || (part as any)?.callId || ''),
          raw: part,
          isStreaming: isPartStreaming
        })
      }
      return { info, items }
    })
  })

  const activeReasoningItemId = computed<string>(() => {
    const rows = chatRows.value
    for (let i = rows.length - 1; i >= 0; i -= 1) {
      const row = rows[i]
      for (let j = row.items.length - 1; j >= 0; j -= 1) {
        const item = row.items[j]
        if (item.type === 'reasoning' && item.isStreaming) {
          return item.id
        }
      }
    }
    return ''
  })

  const canSwitchPlanToBuild = computed<boolean>(() => {
    if (String(selectedAgent.value || '').toLowerCase() !== 'plan') return false
    const planAssistants = orderedMessages.value
      .filter((row) => {
        if (String(row.info.role || '').toLowerCase() !== 'assistant') return false
        const mode = String((row.info as any).mode || '').toLowerCase()
        const agent = String((row.info as any).agent || '').toLowerCase()
        return mode === 'plan' || agent === 'plan'
      })
      .filter((row) => Boolean(row.info.time?.completed))
    if (planAssistants.length === 0) return false

    const latest = planAssistants[planAssistants.length - 1]
    const latestFinish = String((latest.info as any).finish || '').toLowerCase()
    if (latestFinish === 'tool-calls') return true

    const hasPriorToolCalls = planAssistants.some((row) => {
      const finish = String((row.info as any).finish || '').toLowerCase()
      if (finish === 'tool-calls') return true
      const hasToolPart = row.parts.some((part) => String(part.type || '') === 'tool')
      const hasStepFinishToolCalls = row.parts.some((part) => {
        return (
          String(part.type || '') === 'step-finish' && String((part as any).reason || '').toLowerCase() === 'tool-calls'
        )
      })
      return hasToolPart || hasStepFinishToolCalls
    })

    if (latestFinish === 'stop' || latestFinish === '') {
      return hasPriorToolCalls
    }
    return false
  })

  return {
    activeSessionState,
    orderedMessages,
    chatRows,
    activeReasoningItemId,
    canSwitchPlanToBuild
  }
}

