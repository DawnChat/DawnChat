/**
 * 事件监听适配层
 * 
 * 生产环境（Tauri）：使用 @tauri-apps/api/event 的 listen()
 * 开发环境（浏览器）：使用 EventTarget
 */

import { isTauri } from './env'
import { logger } from '../utils/logger'

// ============ 类型定义 ============

export type UnlistenFn = () => void

export interface EventPayload<T> {
  payload: T
}

let devEventTarget: EventTarget | null = null

const getDevEventTarget = (): EventTarget => {
  if (!devEventTarget) {
    devEventTarget = new EventTarget()
  }
  return devEventTarget
}

// ============ 事件监听适配 ============

/**
 * 监听事件
 * 
 * @param event 事件名称
 * @param handler 事件处理函数
 * @returns 取消监听的函数
 */
export const listen = async <T>(
  event: string,
  handler: (event: EventPayload<T>) => void
): Promise<UnlistenFn> => {
  if (isTauri()) {
    const { listen: tauriListen } = await import('@tauri-apps/api/event')
    return tauriListen<T>(event, handler)
  }
  
  // 开发环境：使用 EventTarget
  const eventTarget = getDevEventTarget()
  
  const wrappedHandler = (e: Event) => {
    const customEvent = e as CustomEvent<T>
    handler({ payload: customEvent.detail })
  }
  
  eventTarget.addEventListener(event, wrappedHandler)
  logger.debug(`[DevEvents] 订阅事件: ${event}`)
  
  return () => {
    eventTarget.removeEventListener(event, wrappedHandler)
    logger.debug(`[DevEvents] 取消订阅: ${event}`)
  }
}

/**
 * 触发事件（仅开发环境使用）
 */
export const emit = <T>(event: string, payload: T): void => {
  if (isTauri()) {
    // Tauri 环境下，事件由 Rust 层触发
    logger.warn(`[DevEvents] emit() 在 Tauri 环境下不可用: ${event}`)
    return
  }
  
  const eventTarget = getDevEventTarget()
  const customEvent = new CustomEvent(event, { detail: payload })
  eventTarget.dispatchEvent(customEvent)
  logger.debug(`[DevEvents] 触发事件: ${event}`, payload)
}

// ============ 常用事件名称 ============

export const EVENTS = {
  // 数据库更新事件
  DB_PROJECT_UPDATE: 'db-project-update',
  DB_MESSAGE_UPDATE: 'db-message-update',
  
  // 后端状态事件
  BACKEND_START_FAILED: 'backend-start-failed',
  BACKEND_CRASHED: 'backend-crashed',
  BACKEND_RESTARTING: 'backend-restarting',
  
  // Deep Link 事件
  DEEP_LINK_EVENT: 'deep-link-event',
  
  // 心跳事件
  HEARTBEAT: 'heartbeat'
} as const
