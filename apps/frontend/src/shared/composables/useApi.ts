/**
 * 统一的 API 请求管理器
 * 处理 Supabase token 刷新、错误重试等逻辑
 */
import { supabase } from '@/shared/composables/supabaseClient'
import { logger } from '@/utils/logger'
import { getSupabaseSession, saveSupabaseSession } from '@/shared/composables/useSecureStorage'
import { useI18n } from '@/composables/useI18n'

const { t } = useI18n()

// 请求配置接口
interface RequestConfig extends RequestInit {
  retryOnAuthError?: boolean
  maxRetries?: number
}

// API 响应接口
interface ApiResponse<T = any> {
  success: boolean
  data?: T
  error?: string
  status?: number
}

// Token 刷新检查阈值（5分钟）
const TOKEN_REFRESH_THRESHOLD = 5 * 60 * 1000

/**
 * 检查 token 是否需要刷新
 */
const isTokenExpiringSoon = (expiresAt: number): boolean => {
  const now = Date.now()
  const timeUntilExpiry = expiresAt - now
  
  logger.debug('🔍 Token 过期检查:', {
    now: new Date(now).toISOString(),
    expiresAt: new Date(expiresAt).toISOString(),
    timeUntilExpiry: Math.round(timeUntilExpiry / 1000) + t.value.common.seconds,
    threshold: Math.round(TOKEN_REFRESH_THRESHOLD / 1000) + t.value.common.seconds,
    isExpiringSoon: timeUntilExpiry < TOKEN_REFRESH_THRESHOLD
  })
  
  return timeUntilExpiry < TOKEN_REFRESH_THRESHOLD
}

/**
 * 刷新 Supabase session
 */
const refreshSupabaseSession = async (): Promise<boolean> => {
  try {
    logger.info('🔄 尝试刷新 Supabase session...')
    
    const { data, error } = await supabase.auth.refreshSession()
    
    logger.debug('🔍 Session 刷新结果:', {
      hasData: !!data,
      hasSession: !!data?.session,
      error: error
    })
    
    if (error) {
      logger.error('❌ 刷新 session 失败:', error)
      return false
    }
    
    if (data.session) {
      logger.debug('🔍 新 session 数据:', {
        access_token: data.session.access_token?.substring(0, 10) + '...',
        expires_at: data.session.expires_at,
        expires_at_date: data.session.expires_at ? new Date(data.session.expires_at).toISOString() : null,
        user_id: data.session.user?.id
      })
      
      // 保存新的 session
      await saveSupabaseSession({
        access_token: data.session.access_token,
        refresh_token: data.session.refresh_token,
        expires_at: data.session.expires_at,
        token_type: data.session.token_type,
        user: data.session.user
      })
      
      logger.info('✅ Session 刷新成功')
      return true
    }
    
    return false
  } catch (error) {
    logger.error('❌ 刷新 session 异常:', error)
    return false
  }
}

/**
 * 获取有效的 access token
 */
