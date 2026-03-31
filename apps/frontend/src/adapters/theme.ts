/**
 * 主题适配层
 * 
 * 封装 Tauri 原生窗口主题设置，提供跨平台支持。
 * 
 * 跨平台兼容性：
 * - macOS 10.14+: 完整支持标题栏颜色
 * - Windows 10+: 完整支持标题栏颜色
 * - Linux: 依赖桌面环境，效果可能有限
 */

import { isTauri } from './env'
import { logger } from '../utils/logger'
import type { ThemeMode } from '@/shared/types/common'

/**
 * 设置原生窗口主题
 * 
 * @param mode 主题模式: 'light' | 'dark'
 */
export async function setNativeTheme(mode: ThemeMode): Promise<void> {
  if (!isTauri()) {
    logger.debug('[Theme] 非 Tauri 环境，跳过原生主题设置')
    return
  }
  
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    await invoke('set_native_theme', { theme: mode })
    logger.info(`[Theme] 原生窗口主题已设置: ${mode}`)
  } catch (error) {
    logger.error('[Theme] 设置原生主题失败:', error)
  }
}

