import { onMounted, onUnmounted, watch, type ComputedRef } from 'vue'
import { useCodingAgentStore } from '@/features/coding-agent/store/codingAgentStore'
import { logger } from '@/utils/logger'
import { buildBackendUrl } from '@/utils/backendUrl'

interface UseWorkbenchCodingRuntimeOptions {
  pluginId: ComputedRef<string>
}

export const useWorkbenchCodingRuntime = (options: UseWorkbenchCodingRuntimeOptions) => {
  const codingAgentStore = useCodingAgentStore()

  const readOpencodeWorkspaceSnapshot = async (): Promise<{
    workspacePath: string
    startupPluginId: string
    startupWorkspaceKind: string
  }> => {
    if (typeof fetch !== 'function') {
      return {
        workspacePath: '',
        startupPluginId: '',
        startupWorkspaceKind: '',
      }
    }
    try {
      const response = await fetch(buildBackendUrl('/api/opencode/workspace'))
      if (!response.ok) {
        return {
          workspacePath: '',
          startupPluginId: '',
          startupWorkspaceKind: '',
        }
      }
      const payload = await response.json().catch(() => ({}))
      return {
        workspacePath: String(payload?.data?.workspace_path || '').trim(),
        startupPluginId: String(payload?.data?.startup_context?.plugin_id || '').trim(),
        startupWorkspaceKind: String(payload?.data?.startup_context?.workspace_kind || '').trim(),
      }
    } catch {
      return {
        workspacePath: '',
        startupPluginId: '',
        startupWorkspaceKind: '',
      }
    }
  }

  const ensureReady = async (reason: string) => {
    const id = String(options.pluginId.value || '').trim()
    if (!id) return false
    try {
      await codingAgentStore.ensureReadyWithWorkspace({ pluginId: id })
      const workspaceSnapshot = await readOpencodeWorkspaceSnapshot()
      logger.info('workbench_coding_runtime_workspace_snapshot', {
        reason,
        routePluginId: id,
        boundWorkspacePluginId: String(codingAgentStore.boundWorkspaceTarget?.pluginId || ''),
        boundWorkspaceId: String(codingAgentStore.boundWorkspaceTarget?.id || ''),
        workspaceProfilePath: String(codingAgentStore.workspaceProfile?.workspacePath || ''),
        activeSessionId: String(codingAgentStore.activeSessionId || ''),
        opencodeWorkspacePath: workspaceSnapshot.workspacePath,
        opencodeStartupPluginId: workspaceSnapshot.startupPluginId,
        opencodeStartupWorkspaceKind: workspaceSnapshot.startupWorkspaceKind,
      })
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
