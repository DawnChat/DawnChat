import { computed, ref } from 'vue'
import {
  buildDesktopAuthBridgeUrl,
  DESKTOP_AUTH_DEFAULT_BRIDGE_BASE_URL,
  DESKTOP_AUTH_PENDING_KEY,
  DESKTOP_AUTH_PROTOCOL_VERSION,
  DESKTOP_AUTH_REDIRECT_URI,
  generateDesktopAuthState,
  normalizeDesktopAuthRedirectUri,
  normalizeNextPath,
  normalizeProvider,
  parseDesktopAuthCallback,
  type DesktopAuthPendingState,
  type OAuthProvider
} from '@dawnchat/auth-bridge'
import { generatePersistentDeviceId, saveSupabaseSession } from '@/shared/composables/useSecureStorage'
import { supabase } from '@/shared/composables/supabaseClient'
import { logger } from '@/utils/logger'
import { APPS_HUB_PATH } from '@/app/router/paths'
import { isSafeRedirectPath } from '@/shared/auth/redirect'

const requireEnv = (key: string): string => {
  const value = String(import.meta.env[key] || '').trim()
  if (!value) {
    throw new Error(`Missing required env: ${key}`)
  }
  return value
}

const SUPABASE_URL = requireEnv('VITE_SUPABASE_URL')
const SUPABASE_ANON_KEY = requireEnv('VITE_SUPABASE_ANON_KEY')
const PENDING_TTL_MS = 10 * 60 * 1000
const DEFAULT_AUTH_ROUTE = APPS_HUB_PATH

const resolveDesktopAuthRedirectUri = (): string => {
  const envRedirectUri = normalizeDesktopAuthRedirectUri(import.meta.env.VITE_DESKTOP_AUTH_REDIRECT_URI, '')
  if (envRedirectUri) {
    return envRedirectUri
  }
  if ((window as any).__TAURI_INTERNALS__) {
    return DESKTOP_AUTH_REDIRECT_URI
  }
  return `${window.location.origin}/auth/callback`
}

interface DesktopAuthPendingStateWithNext extends DesktopAuthPendingState {
  nextPath?: string
}

const readPendingState = (): DesktopAuthPendingStateWithNext | null => {
  try {
    const raw = localStorage.getItem(DESKTOP_AUTH_PENDING_KEY)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as DesktopAuthPendingStateWithNext
    if (!parsed?.state || !parsed?.deviceId || !parsed?.createdAt) {
      clearPendingState()
      return null
    }
    if (Date.now() - parsed.createdAt > PENDING_TTL_MS) {
      clearPendingState()
      return null
    }
    return parsed
  } catch {
    clearPendingState()
    return null
  }
}

const writePendingState = (pending: DesktopAuthPendingStateWithNext): void => {
  localStorage.setItem(DESKTOP_AUTH_PENDING_KEY, JSON.stringify(pending))
}

const clearPendingState = (): void => {
  localStorage.removeItem(DESKTOP_AUTH_PENDING_KEY)
}

const maskSensitiveParams = (value: string): string => {
  try {
    const parsed = new URL(value)
    const sensitiveKeys = ['access_token', 'refresh_token', 'provider_token', 'code', 'ticket', 'state']
    for (const key of sensitiveKeys) {
      if (parsed.searchParams.has(key)) {
        parsed.searchParams.set(key, '***')
      }
    }
    return parsed.toString()
  } catch {
    return value
  }
}

const isLoading = ref(false)
const error = ref<string | null>(null)

