import type { ChatRenderRow, PermissionCard, QuestionCard, SessionTodoItem, TimelineItem } from '@/features/coding-agent/store/types'
import { parseTimeOrZero } from '@/features/coding-agent/store/toolDisplay'

export function buildTimelineItems(input: {
  rows: ChatRenderRow[]
  questions: QuestionCard[]
  permissions: PermissionCard[]
  todos: SessionTodoItem[]
  activeSessionId: string
}): {
  items: TimelineItem[]
  permissionDebug: {
    signature: string
    payload: {
      sessionID: string
      totalPermissions: number
      permissions: Array<{ id: string; messageID: string; callID: string; tool: string; status: string }>
    }
  } | null
} {
  const { rows, questions, permissions, todos, activeSessionId } = input
  const ordered: Array<{ order: number; item: TimelineItem }> = []
  const messageOrder: Record<string, number> = {}
  let seq = 0

  for (const row of rows) {
    const createdAt = parseTimeOrZero(row.info.time?.created || '')
    const base = createdAt * 1000 + seq
    messageOrder[String(row.info.id || '')] = base
    for (const item of row.items) {
      seq += 1
      ordered.push({
        order: base + seq / 1000,
        item: {
          id: `${item.messageID}_${item.id}`,
          kind: 'part',
          role: String(row.info.role || ''),
          item
        }
      })
    }
  }

  for (let i = 0; i < questions.length; i += 1) {
    const question = questions[i]
    const base = messageOrder[question.messageID] || Number.MAX_SAFE_INTEGER / 4
    ordered.push({
      order: base + 0.3 + i / 10000,
      item: {
        id: question.id,
        kind: 'question',
        question
      }
    })
  }

  for (let i = 0; i < permissions.length; i += 1) {
    const permission = permissions[i]
    const base = messageOrder[permission.messageID] || Number.MAX_SAFE_INTEGER / 3
    ordered.push({
      order: base + 0.35 + i / 10000,
      item: {
        id: permission.id,
        kind: 'permission',
        permission
      }
    })
  }

  if (todos.length > 0) {
    ordered.push({
      order: Number.MAX_SAFE_INTEGER / 2,
      item: {
        id: `todo_${activeSessionId || 'session'}`,
        kind: 'todo',
        todos
      }
    })
  }

  const items = ordered.sort((a, b) => a.order - b.order).map((entry) => entry.item)
  if (permissions.length === 0) {
    return { items, permissionDebug: null }
  }

  const payload = {
    sessionID: String(activeSessionId || ''),
    totalPermissions: permissions.length,
    permissions: permissions.map((item) => ({
      id: item.id,
      messageID: item.messageID,
      callID: item.callID,
      tool: item.tool,
      status: item.status
    }))
  }
  return {
    items,
    permissionDebug: {
      signature: JSON.stringify(payload),
      payload
    }
  }
}

