import { onMounted, onUnmounted, watch, type ComputedRef } from 'vue'
import { useCodingAgentStore } from '@/features/coding-agent/store/codingAgentStore'
import { logger } from '@/utils/logger'

interface UseWorkbenchCodingRuntimeOptions {
  pluginId: ComputedRef<string>
}

export const useWorkbenchCodingRuntime = (options: UseWorkbenchCodingRuntimeOptions) => {
  const codingAgentStore = useCodingAgentStore()

  const ensureReady = async (reason: string) => {
    const id = String(options.pluginId.value || '').trim()
    if (!id) return false
    try {
      await codingAgentStore.ensureReadyWithWorkspace({ pluginId: id })
      return true
    } catch (error) {
      logger.error('workbench_coding_runtime_ensure_failed', {
        reason,
        pluginId: id,
        error: error instanceof Error ? error.message : String(error)
      })
      return false
    }
  }

  watch(
    () => options.pluginId.value,
    async (next, prev) => {
      if (!next || next === prev) return
      await ensureReady('plugin_changed')
    }
  )

  onMounted(async () => {
    await ensureReady('workbench_mounted')
  })

  onUnmounted(() => {
    codingAgentStore.dispose()
  })

  return {
    ensureReady,
  }
}
