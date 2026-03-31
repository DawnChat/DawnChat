import { logger } from '@/utils/logger'

export function initI18nBootstrap(initI18n: () => void) {
  initI18n()
  logger.info('✅ 国际化系统初始化完成')
}
