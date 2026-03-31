/**
 * Supabase 客户端 Composable - 直接在前端处理认证
 */
import { createClient } from '@supabase/supabase-js'
import type { Session as SupabaseSession } from '@supabase/supabase-js'
import { ref } from 'vue'
import { logger } from '@/utils/logger'
import { 
  saveSupabaseSession,
  getSupabaseSession,
  clearAllStorage
} from '@/shared/composables/useSecureStorage'
import { useI18n } from '@/composables/useI18n'

const requireEnv = (key: string): string => {
  const value = String(import.meta.env[key] || '').trim()
  if (!value) {
    throw new Error(`Missing required env: ${key}`)
  }
  return value
}

// 环境变量 - 开源版本禁止硬编码回退
const SUPABASE_URL = requireEnv('VITE_SUPABASE_URL')
const SUPABASE_ANON_KEY = requireEnv('VITE_SUPABASE_ANON_KEY')

// 创建 Supabase 客户端 - 配置 PKCE 模式
export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    flowType: 'pkce',
    detectSessionInUrl: true,
    autoRefreshToken: true,
    persistSession: true
  }
})

interface UserSession {
  access_token: string
  refresh_token: string
  expires_in: number
  token_type: string
  user: any
}

const SIGN_OUT_TIMEOUT_MS = 3000
let signOutInFlight: Promise<{ success: boolean; error?: string }> | null = null

export function useSupabase() {
  const { t } = useI18n()
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  /**
   * 保存会话到安全存储
   */
  const saveSession = async (session: UserSession) => {
    try {
      // Debug: 检查 session 的实际结构
      logger.debug('🔍 保存会话 - 原始 session 数据:', {
        has_access_token: !!session.access_token,
        has_refresh_token: !!session.refresh_token,
        has_expires_in: !!session.expires_in,
        expires_in_value: session.expires_in,
        has_token_type: !!session.token_type,
        has_user: !!session.user,
        user_id: session.user?.id
      })

      // 计算正确的过期时间 - expires_in 是秒数，需要转换为毫秒时间戳
      const expiresAt = Math.floor(Date.now() / 1000) + session.expires_in
      logger.debug('🔍 计算过期时间:', {
        current_time: new Date().toISOString(),
        current_timestamp: Math.floor(Date.now() / 1000),
        expires_in_seconds: session.expires_in,
        calculated_expires_at_timestamp: expiresAt,
        calculated_expires_at_date: new Date(expiresAt * 1000).toISOString()
      })

      // 使用新的安全存储
      await saveSupabaseSession({
        access_token: session.access_token,
        refresh_token: session.refresh_token,
        expires_at: expiresAt,
        token_type: session.token_type,
        user: session.user
      })

      logger.info('💾 会话已保存到安全存储')
      logger.info('🔐 会话信息:', {
        expires_at: new Date(expiresAt).toISOString(),
        user_id: session.user?.id,
        user_email: session.user?.email
      })
    } catch (err) {
      logger.error('❌ 保存会话失败:', err)
      throw err
    }
  }

  /**
   * 清除存储的数据
   */
  const clearStore = async () => {
    try {
      await clearAllStorage()
      logger.info('🗑️ 安全存储已清空')
    } catch (err) {
      logger.error('❌ 清空存储失败:', err)
      throw err
    }
  }

  /**
   * 获取当前会话
   */
  const getSession = async () => {
    try {
      const { data: { session }, error: sessionError } = await supabase.auth.getSession()

      if (sessionError) {
        throw sessionError
      }

      if (session?.access_token) {
        return session
      }

      const storedSession = await getSupabaseSession()
      const accessToken = String(storedSession?.access_token || '').trim()
      const refreshToken = String(storedSession?.refresh_token || '').trim()
      if (!accessToken) {
        logger.warn('⚠️ 当前 Supabase 会话缺失，且安全存储中没有 access token')
        return null
      }

      if (refreshToken) {
        const { data: restoredData, error: restoreError } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken
        })
        if (!restoreError && restoredData.session?.access_token) {
          logger.info('✅ getSession 从安全存储恢复了 Supabase 会话', {
            userId: restoredData.session.user?.id || null
          })
          return restoredData.session
        }
        logger.warn('⚠️ getSession 恢复 Supabase 会话失败，回退到安全存储快照', {
          message: restoreError?.message || null
        })
      } else {
        logger.warn('⚠️ 安全存储中缺少 refresh token，将返回本地 session 快照')
      }

      const fallbackSession = {
        access_token: accessToken,
        refresh_token: refreshToken,
        expires_at: storedSession?.expires_at,
        token_type: storedSession?.token_type || 'bearer',
        user: storedSession?.user || null
      } as SupabaseSession

      return fallbackSession
    } catch (err) {
      logger.error('❌ 获取当前会话失败:', err)
      return null
    }
  }

  /**
   * 登出
   */
  const signOut = async () => {
    if (signOutInFlight) {
      logger.info('ℹ️ 登出已在进行中，复用当前请求')
      return signOutInFlight
    }

    signOutInFlight = (async () => {
      try {
        logger.info('🚪 开始登出流程...')

        const { data: { session: currentSession }, error: sessionError } = await supabase.auth.getSession()
        if (sessionError) {
          logger.warn('⚠️ 获取当前会话失败:', sessionError)
        } else {
          logger.info('📋 当前会话状态:', {
            hasSession: !!currentSession,
            userId: currentSession?.user?.id,
            accessTokenLength: currentSession?.access_token?.length
          })
        }

        logger.info('🔄 调用 Supabase auth.signOut()...')
        const signOutResult = await Promise.race([
          supabase.auth.signOut(),
          new Promise<{ error: Error }>((resolve) => {
            setTimeout(() => {
              resolve({ error: new Error(`Supabase signOut timeout after ${SIGN_OUT_TIMEOUT_MS}ms`) })
            }, SIGN_OUT_TIMEOUT_MS)
          })
        ])

        const signOutError = signOutResult.error
        if (signOutError) {
          if (signOutError.name === 'AuthSessionMissingError') {
            logger.warn('⚠️ Supabase 会话已缺失，这可能是因为会话已过期或已被清除')
          } else if (signOutError.message?.includes('timeout')) {
            logger.warn('⚠️ Supabase signOut 请求超时，已继续执行本地登出清理')
          } else {
            logger.warn('⚠️ Supabase 登出失败，已继续执行本地登出清理:', signOutError)
          }
        } else {
          logger.info('✅ Supabase 登出成功')
        }

        logger.info('🧹 清除本地存储...')
        await clearStore()

        logger.info('✅ 登出流程完成')
        return { success: true }
      } catch (err: any) {
        logger.error('❌ 登出失败:', {
          error: err,
          message: err.message,
          name: err.name,
          code: err.code
        })
        error.value = err.message || t.value.auth.logoutFailed
        return { success: false, error: error.value || t.value.auth.logoutFailed }
      } finally {
        signOutInFlight = null
      }
    })()

    return signOutInFlight
  }

  return {
    supabase,
    isLoading,
    error,
    saveSession,
    clearStore,
    getSession,
    signOut
  }
}
