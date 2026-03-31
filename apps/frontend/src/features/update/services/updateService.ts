import { isTauri } from '@/adapters/env'

const UPDATE_JSON_URL = 'https://plugins.dawnchat.com/update.json'

interface PlatformUpdateConfig {
  latest_version?: string
  min_supported_version?: string
  download_url?: string
  release_notes?: string
}

interface StableChannelConfig {
  latest_version?: string
  min_supported_version?: string
  release_notes?: string
  downloads?: {
    fallback?: string
  }
  platforms?: Record<string, PlatformUpdateConfig>
}

interface UpdateJson {
  schema_version?: string
  published_at?: string
  channels?: {
    stable?: StableChannelConfig
  }
}

export type UpdateCheckMode = 'none' | 'recommended' | 'forced'

export interface UpdateCheckResult {
  mode: UpdateCheckMode
  currentVersion: string
  latestVersion: string | null
  minSupportedVersion: string | null
  downloadUrl: string | null
  releaseNotes: string
  platformKey: string
}

export function compareSemver(left: string, right: string): number {
  const normalize = (value: string): number[] => {
    const cleaned = String(value || '').trim().replace(/^v/i, '').split('-')[0]
    const [major = '0', minor = '0', patch = '0'] = cleaned.split('.')
    const parsePart = (part: string) => {
      const matched = part.match(/^\d+/)
      return Number(matched?.[0] || '0')
    }
    return [parsePart(major), parsePart(minor), parsePart(patch)]
  }

  const [a1, a2, a3] = normalize(left)
  const [b1, b2, b3] = normalize(right)
  if (a1 !== b1) return a1 > b1 ? 1 : -1
  if (a2 !== b2) return a2 > b2 ? 1 : -1
  if (a3 !== b3) return a3 > b3 ? 1 : -1
  return 0
}

export const resolvePlatformKey = (): string => {
  const ua = String(navigator.userAgent || '').toLowerCase()
  if (ua.includes('windows')) {
    return 'windows-x64'
  }
  return 'darwin-aarch64'
}

const toNonEmptyString = (value: unknown): string | null => {
  const normalized = String(value || '').trim()
  return normalized ? normalized : null
}

export async function getCurrentAppVersion(): Promise<string> {
  if (!isTauri()) {
    return '0.0.0'
  }
  const { getVersion } = await import('@tauri-apps/api/app')
  return await getVersion()
}

export async function checkForAppUpdate(
  fetcher: typeof fetch = fetch
): Promise<UpdateCheckResult> {
  const currentVersion = await getCurrentAppVersion()
  const platformKey = resolvePlatformKey()
  const response = await fetcher(UPDATE_JSON_URL, { method: 'GET' })
  if (!response.ok) {
    throw new Error(`update_json_fetch_failed_${response.status}`)
  }

  const payload = (await response.json()) as UpdateJson
  const stable = payload.channels?.stable
  if (!stable) {
    throw new Error('update_json_stable_channel_missing')
  }

  const platform = stable.platforms?.[platformKey]
  const latestVersion = toNonEmptyString(platform?.latest_version || stable.latest_version)
  const minSupportedVersion = toNonEmptyString(platform?.min_supported_version || stable.min_supported_version || latestVersion)
  const downloadUrl = toNonEmptyString(platform?.download_url || stable.downloads?.fallback)
  const releaseNotes = String(platform?.release_notes || stable.release_notes || '').trim()

  if (!latestVersion || !minSupportedVersion || !downloadUrl) {
    throw new Error('update_json_required_fields_missing')
  }

  if (compareSemver(currentVersion, minSupportedVersion) < 0) {
    return {
      mode: 'forced',
      currentVersion,
      latestVersion,
      minSupportedVersion,
      downloadUrl,
      releaseNotes,
      platformKey
    }
  }

  if (compareSemver(currentVersion, latestVersion) < 0) {
    return {
      mode: 'recommended',
      currentVersion,
      latestVersion,
      minSupportedVersion,
      downloadUrl,
      releaseNotes,
      platformKey
    }
  }

  return {
    mode: 'none',
    currentVersion,
    latestVersion,
    minSupportedVersion,
    downloadUrl,
    releaseNotes,
    platformKey
  }
}
