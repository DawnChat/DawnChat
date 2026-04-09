/**
 * 认证状态管理 Composable - 纯前端实现
 */
import { ref, computed } from 'vue'
import type { AuthChangeEvent, Session as SupabaseSession } from '@supabase/supabase-js'
import { logger } from '@/utils/logger'
import { useSupabase } from '@/shared/composables/supabaseClient'
import { useI18n } from '@/composables/useI18n'
import { useDesktopWebAuth } from '@/auth-bridge/useDesktopWebAuth'
import {
  deleteSupabaseSession,
  getSupabaseSession,
  saveSupabaseSession
} from '@/shared/composables/useSecureStorage'
import { supabase } from '@/shared/composables/supabaseClient'
import {
  clearAuthUserStorage,
  loadAuthUserFromStorage,
  saveAuthUserToStorage,
  type AuthUser
} from '@/shared/auth/userStorage'
import { resolveSafeRedirectPath } from '@/shared/auth/redirect'

interface Session {
  access_token: string
  refresh_token: string
  expires_at?: number
  token_type?: string
}

interface FinalizeSignInContext {
  supabaseSession: SupabaseSession
  preferredRedirect?: string | null
}

const summarizeAuthCallbackUrl = (value: string): Record<string, unknown> => {
  try {
    const parsed = new URL(value)
    return {
      protocol: parsed.protocol,
      host: parsed.host,
      pathname: parsed.pathname,
      hasTicket: parsed.searchParams.has('ticket'),
      hasState: parsed.searchParams.has('state'),
      hasCode: parsed.searchParams.has('code'),
      hasError: parsed.searchParams.has('error') || parsed.searchParams.has('error_description')
    }
  } catch {
    return { invalidUrl: true }
  }
}

const user = ref<AuthUser | null>(null)
const session = ref<Session | null>(null)
const isLoading = ref(false)
const error = ref<string | null>(null)
let hasHydratedFromStorage = false
let hasBoundAuthStateListener = false
let logoutInFlight: Promise<void> | null = null

const buildAuthUser = (supabaseSession: SupabaseSession): AuthUser => ({
  id: supabaseSession.user.id,
  email: supabaseSession.user.email!,
  name: supabaseSession.user.user_metadata?.name || supabaseSession.user.email,
  avatar_url: supabaseSession.user.user_metadata?.avatar_url,
  provider: supabaseSession.user.app_metadata?.provider || 'oauth',
  created_at: supabaseSession.user.created_at || new Date().toISOString(),
  updated_at: supabaseSession.user.updated_at || new Date().toISOString()
})

const buildSessionSnapshot = (supabaseSession: SupabaseSession): Session => ({
  access_token: supabaseSession.access_token,
  refresh_token: supabaseSession.refresh_token,
  expires_at: supabaseSession.expires_at,
  token_type: supabaseSession.token_type
})

const persistSupabaseSession = async (supabaseSession: SupabaseSession): Promise<void> => {
  await saveSupabaseSession({
    access_token: supabaseSession.access_token,
    refresh_token: supabaseSession.refresh_token,
    expires_at: supabaseSession.expires_at,
    token_type: supabaseSession.token_type,
    user: supabaseSession.user
  })
}

const dispatchSignedIn = (redirectPath?: string): void => {
  if (!redirectPath) {
    return
  }
  window.dispatchEvent(new CustomEvent('dawnchat-auth-signed-in', {
    detail: { redirectPath }
  }))
}

const loadUserFromStorage = async (force = false): Promise<void> => {
  if (hasHydratedFromStorage && !force) {
    return
  }
  user.value = await loadAuthUserFromStorage()
  hasHydratedFromStorage = true
  if (user.value?.email) {
    logger.info('从持久化存储加载用户信息成功')
  }
}

const clearUserFromStorage = async (): Promise<void> => {
  await clearAuthUserStorage()
  hasHydratedFromStorage = false
  logger.info('持久化存储中的用户信息已清除')
}

