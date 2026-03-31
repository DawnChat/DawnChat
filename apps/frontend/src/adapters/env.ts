/**
 * 环境检测工具
 * 
 * 用于检测当前运行环境（Tauri 桌面端 vs 浏览器开发环境）
 */

/**
 * 检测是否在 Tauri 环境中运行
 */
export const isTauri = (): boolean => {
  return typeof window !== 'undefined' && 
         !!(window as any).__TAURI_INTERNALS__
}

/**
 * 检测是否为开发模式
 * 
 * 开发模式的判断逻辑：
 * 1. 显式设置了 VITE_DEV_MODE=true
 * 2. 或者不在 Tauri 环境中（浏览器直接访问）
 */
export const isDevMode = (): boolean => {
  // 如果显式设置了 VITE_DEV_MODE，使用该值
  if (import.meta.env.VITE_DEV_MODE !== undefined) {
    return import.meta.env.VITE_DEV_MODE === 'true'
  }
  // 否则，非 Tauri 环境就是开发模式
  return !isTauri()
}

/**
 * 检测是否为生产模式
 */
export const isProdMode = (): boolean => {
  return !isDevMode()
}

/**
 * 获取当前环境名称（用于日志）
 */
export const getEnvName = (): string => {
  if (isTauri()) {
    return 'Tauri Desktop'
  }
  return isDevMode() ? 'Browser Dev' : 'Browser Prod'
}

