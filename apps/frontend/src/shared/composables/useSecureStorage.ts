/**
 * 安全存储管理器 - 跨环境存储适配
 *
 * 生产环境（Tauri）：使用 tauri-plugin-store
 * 开发环境（浏览器）：使用 localStorage
 */

import { isTauri } from '@/adapters/env'
import { logger } from '@/utils/logger'

export interface SecureStorage {
  get<T>(key: string): Promise<T | null>
  set(key: string, value: any): Promise<void>
  delete(key: string): Promise<void>
  clear(): Promise<void>
}

export const STORAGE_KEYS = {
  DEVICE_ID: 'dawnchat_device_id',
  MATRIX_DEVICE_ID: 'dawnchat_matrix_device_id',
  SUPABASE_SESSION: 'dawnchat_supabase_session',
  USER_INFO: 'dawnchat_user_info'
} as const

const createTauriStore = (): SecureStorage => {
  const storePath = 'dawnchat/secure_storage.dat'
  let storePromise: Promise<any> | null = null

  const getStore = async () => {
    if (!storePromise) {
      const { load } = await import('@tauri-apps/plugin-store')
      storePromise = load(storePath)
    }
    return storePromise
  }

  return {
    async get<T>(key: string): Promise<T | null> {
      try {
        const store = await getStore()
        const value = await store.get(key) as T
        return value !== undefined ? value : null
      } catch (error) {
        logger.error(`[TauriStore] get failed: ${key}`, error)
        return null
      }
    },
    async set(key: string, value: any): Promise<void> {
      const store = await getStore()
      await store.set(key, value)
      await store.save()
    },
    async delete(key: string): Promise<void> {
      const store = await getStore()
      await store.delete(key)
      await store.save()
    },
    async clear(): Promise<void> {
      const store = await getStore()
      for (const key of Object.values(STORAGE_KEYS)) {
        await store.delete(key)
      }
      await store.save()
    }
  }
}

const createLocalStorage = (): SecureStorage => {
  const prefix = 'dawnchat_dev_'

  return {
    async get<T>(key: string): Promise<T | null> {
      try {
        const value = localStorage.getItem(prefix + key)
        if (value === null) return null
        return JSON.parse(value) as T
      } catch (error) {
        logger.error(`[LocalStorage] get failed: ${key}`, error)
        return null
      }
    },
    async set(key: string, value: any): Promise<void> {
      localStorage.setItem(prefix + key, JSON.stringify(value))
    },
    async delete(key: string): Promise<void> {
      localStorage.removeItem(prefix + key)
    },
    async clear(): Promise<void> {
      for (const key of Object.values(STORAGE_KEYS)) {
        localStorage.removeItem(prefix + key)
      }
    }
  }
}

let storageInstance: SecureStorage | null = null

export const getStorage = (): SecureStorage => {
  if (!storageInstance) {
    storageInstance = isTauri() ? createTauriStore() : createLocalStorage()
  }
  return storageInstance
}

export const generatePersistentDeviceId = async (): Promise<string> => {
  const storage = getStorage()
  const legacyDeviceId = await storage.get<string>(STORAGE_KEYS.MATRIX_DEVICE_ID)
  if (legacyDeviceId) {
    await storage.set(STORAGE_KEYS.DEVICE_ID, legacyDeviceId)
    return legacyDeviceId
  }

  const existingDeviceId = await storage.get<string>(STORAGE_KEYS.DEVICE_ID)
  if (existingDeviceId) return existingDeviceId

  const timestamp = Date.now()
  const randomPart = Math.random().toString(36).substring(2, 11)
  const newDeviceId = `DAWNCHAT_DESKTOP_${timestamp}_${randomPart}`
  await storage.set(STORAGE_KEYS.DEVICE_ID, newDeviceId)
  return newDeviceId
}

export const getDeviceId = async (): Promise<string | null> => {
  const storage = getStorage()
  return storage.get<string>(STORAGE_KEYS.DEVICE_ID)
}

export const saveSupabaseSession = async (session: any): Promise<void> => {
  const storage = getStorage()
  await storage.set(STORAGE_KEYS.SUPABASE_SESSION, session)
}

export const getSupabaseSession = async (): Promise<any | null> => {
  const storage = getStorage()
  return storage.get(STORAGE_KEYS.SUPABASE_SESSION)
}

export const deleteSupabaseSession = async (): Promise<void> => {
  const storage = getStorage()
  await storage.delete(STORAGE_KEYS.SUPABASE_SESSION)
}

export const saveAuthUserToSecureStorage = async (user: any): Promise<void> => {
  const storage = getStorage()
  await storage.set(STORAGE_KEYS.USER_INFO, user)
}

export const getAuthUserFromSecureStorage = async <T>(): Promise<T | null> => {
  const storage = getStorage()
  return storage.get<T>(STORAGE_KEYS.USER_INFO)
}

export const deleteAuthUserFromSecureStorage = async (): Promise<void> => {
  const storage = getStorage()
  await storage.delete(STORAGE_KEYS.USER_INFO)
}

export const clearAllStorage = async (): Promise<void> => {
  const storage = getStorage()
  const keys = [
    STORAGE_KEYS.MATRIX_DEVICE_ID,
    STORAGE_KEYS.SUPABASE_SESSION,
    STORAGE_KEYS.USER_INFO
  ]
  for (const key of keys) {
    await storage.delete(key)
  }
}
