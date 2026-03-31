import { isDevMode } from '@/adapters'
import {
  deleteAuthUserFromSecureStorage,
  getAuthUserFromSecureStorage,
  saveAuthUserToSecureStorage
} from '@/shared/composables/useSecureStorage'
import { logger } from '@/utils/logger'

export const USER_STORAGE_KEY = 'dawnchat_user_info'
export const DEV_MODE_AUTH_KEY = 'dawnchat_dev_mode_auth'
export const DEV_USER_KEY = 'dawnchat_dev_user'

export interface AuthUser {
  id: string
  email: string
  name?: string
  avatar_url?: string
  provider?: string
  created_at?: string
  updated_at?: string
}

const sanitizeAuthUser = (userData: AuthUser): AuthUser => ({
  id: userData.id,
  email: userData.email,
  name: userData.name,
  avatar_url: userData.avatar_url,
  provider: userData.provider,
  created_at: userData.created_at,
  updated_at: userData.updated_at
})

export const loadAuthUserFromStorage = async (): Promise<AuthUser | null> => {
  try {
    if (isDevMode()) {
      const devModeAuth = localStorage.getItem(DEV_MODE_AUTH_KEY)
      const devUserStr = localStorage.getItem(DEV_USER_KEY)
      if (devModeAuth === 'true' && devUserStr) {
        return JSON.parse(devUserStr) as AuthUser
      }
    }

    const secureUser = await getAuthUserFromSecureStorage<AuthUser>()
    if (secureUser?.email) {
      const safeUser = sanitizeAuthUser(secureUser)
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(safeUser))
      return safeUser
    }

    const storedUser = localStorage.getItem(USER_STORAGE_KEY)
    if (!storedUser) {
      return null
    }
    const safeUser = sanitizeAuthUser(JSON.parse(storedUser) as AuthUser)
    await saveAuthUserToSecureStorage(safeUser)
    return safeUser
  } catch (error) {
    logger.error('加载用户信息失败:', error)
    localStorage.removeItem(USER_STORAGE_KEY)
    await deleteAuthUserFromSecureStorage()
    return null
  }
}

export const saveAuthUserToStorage = async (userData: AuthUser): Promise<void> => {
  try {
    const safeUserData = sanitizeAuthUser(userData)
    await saveAuthUserToSecureStorage(safeUserData)
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(safeUserData))
  } catch (error) {
    logger.error('保存用户信息失败:', error)
  }
}

export const clearAuthUserStorage = async (): Promise<void> => {
  try {
    await deleteAuthUserFromSecureStorage()
    localStorage.removeItem(USER_STORAGE_KEY)
    localStorage.removeItem(DEV_MODE_AUTH_KEY)
    localStorage.removeItem(DEV_USER_KEY)
  } catch (error) {
    logger.error('清除用户信息失败:', error)
  }
}
