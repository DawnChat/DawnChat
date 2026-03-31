import type { Router } from 'vue-router'
import type { ThemeMode } from '@/shared/types/common'
import { logger } from '@/utils/logger'
import { isTauri } from '@/adapters/env'
import { initThemeBootstrap } from '@/app/bootstrap/initTheme'
import { initI18nBootstrap } from '@/app/bootstrap/initI18n'
import { initBackendBootstrap } from '@/app/bootstrap/initBackend'
import { initAuthBootstrap } from '@/app/bootstrap/initAuth'
import { initDeepLinkBootstrap } from '@/app/bootstrap/initDeepLink'

interface AppBootstrapOptions {
  router: Router
  initTheme: () => void
  getTheme: () => ThemeMode
  initI18n: () => void
  initAuthListener: () => Promise<void>
  loadUserFromStorage: () => Promise<void>
}

const resolveAppVersion = async (): Promise<string> => {
  if (!isTauri()) return 'web-dev'
  try {
    const { getVersion } = await import('@tauri-apps/api/app')
    return await getVersion()
  } catch {
    return 'unknown'
  }
}

export async function bootstrapApp(options: AppBootstrapOptions): Promise<() => void> {
  const appVersion = await resolveAppVersion()
  logger.info('🚀 App.vue 初始化开始')
  logger.info(`📱 应用版本: ${appVersion}`)

  initThemeBootstrap(options.initTheme, options.getTheme)
  initI18nBootstrap(options.initI18n)
  const unlistenBackend = await initBackendBootstrap()
  const removeAuthSignedInListener = await initAuthBootstrap({
    router: options.router,
    initAuthListener: options.initAuthListener,
    loadUserFromStorage: options.loadUserFromStorage
  })
  const unlistenDeepLink = await initDeepLinkBootstrap(options.router)

  logger.info('🎉 App.vue 初始化完成')
  return () => {
    unlistenBackend()
    removeAuthSignedInListener()
    unlistenDeepLink()
  }
}
