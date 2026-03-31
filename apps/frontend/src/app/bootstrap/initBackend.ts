import { EVENTS, listen } from '@/adapters/events'
import { useBackendStatus } from '@/composables/useBackendStatus'
import { logger } from '@/utils/logger'

const normalizeErrorMessage = (value: unknown): string => {
  if (typeof value === 'string' && value.trim()) {
    return value.trim()
  }
  return '后端服务启动失败，请检查应用日志'
}

export async function initBackendBootstrap(): Promise<() => void> {
  const backend = useBackendStatus()
  const unlisteners: Array<() => void> = []

  await backend.startChecking('waiting_for_backend')

  const unlistenStartFailed = await listen<string>(EVENTS.BACKEND_START_FAILED, (event) => {
    const message = normalizeErrorMessage(event.payload)
    logger.error('❌ 收到后端启动失败事件', { message })
    backend.markFailed(message)
  })
  unlisteners.push(unlistenStartFailed)

  const restartHandler = () => {
    logger.warn('⚠️ 收到后端重启事件，重新进入启动门禁')
    backend.markRestarting()
    void backend.startChecking('backend_restarting')
  }

  const unlistenRestarting = await listen(EVENTS.BACKEND_RESTARTING, restartHandler)
  const unlistenCrashed = await listen(EVENTS.BACKEND_CRASHED, restartHandler)
  unlisteners.push(unlistenRestarting, unlistenCrashed)

  return () => {
    backend.stopChecking()
    for (const unlisten of unlisteners) {
      unlisten()
    }
  }
}
