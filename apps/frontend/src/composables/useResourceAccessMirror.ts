import { buildBackendUrl } from '../utils/backendUrl'
import { logger } from '../utils/logger'

export type MirrorProvider = 'huggingface' | 'github' | 'playwright' | 'pypi'
type AccessMode = 'auto' | 'direct_only' | 'mirror_only' | 'prefer_direct' | 'prefer_mirror'

interface ProviderPolicy {
  mode?: AccessMode
  mirror_url?: string
  direct_url?: string
  mirror_prefix?: string
  mirror_host?: string
  direct_host?: string
}

interface ResourceAccessSettings {
  global_mode: AccessMode
  providers: Record<string, ProviderPolicy>
  auto_probe: {
    enabled: boolean
    timeout_ms: number
  }
}

function modePrefersMirror(mode?: AccessMode): boolean | null {
  if (mode === 'mirror_only' || mode === 'prefer_mirror') return true
  if (mode === 'direct_only' || mode === 'prefer_direct') return false
  return null
}

export async function getProviderMirrorEnabled(provider: MirrorProvider): Promise<boolean> {
  try {
    const res = await fetch(buildBackendUrl('/api/network/resource-access'))
    if (!res.ok) return false
    const settings = (await res.json()) as ResourceAccessSettings
    const providerMode = settings.providers?.[provider]?.mode
    const byProvider = modePrefersMirror(providerMode)
    if (byProvider !== null) return byProvider
    const byGlobal = modePrefersMirror(settings.global_mode)
    return byGlobal ?? false
  } catch (error) {
    logger.error('Failed to get provider mirror setting', { provider, error })
    return false
  }
}

export async function setProviderMirrorEnabled(provider: MirrorProvider, enabled: boolean): Promise<void> {
  try {
    const res = await fetch(buildBackendUrl('/api/network/resource-access'))
    if (!res.ok) throw new Error(`fetch_failed_${res.status}`)
    const settings = (await res.json()) as ResourceAccessSettings

    const next: ResourceAccessSettings = {
      ...settings,
      providers: {
        ...(settings.providers || {})
      },
      auto_probe: {
        ...(settings.auto_probe || { enabled: true, timeout_ms: 2500 })
      }
    }

    next.providers[provider] = {
      ...(next.providers[provider] || {}),
      mode: enabled ? 'prefer_mirror' : 'prefer_direct'
    }

    const saveRes = await fetch(buildBackendUrl('/api/network/resource-access'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(next)
    })
    if (!saveRes.ok) throw new Error(`save_failed_${saveRes.status}`)
  } catch (error) {
    logger.error('Failed to save provider mirror setting', { provider, enabled, error })
  }
}

