import { logger } from '@/utils/logger'
import type { ThemeMode } from '@/shared/types/common'

export function initThemeBootstrap(initTheme: () => void, getTheme: () => ThemeMode) {
  initTheme()
  logger.info('✅ 主题系统初始化完成', { theme: getTheme() })
}