export function useAuth() {
  const { t } = useI18n()
  const { getSession, signOut: supabaseSignOut } = useSupabase()
  const { exchangeDesktopTicket } = useDesktopWebAuth()
  const isAuthenticated = computed(() => user.value !== null)

  const resolvePostLoginRedirect = (preferred?: string | null): string => {
    return resolveSafeRedirectPath(preferred)
  }

  const applySupabaseSession = async (supabaseSession: SupabaseSession) => {
    user.value = buildAuthUser(supabaseSession)
    session.value = buildSessionSnapshot(supabaseSession)
    await Promise.all([
      saveAuthUserToStorage(user.value),
      persistSupabaseSession(supabaseSession)
    ])
    hasHydratedFromStorage = true
    error.value = null
  }

  const finalizeSignIn = async (context: FinalizeSignInContext): Promise<{ redirectPath: string }> => {
    await applySupabaseSession(context.supabaseSession)
    const redirectPath = resolvePostLoginRedirect(context.preferredRedirect)
    logger.info('✅ 登录态收敛完成', {
      userId: context.supabaseSession.user.id,
      redirectPath
    })
    return { redirectPath }
  }

  const restoreSupabaseSessionFromSecureStorage = async (): Promise<void> => {
    const { data: currentData } = await supabase.auth.getSession()
    if (currentData.session?.access_token) {
      return
    }

    const stored = await getSupabaseSession()
    const accessToken = String(stored?.access_token || '').trim()
    const refreshToken = String(stored?.refresh_token || '').trim()
    if (!accessToken || !refreshToken) {
      return
    }

    const { data, error: restoreError } = await supabase.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken
    })
    if (restoreError || !data.session) {
      logger.warn('⚠️ 安全存储会话恢复失败', {
        message: restoreError?.message
      })
      return
    }

    logger.info('✅ 已从安全存储恢复 Supabase 会话', {
      userId: data.session.user.id
    })
  }

  const consumePendingAuthCallback = async (): Promise<string | null> => {
    try {
      const invoke = (window as any).__TAURI_INTERNALS__?.invoke
      if (typeof invoke !== 'function') {
        return null
      }
      const pending = await invoke('consume_pending_auth_callback')
      return typeof pending === 'string' && pending.trim()
        ? pending.trim()
        : null
    } catch (consumeError: any) {
      logger.warn('⚠️ 读取待处理认证回调失败', {
        message: consumeError?.message
      })
      return null
    }
  }

  const processAuthCallback = async (url: string, source: 'event' | 'pending'): Promise<void> => {
    logger.info('🔗 收到认证回调 Deep Link', {
      source,
      ...summarizeAuthCallbackUrl(url)
    })
    if (!url?.startsWith('dawnchat://auth/callback')) {
      logger.warn('⚠️ 收到非认证回调 Deep Link，已忽略', summarizeAuthCallbackUrl(url))
      return
    }
    logger.info('✅ 检测到认证回调 URL，开始处理...')
    const result = await handleDeepLinkCallback(url)
    if (result.success && result.redirectPath) {
      dispatchSignedIn(result.redirectPath)
    }
  }

  const bindAuthStateListener = () => {
    if (hasBoundAuthStateListener) {
      return
    }
    supabase.auth.onAuthStateChange(async (authEvent: AuthChangeEvent, newSession: SupabaseSession | null) => {
      logger.info('🔄 Supabase Auth 状态变化', {
        event: authEvent,
        hasSession: Boolean(newSession),
        userId: newSession?.user?.id
      })

      if (newSession) {
        if (authEvent === 'SIGNED_IN' || authEvent === 'TOKEN_REFRESHED' || authEvent === 'USER_UPDATED') {
          await applySupabaseSession(newSession)
        }
        return
      }

      if (authEvent === 'SIGNED_OUT') {
        user.value = null
        session.value = null
        await deleteSupabaseSession()
        await clearUserFromStorage()
      }
    })
    hasBoundAuthStateListener = true
  }

  /**
   * 处理 Deep Link 回调 - 纯前端实现
   */
  const handleDeepLinkCallback = async (url: string): Promise<{ success: boolean; redirectPath?: string; error?: string }> => {
    isLoading.value = true
    try {
      logger.info('=' .repeat(60))
      logger.info('📱 收到 Deep Link 回调（纯前端）', summarizeAuthCallbackUrl(url))

      // 解析 URL 参数
      const urlObj = new URL(url)
      const ticket = urlObj.searchParams.get('ticket')
      const state = urlObj.searchParams.get('state')

      logger.info('🔍 解析参数', {
        ticket: ticket ? `${ticket.substring(0, 8)}...` : 'null',
        state: state ? `${state.substring(0, 10)}...` : 'null'
      })

      if (!ticket) {
        throw new Error('登录回调缺少 ticket 参数，请从桌面端重新发起登录')
      }
      logger.info('🔄 开始处理 Web Bridge ticket 回调...')
      const bridgeResult = await exchangeDesktopTicket(url)
      const finalized = await finalizeSignIn({
        supabaseSession: bridgeResult.session,
        preferredRedirect: bridgeResult.nextPath
      })
      logger.info('✅ Web Bridge ticket 登录成功')

      logger.info('=' .repeat(60))
      return {
        success: true,
        redirectPath: finalized.redirectPath
      }

    } catch (err: any) {
      logger.error('❌ 处理回调失败', {
        message: err.message,
        stack: err.stack
      })
      const message = err.message || t.value.auth.authFailed
      error.value = message
      return { success: false, error: message }
    } finally {
      isLoading.value = false
    }
  }

  // 通知后端函数已移除 - 纯前端认证

  /**
   * 远端 Supabase 会话清理：不阻塞 UI / 路由，失败仅记录日志（本地已登出）。
   */
  const signOutSupabaseInBackground = (): void => {
    void (async () => {
      try {
        const result = await supabaseSignOut()
        if (!result.success) {
          logger.warn('Supabase 登出返回异常，本地已登出', {
            message: result.error
          })
        } else {
          logger.info('Supabase 远端会话已清理')
        }
      } catch (err: unknown) {
        logger.error('Supabase 登出异常（本地已登出）', err)
      }
    })()
  }

  /**
   * 登出：先同步清空内存并 await 本地安全存储清理，供路由守卫识别为未登录；
   * Supabase signOut 在后台执行，避免慢网络阻塞跳转登录页。
   */
  const logout = async () => {
    if (logoutInFlight) {
      logger.info('logout 已在执行中，忽略重复请求')
      return logoutInFlight
    }

    logoutInFlight = (async () => {
      try {
        logger.info('开始登出（本地优先）...')
        user.value = null
        session.value = null
        error.value = null

        await Promise.all([
          deleteSupabaseSession(),
          clearUserFromStorage()
        ])

        logger.info('本地会话已清除')
        signOutSupabaseInBackground()
      } catch (err: unknown) {
        logger.error('登出失败（本地清理）:', err)
        error.value =
          err instanceof Error ? err.message : t.value.auth.logoutFailed
        await Promise.all([
          deleteSupabaseSession(),
          clearUserFromStorage()
        ])
        signOutSupabaseInBackground()
      } finally {
        logoutInFlight = null
      }
    })()

    return logoutInFlight
  }

  /**
   * 检查认证状态 - 纯前端实现
   */
  const checkAuthStatus = async () => {
    logger.info('🔎 检查认证状态（纯前端）...')
    try {
      await restoreSupabaseSessionFromSecureStorage()
      // 使用 Supabase 的纯前端会话检查
      const supabaseSession = await getSession()

      if (supabaseSession && supabaseSession.user) {
        await applySupabaseSession(supabaseSession)
        logger.info('✅ 认证状态正常', { email: user.value?.email })
      } else {
        logger.info('ℹ️ 用户未登录或会话已过期')
        user.value = null
        session.value = null
        await deleteSupabaseSession()
      }

    } catch (err) {
      logger.error('❌ 检查认证状态失败', err)
      user.value = null
      session.value = null
    }
  }

  /**
   * 初始化认证监听器
   */
  const initAuthListener = async () => {
    try {
      logger.info('🔧 初始化认证监听器 (v2)...')
      bindAuthStateListener()

      // 尝试加载 Tauri 事件监听器（仅在 Tauri 环境中可用）
      try {
        const { listen } = await import('@tauri-apps/api/event')
        // 监听从 Rust 后端发送的认证回调事件
        await listen<string>('deep-link-auth-callback', async (event) => {
          await processAuthCallback(event.payload, 'event')
        })

        logger.info('✅ 认证回调监听器已注册 (deep-link-auth-callback)')
        const pendingCallback = await consumePendingAuthCallback()
        if (pendingCallback) {
          await processAuthCallback(pendingCallback, 'pending')
        }
      } catch (tauriErr) {
        logger.info('ℹ️  Tauri 事件监听器不可用，跳过 Deep Link 监听')
      }

      // 检查当前认证状态
      await checkAuthStatus()

    } catch (err: any) {
      logger.error('❌ 初始化认证监听器失败', {
        message: err.message,
        stack: err.stack
      })
    }
  }

  return {
    // 状态
    user: computed(() => user.value),
    session: computed(() => session.value),
    isAuthenticated,
    isLoading: computed(() => isLoading.value),
    error: computed(() => error.value),

    // 方法
    logout,
    checkAuthStatus,
    initAuthListener,
    loadUserFromStorage,
    handleDeepLinkCallback,
    finalizeSignIn
  }
}
