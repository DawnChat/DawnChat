import type { Ref } from 'vue'
import type { SessionMeta, SessionState } from '@/features/coding-agent/store/types'
import { createEmptySessionState } from '@/features/coding-agent/store/sessionHelpers'
import { parseTimeOrZero } from '@/features/coding-agent/store/toolDisplay'

export function createSessionStateRepository(input: {
  activeSessionPrefix: string
  boundWorkspaceId: Ref<string>
  activeSessionId: Ref<string>
  sessions: Ref<SessionMeta[]>
  sessionStateById: Ref<Record<string, SessionState>>
  pendingLocalUserMessageIdsBySession: Ref<Record<string, string[]>>
}) {
  const {
    activeSessionPrefix,
    boundWorkspaceId,
    activeSessionId,
    sessions,
    sessionStateById,
    pendingLocalUserMessageIdsBySession
  } = input

  function activeSessionStorageKey(workspaceId: string): string {
    return `${activeSessionPrefix}${workspaceId}`
  }

  function setActiveSession(id: string) {
    activeSessionId.value = id
    const workspaceId = boundWorkspaceId.value
    if (workspaceId && id) {
      localStorage.setItem(activeSessionStorageKey(workspaceId), id)
    }
  }

  function getOrCreateSessionState(sessionID: string): SessionState {
    const id = String(sessionID || '').trim()
    if (!id) {
      return createEmptySessionState()
    }
    if (!sessionStateById.value[id]) {
      sessionStateById.value[id] = createEmptySessionState()
    }
    return sessionStateById.value[id]
  }

  function sortSessions() {
    sessions.value = [...sessions.value].sort((a, b) => {
      const tb = parseTimeOrZero(b.updatedAt || b.createdAt)
      const ta = parseTimeOrZero(a.updatedAt || a.createdAt)
      return tb - ta
    })
  }

  function upsertSessionMeta(meta: SessionMeta) {
    if (!meta.id) return
    const existingIdx = sessions.value.findIndex((item) => item.id === meta.id)
    if (existingIdx >= 0) {
      sessions.value[existingIdx] = {
        ...sessions.value[existingIdx],
        ...meta
      }
    } else {
      sessions.value.push(meta)
    }
    sortSessions()
  }

  function updateSessionTouch(sessionID: string) {
    const id = String(sessionID || '').trim()
    if (!id) return
    const item = sessions.value.find((row) => row.id === id)
    if (!item) return
    item.updatedAt = new Date().toISOString()
    sortSessions()
  }

  function clearSessionState(sessionID: string) {
    const id = String(sessionID || '').trim()
    if (!id) return
    sessionStateById.value[id] = createEmptySessionState()
    delete pendingLocalUserMessageIdsBySession.value[id]
  }

  function findPermissionSessionID(permissionID: string): string {
    const id = String(permissionID || '').trim()
    if (!id) return ''
    for (const [sessionID, state] of Object.entries(sessionStateById.value)) {
      if (state.permissionCardsById[id]) {
        return sessionID
      }
    }
    return ''
  }

  return {
    activeSessionStorageKey,
    setActiveSession,
    getOrCreateSessionState,
    sortSessions,
    upsertSessionMeta,
    updateSessionTouch,
    clearSessionState,
    findPermissionSessionID
  }
}

