import { API_BASE } from '@/stores/plugin/api/client'
import { logger } from '@/utils/logger'
import type { PluginStoreContext } from '@/stores/plugin/context'
import { APPS_HUB_PATH } from '@/app/router/paths'
import type {
  LifecycleNavigationIntent,
  LifecycleOperationType,
  LifecycleTask,
  LifecycleUiMode,
  RunLifecycleOperationOptions,
} from '@/stores/plugin/types'

interface LifecycleRunOptions {
  navigationIntent: LifecycleNavigationIntent
  from: string
  completionMessage: string
  uiMode: LifecycleUiMode
}

interface RetryLifecycleHandlingOptions {
  from: string
  completionMessage?: string
  uiMode?: LifecycleUiMode
}

export function createLifecycleActions(ctx: PluginStoreContext) {
  const stopLifecyclePolling = (taskId: string) => {
    ctx.state.lifecyclePollers.clear(taskId)
  }

  const clearLifecycleTask = () => {
    if (ctx.state.activeLifecycleTask.value?.task_id) {
      stopLifecyclePolling(ctx.state.activeLifecycleTask.value.task_id)
    }
    ctx.state.activeLifecycleTask.value = null
    ctx.state.lifecycleCompletionMessage.value = ''
  }

  const closeLifecycleModal = () => {
    ctx.state.lifecycleModalVisible.value = false
  }

  const openLifecycleModal = () => {
    ctx.state.lifecycleModalVisible.value = true
  }

  const resetLifecycleHandledState = () => {
    ctx.state.lifecycleLastHandledTaskId.value = ''
    ctx.state.lifecycleCompletionMessage.value = ''
  }

  const fetchLifecycleTask = async (taskId: string): Promise<LifecycleTask | null> => {
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/operations/${encodeURIComponent(taskId)}`)
      if (!res.ok) return null
      const data = await res.json()
      if (data.status === 'success' && data.data) {
        return data.data as LifecycleTask
      }
      return null
    } catch (err) {
      logger.error('Failed to fetch lifecycle task:', err)
      return null
    }
  }

  const pollLifecycleTask = async (taskId: string): Promise<LifecycleTask | null> => {
    const task = await fetchLifecycleTask(taskId)
    if (task) {
      ctx.state.activeLifecycleTask.value = task
      if (task.status === 'completed') {
        stopLifecyclePolling(taskId)
        await ctx.runtimeActions.loadApps(true)
        void ctx.marketActions.loadMarketApps(true).catch((err) => {
          logger.warn('Lifecycle market refresh failed after completion', { taskId, err })
        })
      } else if (task.status === 'failed' || task.status === 'cancelled') {
        stopLifecyclePolling(taskId)
      }
    }
    return task
  }

  const startLifecyclePolling = (taskId: string) => {
    stopLifecyclePolling(taskId)
    void pollLifecycleTask(taskId)
    const timer = setInterval(() => {
      void pollLifecycleTask(taskId)
    }, 1200)
    ctx.state.lifecyclePollers.set(taskId, timer)
  }

  const submitLifecycleOperation = async (
    operationType: LifecycleOperationType,
    payload: Record<string, unknown>,
    options: { showModal?: boolean } = {},
  ) => {
    const endpointMap: Record<LifecycleOperationType, string> = {
      create_dev_session: '/api/plugins/operations/create-dev-session',
      start_dev_session: '/api/plugins/operations/start-dev-session',
      restart_dev_session: '/api/plugins/operations/restart-dev-session',
      start_runtime: '/api/plugins/operations/start-runtime',
    }
    const endpoint = endpointMap[operationType]
    const res = await fetch(`${API_BASE()}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      throw new Error(detail || `submit lifecycle operation failed: ${res.status}`)
    }
    const data = await res.json()
    const taskId = String(data.task_id || '')
    if (!taskId) throw new Error('lifecycle task id missing')
    ctx.state.activeLifecycleTask.value = {
      task_id: taskId,
      operation_type: operationType,
      plugin_id: String(payload.plugin_id || ''),
      app_type: String(payload.app_type || ''),
      status: 'pending',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      elapsed_seconds: 0,
      progress: {
        stage: 'validate_input',
        stage_label: '校验输入',
        progress: 0,
        message: '任务排队中',
      },
      result: null,
      error: null,
    }
    const shouldShowModal = options.showModal ?? true
    ctx.state.lifecycleModalVisible.value = shouldShowModal
    ctx.state.lifecycleCompletionMessage.value = ''
    startLifecyclePolling(taskId)
    return taskId
  }

  const waitForLifecycleTask = async (taskId: string) => {
    while (true) {
      const task = await pollLifecycleTask(taskId)
      if (!task) throw new Error('获取生命周期任务状态失败')
      if (task.status === 'completed') return task
      if (task.status === 'failed') throw new Error(task.error?.message || task.progress?.message || '生命周期任务失败')
      if (task.status === 'cancelled') throw new Error('生命周期任务已取消')
      await new Promise((resolve) => setTimeout(resolve, 1200))
    }
  }

  const cancelLifecycleTask = async (taskId?: string): Promise<boolean> => {
    const id = String(taskId || ctx.state.activeLifecycleTask.value?.task_id || '')
    if (!id) return false
    try {
      const res = await fetch(`${API_BASE()}/api/plugins/operations/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (!res.ok) return false
      await pollLifecycleTask(id)
      return true
    } catch (err) {
      logger.error('Failed to cancel lifecycle task:', err)
      return false
    }
  }

  const retryLifecycleTask = async (): Promise<string | null> => {
    const current = ctx.state.activeLifecycleTask.value
    if (!current || !current.progress?.retryable) return null
    resetLifecycleHandledState()
    if (current.operation_type === 'create_dev_session') return null
    if (current.operation_type === 'start_dev_session') {
      return await submitLifecycleOperation('start_dev_session', { plugin_id: current.plugin_id })
    }
    if (current.operation_type === 'restart_dev_session') {
      return await submitLifecycleOperation('restart_dev_session', { plugin_id: current.plugin_id })
    }
    if (current.operation_type === 'start_runtime') {
      return await submitLifecycleOperation('start_runtime', { plugin_id: current.plugin_id })
    }
    return null
  }

  const performLifecycleNavigation = async (task: LifecycleTask, intent: LifecycleNavigationIntent, from: string) => {
    const pluginId = String(task.result?.plugin_id || task.plugin_id || '')
    if (!pluginId || intent === 'none') return
    if (intent === 'workbench') {
      await ctx.openPluginDevWorkbench(ctx.router, pluginId, from)
      return
    }
    await ctx.openPluginFullscreen(ctx.router, pluginId, from, 'normal')
  }

  const finalizeLifecycleSession = (options: { closeModal?: boolean; clearTask?: boolean; markHandled?: string } = {}) => {
    const { closeModal: shouldCloseModal = true, clearTask: shouldClearTask = true, markHandled = '' } = options
    if (markHandled) {
      ctx.state.lifecycleLastHandledTaskId.value = markHandled
    }
    if (shouldCloseModal) {
      closeLifecycleModal()
    }
    if (shouldClearTask) {
      clearLifecycleTask()
    }
  }

  const handleLifecycleCompletion = async (
    task: LifecycleTask,
    options: LifecycleRunOptions,
  ) => {
    if (ctx.state.lifecycleLastHandledTaskId.value === task.task_id) return
    ctx.state.lifecycleLastHandledTaskId.value = task.task_id
    const completionMessage = options.completionMessage || '启动完成，打开中...'
    ctx.state.lifecycleCompletionMessage.value = completionMessage
    if (ctx.state.activeLifecycleTask.value?.task_id === task.task_id) {
      ctx.state.activeLifecycleTask.value = {
        ...ctx.state.activeLifecycleTask.value,
        progress: {
          ...ctx.state.activeLifecycleTask.value.progress,
          message: completionMessage,
        },
      }
    }
    if (options.navigationIntent === 'none') {
      setTimeout(() => {
        if (ctx.state.activeLifecycleTask.value?.task_id === task.task_id) {
          finalizeLifecycleSession({ closeModal: options.uiMode === 'modal', clearTask: true, markHandled: task.task_id })
        }
      }, 900)
      return
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
    try {
      await performLifecycleNavigation(task, options.navigationIntent, options.from)
    } finally {
      finalizeLifecycleSession({ closeModal: true, clearTask: true, markHandled: task.task_id })
    }
  }

  const runLifecycleOperation = async (options: RunLifecycleOperationOptions) => {
    const uiMode = options.uiMode || 'modal'
    const navigationIntent = options.navigationIntent || 'none'
    const from = options.from || APPS_HUB_PATH
    resetLifecycleHandledState()
    const taskId = await submitLifecycleOperation(options.operationType, options.payload, {
      showModal: uiMode === 'modal',
    })
    const task = await waitForLifecycleTask(taskId)
    if (task.status === 'completed') {
      await handleLifecycleCompletion(task, {
        navigationIntent,
        from,
        completionMessage: options.completionMessage || '启动完成，打开中...',
        uiMode,
      })
    }
    return task
  }

  const retryLifecycleTaskAndHandle = async (options: RetryLifecycleHandlingOptions) => {
    const nextTaskId = await retryLifecycleTask()
    if (!nextTaskId) return null
    const task = await waitForLifecycleTask(nextTaskId)
    if (task.status === 'completed') {
      await handleLifecycleCompletion(task, {
        navigationIntent: task.operation_type === 'start_runtime' ? 'runtime' : 'workbench',
        from: options.from,
        completionMessage: options.completionMessage || '启动完成，打开中...',
        uiMode: options.uiMode || 'modal',
      })
    }
    return task
  }

  const finalizeActiveLifecycleTask = () => {
    const taskId = ctx.state.activeLifecycleTask.value?.task_id || ''
    finalizeLifecycleSession({ closeModal: true, clearTask: true, markHandled: taskId })
  }

  return {
    stopLifecyclePolling,
    clearLifecycleTask,
    closeLifecycleModal,
    openLifecycleModal,
    resetLifecycleHandledState,
    fetchLifecycleTask,
    pollLifecycleTask,
    startLifecyclePolling,
    submitLifecycleOperation,
    waitForLifecycleTask,
    cancelLifecycleTask,
    retryLifecycleTask,
    performLifecycleNavigation,
    finalizeLifecycleSession,
    handleLifecycleCompletion,
    runLifecycleOperation,
    retryLifecycleTaskAndHandle,
    finalizeActiveLifecycleTask,
  }
}
