import type { MarketPlugin } from '@/stores/plugin/types'
import { API_BASE } from '@/stores/plugin/api/client'
import { logger } from '@/utils/logger'
import type { PluginStoreContext } from '@/stores/plugin/context'

export function parseSemver(version: string): [number, number, number] {
  const normalized = String(version || '').trim().replace(/^v/i, '')
  const [major = '0', minor = '0', patch = '0'] = normalized.split('.')
  const parsePart = (value: string) => {
    const match = value.match(/^\d+/)
    return Number(match?.[0] || '0')
  }
  return [parsePart(major), parsePart(minor), parsePart(patch)]
}

export function isVersionGreater(a: string, b: string): boolean {
  const [a1, a2, a3] = parseSemver(a)
  const [b1, b2, b3] = parseSemver(b)
  if (a1 !== b1) return a1 > b1
  if (a2 !== b2) return a2 > b2
  return a3 > b3
}

export function deriveMarketAction(app: Pick<MarketPlugin, 'installed' | 'installed_version' | 'version' | 'state'>): MarketPlugin['action'] {
  if (!app.installed) {
    return 'install'
  }
  if (app.version && app.installed_version && isVersionGreater(app.version, app.installed_version)) {
    return 'update'
  }
  if (app.state === 'running') {
    return 'open'
  }
  return 'installed'
}

export function normalizeMarketApp(app: MarketPlugin): MarketPlugin {
  return {
    ...app,
    action: deriveMarketAction(app),
  }
}

export function createMarketActions(ctx: PluginStoreContext) {
  const patchMarketApp = (appId: string, patch: Partial<MarketPlugin>) => {
    const index = ctx.state.marketApps.value.findIndex((item) => item.id === appId)
    if (index >= 0) {
      const merged = {
        ...ctx.state.marketApps.value[index],
        ...patch,
      }
      ctx.state.marketApps.value[index] = normalizeMarketApp(merged)
    }
  }

  const setMarketQuery = (value: string) => {
    ctx.state.marketQuery.value = value
  }

  const loadMarketApps = async (forceRefresh = false) => {
    ctx.state.marketLoading.value = true
    ctx.state.marketError.value = null
    try {
      const url = `${API_BASE()}/api/plugins/market${forceRefresh ? '?force_refresh=true' : ''}`
      const res = await fetch(url)
      if (!res.ok) {
        throw new Error(`market_fetch_failed_${res.status}`)
      }
      const data = await res.json()
      if (data.status === 'success') {
        ctx.state.marketApps.value = (data.plugins as MarketPlugin[]).map(normalizeMarketApp)
        return
      }
      throw new Error('market_response_invalid')
    } catch (err: unknown) {
      logger.error('Failed to load market apps:', err)
      const message = err instanceof Error ? err.message : 'Failed to load market apps'
      ctx.state.marketError.value = message
      ctx.state.error.value = message
    } finally {
      ctx.state.marketLoading.value = false
    }
  }

  return {
    patchMarketApp,
    setMarketQuery,
    loadMarketApps,
  }
}
