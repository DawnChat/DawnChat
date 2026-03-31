/**
 * 适配层统一导出
 */

export { isTauri, isDevMode, isProdMode, getEnvName } from './env'

export {
  type UnlistenFn,
  type EventPayload,
  listen,
  emit,
  EVENTS
} from './events'