const getValidAccessToken = async (): Promise<string | null> => {
  try {
    // 首先尝试从存储获取 session
    const storedSession = await getSupabaseSession()
    
    logger.debug('🔍 从存储获取的 session:', {
      hasStoredSession: !!storedSession,
      storedSessionData: storedSession ? {
        has_access_token: !!storedSession.access_token,
        has_expires_at: !!storedSession.expires_at,
        expires_at: storedSession.expires_at,
        expires_at_date: storedSession.expires_at ? new Date(storedSession.expires_at * 1000).toISOString() : null,
        user_id: storedSession.user?.id
      } : null
    })

    // 如果有存储的 session，先检查它
    if (storedSession && storedSession.access_token) {
      // 注意：expires_at 是秒时间戳，需要转换为毫秒进行比较
      if (storedSession.expires_at && isTokenExpiringSoon(storedSession.expires_at * 1000)) {
        logger.info('⏰ 存储的 Token 即将过期，需要刷新')
        const refreshed = await refreshSupabaseSession()
        if (refreshed) {
          // 重新获取刷新后的 session
          const { data: { session: newSession } } = await supabase.auth.getSession()
          return newSession?.access_token || null
        }
      } else {
        logger.debug('✅ 存储的 Token 仍然有效')
        return storedSession.access_token
      }
    }

    // 如果存储的 session 无效，尝试从 Supabase 获取当前 session
    logger.debug('🔍 尝试从 Supabase 获取当前 session')
    const { data: { session: currentSession } } = await supabase.auth.getSession()
    
    logger.debug('🔍 获取当前 Supabase session:', {
      hasSession: !!currentSession,
      sessionData: currentSession ? {
        access_token: currentSession.access_token?.substring(0, 10) + '...',
        expires_at: currentSession.expires_at,
        expires_at_date: currentSession.expires_at ? new Date(currentSession.expires_at * 1000).toISOString() : null,
        user_id: currentSession.user?.id
      } : null
    })
    
    if (currentSession) {
      // 检查 token 是否即将过期 - 注意：expires_at 是秒时间戳，需要转换为毫秒进行比较
      if (currentSession.expires_at && isTokenExpiringSoon(currentSession.expires_at * 1000)) {
        logger.info('⏰ Token 即将过期，需要刷新')
        const refreshed = await refreshSupabaseSession()
        if (refreshed) {
          // 重新获取刷新后的 session
          const { data: { session: newSession } } = await supabase.auth.getSession()
          return newSession?.access_token || null
        }
      }
      return currentSession.access_token
    }
    
    logger.debug('🔍 没有可用的 session')
    return null
  } catch (error) {
    logger.error('❌ 获取有效 access token 失败:', error)
    return null
  }
}

/**
 * 统一的 API 请求方法
 */
export const apiRequest = async <T = any>(
  url: string,
  config: RequestConfig = {}
): Promise<ApiResponse<T>> => {
  const {
    retryOnAuthError = true,
    maxRetries = 1,
    headers = {},
    ...restConfig
  } = config
  
  let retries = 0
  
  while (retries <= maxRetries) {
    try {
      // 获取有效的 access token
      const accessToken = await getValidAccessToken()
      const { t } = useI18n()
      
      if (!accessToken) {
        return {
          success: false,
          error: t.value.auth.noValidToken
        }
      }
      
      // 构建请求头
      const requestHeaders: HeadersInit = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`,
        ...headers
      }
      
      logger.info(`📡 API 请求: ${url} (尝试 ${retries + 1}/${maxRetries + 1})`)
      
      // 添加请求超时控制（30秒）
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 30000)
      
      const response = await fetch(url, {
        ...restConfig,
        headers: requestHeaders,
        signal: controller.signal
      })
      
      clearTimeout(timeoutId)
      
      // 处理响应
      if (!response.ok) {
        const errorText = await response.text()
        
        // 如果是认证错误且允许重试
        if (response.status === 401 && retryOnAuthError && retries < maxRetries) {
          logger.warn(`⚠️ 认证失败，尝试刷新 token 后重试...`)
          
          // 尝试刷新 session
          const refreshed = await refreshSupabaseSession()
          if (refreshed) {
            retries++
            continue // 重试请求
          }
        }
        
        return {
          success: false,
          error: `HTTP ${response.status}: ${response.statusText} - ${errorText}`,
          status: response.status
        }
      }
      
      // 解析响应数据
      let data: T
      const contentType = response.headers.get('content-type')
      
      if (contentType && contentType.includes('application/json')) {
        data = await response.json()
      } else {
        data = await response.text() as unknown as T
      }
      
      return {
        success: true,
        data,
        status: response.status
      }
      
    } catch (error) {
      logger.error(`❌ API 请求失败 (尝试 ${retries + 1}):`, error)
      
      // 处理特定错误类型
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          return {
            success: false,
            error: t.value.network.requestTimeout
          }
        }
      }
      
      // 网络错误等，不重试
      return {
        success: false,
        error: error instanceof Error ? error.message : t.value.network.networkRequestFailed
      }
    }
  }
  
  return {
    success: false,
    error: t.value.auth.maxRetriesReached
  }
}

/**
 * 检查当前认证状态
 */
export const checkAuthStatus = async (): Promise<boolean> => {
  try {
    const token = await getValidAccessToken()
    return token !== null
  } catch (error) {
    logger.error('❌ 检查认证状态失败:', error)
    return false
  }
}
