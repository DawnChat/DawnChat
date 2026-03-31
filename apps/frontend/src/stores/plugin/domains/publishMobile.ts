import { fetchMobilePublishStatus, fetchMobilePublishTask, normalizeMobilePublishError, publishMobilePlugin, refreshMobileShare, type MobilePublishPayload, type MobilePublishTask } from '@/services/plugins/mobilePublishApi'
import { logger } from '@/utils/logger'
import type { PluginStoreContext } from '@/stores/plugin/context'
import type { MobilePublishState } from '@/stores/plugin/types'

export function createPublishMobileActions(ctx: PluginStoreContext) {
  const ensureMobilePublishState = (appId: string): MobilePublishState => {
    const existing = ctx.state.mobilePublishStateMap.value.get(appId)
    if (existing) return existing
    const next = {
      loading: false,
      error: null,
      last_result: null,
      last_status: null,
      active_task: null,
    }
    ctx.state.mobilePublishStateMap.value.set(appId, next)
    return next
  }

  const getMobilePublishState = (appId: string) => ensureMobilePublishState(appId)

  const stopMobilePublishPolling = (appId: string) => {
    ctx.state.mobilePublishPollers.clear(appId)
  }

  const pollMobilePublishTask = async (appId: string, taskId: string): Promise<MobilePublishTask | null> => {
    const state = ensureMobilePublishState(appId)
    try {
      const task = await fetchMobilePublishTask(appId, taskId)
      state.active_task = task
      state.error = task.error?.message || null
      if (task.result) {
        state.last_result = task.result
      }
      if (['completed', 'failed'].includes(task.status)) {
        stopMobilePublishPolling(appId)
      }
      return task
    } catch (err: unknown) {
      logger.error('Failed to poll mobile publish task:', err)
      state.error = err instanceof Error ? err.message : 'Failed to poll mobile publish task'
      stopMobilePublishPolling(appId)
      return null
    }
  }

  const startMobilePublishPolling = (appId: string, taskId: string) => {
    stopMobilePublishPolling(appId)
    void pollMobilePublishTask(appId, taskId)
    const timer = setInterval(() => {
      void pollMobilePublishTask(appId, taskId)
    }, 1200)
    ctx.state.mobilePublishPollers.set(appId, timer)
  }

  const waitForMobilePublishTask = async (appId: string, taskId: string): Promise<MobilePublishTask> => {
    while (true) {
      const task = await pollMobilePublishTask(appId, taskId)
      if (!task) throw new Error('移动端发布任务状态获取失败')
      if (task.status === 'completed') return task
      if (task.status === 'failed') throw new Error(task.error?.message || task.message || '移动端发布失败')
      await new Promise((resolve) => setTimeout(resolve, 1200))
    }
  }

  const loadMobilePublishStatus = async (appId: string) => {
    const state = ensureMobilePublishState(appId)
    try {
      const data = await fetchMobilePublishStatus(appId)
      state.last_status = data
      state.last_result = data.last_result || state.last_result
      state.active_task = data.active_task || null
      state.error = data.last_error || null
      if (data.active_task?.id && ['pending', 'running'].includes(data.active_task.status)) {
        startMobilePublishPolling(appId, data.active_task.id)
      } else {
        stopMobilePublishPolling(appId)
      }
    } catch (err: unknown) {
      logger.error('Failed to load mobile publish status:', err)
      state.error = err instanceof Error ? err.message : 'Failed to load mobile publish status'
    }
    return state
  }

  const publishMobileApp = async (appId: string, payload: MobilePublishPayload) => {
    const state = ensureMobilePublishState(appId)
    state.loading = true
    state.error = null
    try {
      const task = await publishMobilePlugin(appId, payload)
      state.active_task = task
      if (task.id) {
        startMobilePublishPolling(appId, task.id)
      }
      const completedTask = await waitForMobilePublishTask(appId, task.id)
      const data = completedTask.result
      if (!data) {
        throw new Error(completedTask.error?.message || completedTask.message || '移动端发布失败')
      }
      state.last_result = data
      await ctx.runtimeActions.refreshInstalledApp(appId)
      await loadMobilePublishStatus(appId)
      return data
    } catch (err: unknown) {
      const normalized = normalizeMobilePublishError(err)
      logger.error('mobile_publish_failed', {
        pluginId: appId,
        version: payload.version || null,
        ...normalized.logContext,
      })
      state.error = normalized.message || 'Failed to publish mobile plugin'
      throw err
    } finally {
      state.loading = false
    }
  }

  const refreshMobileSharePayload = async (appId: string, accessToken: string) => {
    const state = ensureMobilePublishState(appId)
    state.loading = true
    state.error = null
    try {
      const result = await refreshMobileShare(appId, accessToken)
      state.last_result = result
      if (state.last_status) {
        state.last_status.last_result = result
        state.last_status.last_status = 'completed'
      }
      return result
    } catch (err: unknown) {
      const normalized = normalizeMobilePublishError(err)
      logger.error('mobile_publish_refresh_share_failed', {
        pluginId: appId,
        ...normalized.logContext,
      })
      state.error = normalized.message || 'Failed to refresh mobile share payload'
      throw err
    } finally {
      state.loading = false
    }
  }

  return {
    ensureMobilePublishState,
    getMobilePublishState,
    stopMobilePublishPolling,
    pollMobilePublishTask,
    startMobilePublishPolling,
    waitForMobilePublishTask,
    loadMobilePublishStatus,
    publishMobileApp,
    refreshMobileSharePayload,
  }
}