export function useDesktopWebAuth() {

  const bridgeBaseUrl = computed(() => {
    return (import.meta.env.VITE_DESKTOP_AUTH_BRIDGE_BASE_URL || DESKTOP_AUTH_DEFAULT_BRIDGE_BASE_URL).trim()
  })

  const startBridgeLogin = async (provider: OAuthProvider | undefined, nextPath: string): Promise<{ success: boolean; url?: string; error?: string }> => {
    isLoading.value = true
    error.value = null
    try {
      const state = generateDesktopAuthState()
      const deviceId = await generatePersistentDeviceId()
      const normalizedNextPath = normalizeNextPath(nextPath)
      const url = buildDesktopAuthBridgeUrl(bridgeBaseUrl.value, {
        state,
        device_id: deviceId,
        redirect_uri: resolveDesktopAuthRedirectUri(),
        next: normalizedNextPath,
        provider: normalizeProvider(provider)
      })
      logger.info('[desktop-web-auth] bridge login prepared', {
        origin: window.location.origin,
        bridgeBaseUrl: bridgeBaseUrl.value,
        provider: provider || 'default',
        nextPath: normalizedNextPath,
        redirectUri: resolveDesktopAuthRedirectUri(),
        statePrefix: state.slice(0, 10),
        deviceIdPrefix: deviceId.slice(0, 16),
        finalBridgeUrl: maskSensitiveParams(url)
      })

      writePendingState({
        state,
        deviceId,
        createdAt: Date.now(),
        nextPath: normalizedNextPath
      })

      if ((window as any).__TAURI_INTERNALS__) {
        const { openUrl } = await import('@tauri-apps/plugin-opener')
        await openUrl(url)
      } else {
        window.open(url, '_blank')
      }

      return { success: true, url }
    } catch (err: any) {
      const message = err?.message || '无法打开 Web 登录页面'
      error.value = message
      logger.error('[desktop-web-auth] startBridgeLogin failed', err)
      return { success: false, error: message }
    } finally {
      isLoading.value = false
    }
  }

  const exchangeDesktopTicket = async (
    callbackUrl: string
  ): Promise<{ session: any; nextPath: string }> => {
    isLoading.value = true
    error.value = null
    try {
      logger.info('[desktop-web-auth] exchange ticket start', {
        callbackUrl: maskSensitiveParams(callbackUrl),
        origin: window.location.origin
      })
      const parsed = parseDesktopAuthCallback(callbackUrl)
      if (parsed.error) {
        throw new Error(parsed.error)
      }
      if (!parsed.ticket || !parsed.state) {
        throw new Error('登录回调缺少 ticket 或 state')
      }

      const pending = readPendingState()
      if (!pending) {
        throw new Error('登录状态已失效，请重新发起登录')
      }
      if (pending.state !== parsed.state) {
        clearPendingState()
        throw new Error('登录状态校验失败，请重新登录')
      }

      const exchangeUrl = `${SUPABASE_URL}/functions/v1/exchange-desktop-ticket`
      const response = await fetch(exchangeUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          apikey: SUPABASE_ANON_KEY
        },
        body: JSON.stringify({
          desktop_ticket: parsed.ticket,
          state: parsed.state,
          device_id: pending.deviceId,
          protocol_version: DESKTOP_AUTH_PROTOCOL_VERSION
        })
      })

      if (!response.ok) {
        const text = await response.text()
        let message = text
        try {
          const parsedError = JSON.parse(text)
          message = parsedError?.message || parsedError?.code || text
        } catch {
        }
        logger.error('[desktop-web-auth] exchange ticket failed', {
          status: response.status,
          body: text
        })
        throw new Error(message || `ticket 兑换失败(${response.status})`)
      }

      const payload = await response.json()
      const accessToken = String(payload?.access_token || '').trim()
      const refreshToken = String(payload?.refresh_token || '').trim()
      if (!accessToken || !refreshToken) {
        throw new Error('ticket 兑换结果缺少会话 token')
      }
      const nextPathRaw = String(payload?.next_path || pending.nextPath || DEFAULT_AUTH_ROUTE).trim()
      const nextPath = isSafeRedirectPath(nextPathRaw) ? nextPathRaw : DEFAULT_AUTH_ROUTE

      const { data, error: setSessionError } = await supabase.auth.setSession({
        access_token: accessToken,
        refresh_token: refreshToken
      })
      if (setSessionError || !data.session) {
        logger.error('[desktop-web-auth] setSession failed', { message: setSessionError?.message })
        throw setSessionError || new Error('会话注入失败')
      }

      await saveSupabaseSession({
        access_token: data.session.access_token,
        refresh_token: data.session.refresh_token,
        expires_at: data.session.expires_at,
        token_type: data.session.token_type,
        user: data.session.user
      })
      logger.info('[desktop-web-auth] exchange ticket success', {
        userId: data.session.user.id,
        nextPath
      })
      clearPendingState()
      return {
        session: data.session,
        nextPath
      }
    } catch (err: any) {
      error.value = err?.message || '登录处理失败，请重试'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  return {
    isLoading,
    error,
    startBridgeLogin,
    exchangeDesktopTicket
  }
}
