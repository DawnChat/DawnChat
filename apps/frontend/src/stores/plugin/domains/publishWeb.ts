import { fetchWebPublishTask, fetchWebPublishStatus, normalizeWebPublishError, publishWebPlugin, type WebPublishPayload, type WebPublishStatusResult, type WebPublishTask } from '@/services/plugins/webPublishApi'
import { logger } from '@/utils/logger'
import type { PluginStoreContext } from '@/stores/plugin/context'
import type { WebPublishState } from '@/stores/plugin/types'

export function createPublishWebActions(ctx: PluginStoreContext) {
  const ensurePublishState = (appId: string): WebPublishState => {
    const existing = ctx.state.publishStateMap.value.get(appId)
    if (existing) return existing
    const next = {
      loading: false,
      error: null,
      last_result: null,
      last_status: null,
      active_task: null,
    }
    ctx.state.publishStateMap.value.set(appId, next)
    return next
  }

  const getPublishState = (appId: string) => ensurePublishState(appId)

  const stopPublishPolling = (appId: string) => {
    ctx.state.publishPollers.clear(appId)
  }

  const pollPublishTask = async (appId: string, taskId: string): Promise<WebPublishTask | null> => {
    const state = ensurePublishState(appId)
    try {
      const task = await fetchWebPublishTask(appId, taskId)
      state.active_task = task
      state.error = task.error?.message || null
      if (task.result) {
        state.last_result = task.result
        state.last_status = {
          ...(state.last_status || ({} as WebPublishStatusResult)),
          local_version: task.result.local_version || state.last_status?.local_version || '',
          manifest_version: state.last_status?.manifest_version || '',
          package_version: state.last_status?.package_version || '',
          version_mismatch: state.last_status?.version_mismatch || false,
          remote_latest_version:
            task.result.remote_latest_version || task.result.release?.version || state.last_status?.remote_latest_version || null,
          remote_release_status: task.result.release?.status || state.last_status?.remote_release_status || null,
          current_status: task.result.release?.status || state.last_status?.current_status || 'published',
          current_slug: task.result.web_app?.slug || state.last_status?.current_slug || '',
          runtime_url: task.result.runtime_url || state.last_status?.runtime_url || '',
          last_published_at: task.result.release?.published_at || state.last_status?.last_published_at || null,
          active_task: task,
          metadata: state.last_status?.metadata,
          remote_error: null,
        }
      }
      if (['completed', 'failed'].includes(task.status)) {
        stopPublishPolling(appId)
      }
      return task
    } catch (err: unknown) {
      logger.error('Failed to poll web publish task:', err)
      state.error = err instanceof Error ? err.message : 'Failed to poll publish task'
      stopPublishPolling(appId)
      return null
    }
  }

  const startPublishPolling = (appId: string, taskId: string) => {
    stopPublishPolling(appId)
    void pollPublishTask(appId, taskId)
    const timer = setInterval(() => {
      void pollPublishTask(appId, taskId)
    }, 1200)
    ctx.state.publishPollers.set(appId, timer)
  }

  const waitForPublishTask = async (appId: string, taskId: string): Promise<WebPublishTask> => {
    while (true) {
      const task = await pollPublishTask(appId, taskId)
      if (!task) throw new Error('发布任务状态获取失败')
      if (task.status === 'completed') return task
      if (task.status === 'failed') throw new Error(task.error?.message || task.message || '发布失败')
      await new Promise((resolve) => setTimeout(resolve, 1200))
    }
  }

  const loadPublishStatus = async (appId: string, accessToken?: string) => {
    const state = ensurePublishState(appId)
    try {
      const data = await fetchWebPublishStatus(appId, accessToken)
      state.last_status = data
      state.active_task = data.active_task || null
      state.error = null
      if (data.active_task?.id && ['pending', 'running'].includes(data.active_task.status)) {
        startPublishPolling(appId, data.active_task.id)
      } else {
        stopPublishPolling(appId)
      }
    } catch (err: unknown) {
      logger.error('Failed to load web publish status:', err)
      state.error = err instanceof Error ? err.message : 'Failed to load publish status'
    }
    return state
  }

  const publishWebApp = async (appId: string, payload: WebPublishPayload) => {
    const state = ensurePublishState(appId)
    state.loading = true
    state.error = null
    try {
      const task = await publishWebPlugin(appId, payload)
      state.active_task = task
      if (task.id) {
        startPublishPolling(appId, task.id)
      }
      const completedTask = await waitForPublishTask(appId, task.id)
      const data = completedTask.result
      if (!data) {
        throw new Error(completedTask.error?.message || completedTask.message || '发布失败')
      }
      state.last_result = data
      await ctx.runtimeActions.refreshInstalledApp(appId)
      await loadPublishStatus(appId, payload.supabase_access_token)
      return data
    } catch (err: unknown) {
      const normalized = normalizeWebPublishError(err)
      logger.error('web_publish_failed', {
        pluginId: appId,
        slug: payload.slug || null,
        version: payload.version || null,
        ...normalized.logContext,
      })
      state.error = normalized.message || 'Failed to publish web app'
      throw err
    } finally {
      state.loading = false
    }
  }

  return {
    ensurePublishState,
    getPublishState,
    stopPublishPolling,
    pollPublishTask,
    startPublishPolling,
    waitForPublishTask,
    loadPublishStatus,
    publishWebApp,
  }
}
