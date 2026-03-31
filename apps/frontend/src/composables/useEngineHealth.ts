import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import type { EngineId } from '../services/coding-agent/adapterRegistry'
import { checkEngineHealth } from '../services/coding-agent/engineCapabilities'
import { logger } from '../utils/logger'

export type EngineHealthStatus = 'checking' | 'healthy' | 'unhealthy'

const POLL_INTERVAL_MS = 8000

export function useEngineHealth(selectedEngine: Ref<EngineId>) {
  const status = ref<EngineHealthStatus>('checking')
  const detail = ref('')
  let pollTimer: number | null = null
  let requestSeq = 0

  const clearPollTimer = () => {
    if (pollTimer !== null) {
      window.clearInterval(pollTimer)
      pollTimer = null
    }
  }

  const refresh = async () => {
    const currentSeq = ++requestSeq
    const engineId = selectedEngine.value
    status.value = status.value === 'healthy' ? 'healthy' : 'checking'
    try {
      const health = await checkEngineHealth(engineId)
      if (currentSeq !== requestSeq) return
      status.value = health.healthy ? 'healthy' : 'unhealthy'
      detail.value = health.detail
    } catch (err) {
      if (currentSeq !== requestSeq) return
      status.value = 'unhealthy'
      detail.value = err instanceof Error ? err.message : String(err)
      logger.debug('[codingAgentStore] engine health check failed', {
        engineId,
        detail: detail.value
      })
    }
  }

  const startPolling = () => {
    clearPollTimer()
    void refresh()
    pollTimer = window.setInterval(() => {
      void refresh()
    }, POLL_INTERVAL_MS)
  }

  watch(
    selectedEngine,
    () => {
      status.value = 'checking'
      detail.value = ''
      startPolling()
    },
    { immediate: true }
  )

  onUnmounted(() => {
    clearPollTimer()
  })

  return {
    engineHealthStatus: computed(() => status.value),
    engineHealthTitle: computed(() => detail.value)
  }
}
