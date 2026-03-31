import type { Router } from 'vue-router'
import { logger } from '@/utils/logger'

interface InitAuthBootstrapOptions {
  router: Router
  initAuthListener: () => Promise<void>
  loadUserFromStorage: () => Promise<void>
}

export async function initAuthBootstrap(options: InitAuthBootstrapOptions): Promise<() => void> {
  const { router, initAuthListener, loadUserFromStorage } = options

  logger.info('📦 从持久化存储加载用户信息...')
  await loadUserFromStorage()

  logger.info('🔐 开始初始化认证监听器...')
  await initAuthListener()
  logger.info('✅ 认证监听器初始化完成')

  const handleAuthSignedIn = async (event: Event) => {
    const customEvent = event as CustomEvent<{ redirectPath?: string }>
    const redirectPath = customEvent.detail?.redirectPath
    if (!redirectPath) {
      return
    }
    if (router.currentRoute.value.name === 'login' || router.currentRoute.value.name === 'auth-callback') {
      await router.replace(redirectPath)
      logger.info('✅ 登录完成后已路由跳转', { redirectPath })
    }
  }

  window.addEventListener('dawnchat-auth-signed-in', handleAuthSignedIn)
  return () => window.removeEventListener('dawnchat-auth-signed-in', handleAuthSignedIn)
}
