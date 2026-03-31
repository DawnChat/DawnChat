import type { BuildHubFilter, BuildHubRecentSession } from '@/stores/plugin/types'
import type { PluginStoreState } from '@/stores/plugin/state'

const BUILD_HUB_RECENT_SESSION_KEY = 'dawnchat.apps.buildhub.recent-dev.v1'

const normalizeBuildHubFilter = (raw: string): BuildHubFilter => {
  if (raw === 'recent' || raw === 'installed' || raw === 'market') {
    return raw
  }
  return 'all'
}

const canUseLocalStorage = (): boolean => {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

const readRecentSession = (): BuildHubRecentSession | null => {
  if (!canUseLocalStorage()) return null
  try {
    const raw = window.localStorage.getItem(BUILD_HUB_RECENT_SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<BuildHubRecentSession>
    const pluginId = String(parsed.pluginId || '').trim()
    const visitedAt = Number(parsed.visitedAt || 0)
    if (!pluginId || !visitedAt) return null
    return { pluginId, visitedAt }
  } catch {
    return null
  }
}

const writeRecentSession = (next: BuildHubRecentSession) => {
  if (!canUseLocalStorage()) return
  window.localStorage.setItem(BUILD_HUB_RECENT_SESSION_KEY, JSON.stringify(next))
}

export function createBuildHubActions(state: PluginStoreState) {
  const setBuildHubFilter = (filter: string) => {
    state.buildHubFilter.value = normalizeBuildHubFilter(String(filter || ''))
  }

  const setBuildHubPromptDraft = (value: string) => {
    state.buildHubPromptDraft.value = String(value || '')
  }

  const hydrateBuildHubRecentSession = () => {
    const session = readRecentSession()
    state.buildHubRecentPluginId.value = String(session?.pluginId || '')
    state.buildHubRecentVisitedAt.value = Number(session?.visitedAt || 0)
  }

  const rememberBuildHubRecentSession = (pluginId: string) => {
    const normalizedPluginId = String(pluginId || '').trim()
    if (!normalizedPluginId) return
    const visitedAt = Date.now()
    state.buildHubRecentPluginId.value = normalizedPluginId
    state.buildHubRecentVisitedAt.value = visitedAt
    writeRecentSession({ pluginId: normalizedPluginId, visitedAt })
  }

  return {
    setBuildHubFilter,
    setBuildHubPromptDraft,
    hydrateBuildHubRecentSession,
    rememberBuildHubRecentSession,
  }
}
