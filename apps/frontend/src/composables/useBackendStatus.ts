import { ref, readonly, computed } from 'vue'
import { logger } from '../utils/logger'
import { buildBackendUrl, getBackendUrl } from '../utils/backendUrl'
import { useI18n } from './useI18n'

export type BackendPhase =
  | 'waiting_for_backend'
  | 'backend_ready'
  | 'backend_restarting'
  | 'backend_failed'

export interface BackendStatus {
  phase: BackendPhase
  isReady: boolean
  isLoading: boolean
  error: string | null
  retryCount: number
  maxRetries: number
}

const BACKEND_CHECK_INTERVAL = 1000
const BACKEND_RECOVERY_INTERVAL = 3000
const MAX_RETRY_COUNT = 60
const DEFAULT_TIMEOUT_MESSAGE = '服务启动超时，请检查应用日志'
const BACKEND_HEALTH_PATH = '/api/frontend/health'

const createStatus = (phase: BackendPhase, retryCount = 0): BackendStatus => ({
  phase,
  isReady: phase === 'backend_ready',
  isLoading: phase === 'waiting_for_backend' || phase === 'backend_restarting',
  error: null,
  retryCount,
  maxRetries: MAX_RETRY_COUNT
})

const status = ref<BackendStatus>(createStatus('waiting_for_backend'))
let checkInterval: number | null = null
let activeRequestId = 0

export function useBackendStatus() {
  const { t } = useI18n()

  const checkBackendStatus = async (timeoutMs = 2000): Promise<boolean> => {
    const targetUrl = buildBackendUrl(BACKEND_HEALTH_PATH)
    try {
      const response = await fetch(targetUrl, {
        method: 'GET',
        signal: AbortSignal.timeout(timeoutMs),
      })
      
      if (response.ok) {
        const data = await response.json()
        if (data.status === 'ok' && data.name === 'DawnChat') {
          logger.info('✅ 后端服务已就绪', { targetUrl, timeoutMs })
          return true
        }
      }
      return false
    } catch (error) {
      logger.debug('⏳ 后端服务未就绪', {
        targetUrl,
        timeoutMs,
        error: String(error)
      })
      return false
    }
  }

  const stopChecking = () => {
    if (checkInterval) {
      window.clearInterval(checkInterval)
      checkInterval = null
    }
  }

  const markReady = () => {
    stopChecking()
    status.value = {
      ...status.value,
      phase: 'backend_ready',
      isReady: true,
      isLoading: false,
      error: null
    }
  }

  const markFailed = (message: string) => {
    status.value = {
      ...status.value,
      phase: 'backend_failed',
      isReady: false,
      isLoading: false,
      error: message
    }
  }

  const startChecking = async (phase: BackendPhase = 'waiting_for_backend') => {
    logger.info('🔍 开始检测后端服务状态...', {
      phase,
      backendUrl: getBackendUrl()
    })
    stopChecking()
    const requestId = ++activeRequestId
    status.value = createStatus(phase)

    // 立即检查一次
    const isReady = await checkBackendStatus()
    if (requestId !== activeRequestId) {
      return
    }
    if (isReady) {
      markReady()
      return
    }

    // 开始轮询检查
    checkInterval = window.setInterval(async () => {
      if (requestId !== activeRequestId) {
        stopChecking()
        return
      }
      const inFailedRecovery = status.value.phase === 'backend_failed'
      if (!inFailedRecovery && status.value.retryCount >= MAX_RETRY_COUNT) {
        logger.error('❌ 后端服务检测超时，进入自动恢复等待态', {
          backendUrl: getBackendUrl()
        })
        const finalCheckPassed = await checkBackendStatus(5000)
        if (finalCheckPassed) {
          markReady()
          return
        }
        markFailed((t.value as any).backend.checkTimeout || DEFAULT_TIMEOUT_MESSAGE)
        stopChecking()
        checkInterval = window.setInterval(async () => {
          if (requestId !== activeRequestId) {
            stopChecking()
            return
          }
          const recovered = await checkBackendStatus(5000)
          if (recovered) {
            logger.info('✅ 后端在 fatal 后自动恢复，无需手动重试')
            markReady()
            stopChecking()
          }
        }, BACKEND_RECOVERY_INTERVAL)
        return
      }

      if (!inFailedRecovery) {
        status.value = {
          ...status.value,
          retryCount: status.value.retryCount + 1
        }
      }
      const isReady = await checkBackendStatus(inFailedRecovery ? 5000 : 2000)

      if (isReady) {
        logger.info(`✅ 后端服务在第 ${status.value.retryCount} 次检测后就绪`)
        markReady()
      } else {
        logger.debug(`⏳ 第 ${status.value.retryCount} 次检测，后端服务未就绪`, {
          phase: status.value.phase,
          backendUrl: getBackendUrl()
        })
      }
    }, BACKEND_CHECK_INTERVAL)
  }

  const markRestarting = () => {
    status.value = {
      ...status.value,
      phase: 'backend_restarting',
      isReady: false,
      isLoading: true,
      error: null
    }
  }

  const retry = () => {
    logger.info('🔄 手动重试后端服务检测')
    void startChecking('waiting_for_backend')
  }

  return {
    backendUrl: computed(() => getBackendUrl()),
    backendReady: computed(() => status.value.isReady),
    status: readonly(status),
    phase: computed(() => status.value.phase),
    isReady: computed(() => status.value.isReady),
    isLoading: computed(() => status.value.isLoading),
    error: computed(() => status.value.error),
    retryCount: computed(() => status.value.retryCount),
    retry,
    startChecking,
    stopChecking,
    markFailed,
    markRestarting,
    markReady
  }
}
