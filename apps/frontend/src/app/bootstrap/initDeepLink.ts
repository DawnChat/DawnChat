import type { Router } from 'vue-router'
import { logger } from '@/utils/logger'
import { parseDeepLink } from '@/app/router/deepLink'

export async function initDeepLinkBootstrap(router: Router): Promise<() => void> {
  logger.info('🔗 初始化新的 Deep Link 监听器...')

  try {
    const { listen } = await import('@tauri-apps/api/event')
    const unlisten = await listen<string[]>('deep-link-route', async (event) => {
      const urls = event.payload || []
      for (const url of urls) {
        const parsed = parseDeepLink(url)
        if (parsed.status === 'valid' && parsed.route) {
          await router.push(parsed.route)
          logger.info('✅ Deep Link 已路由跳转', { url, target: parsed.route })
          break
        }
        if (parsed.status === 'unsupported') {
          logger.info('ℹ️ Deep Link 目标不支持，已忽略', { url, reason: parsed.reason })
        } else {
          logger.warn('⚠️ Deep Link 无效，已忽略', { url, reason: parsed.reason })
        }
      }
    })
    logger.info('✅ Deep Link 路由监听器初始化完成')
    return unlisten
  } catch {
    logger.info('ℹ️ Deep Link 路由监听器不可用，跳过')
    return () => {}
  }
}
