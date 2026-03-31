import { describe, expect, it, vi, beforeEach } from 'vitest'

const runLifecycleOperation = vi.fn()

vi.mock('@/features/plugin/store', () => ({
  usePluginStore: () => ({
    runLifecycleOperation,
  }),
}))

import { useBuildHubLifecycleFacade } from '@/features/plugin/services/buildHubLifecycleFacade'

describe('useBuildHubLifecycleFacade', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    runLifecycleOperation.mockResolvedValue({
      task_id: 'task-1',
      operation_type: 'start_dev_session',
      plugin_id: 'com.test.app',
      app_type: 'web',
      status: 'completed',
      created_at: '',
      updated_at: '',
      elapsed_seconds: 0,
      progress: {
        stage: 'done',
        stage_label: '完成',
        progress: 100,
        message: 'done',
      },
      result: null,
      error: null,
    })
  })

  it('createDevSession 使用统一 lifecycle 导航参数', async () => {
    const facade = useBuildHubLifecycleFacade()
    await facade.createDevSession({
      template_id: 'template.web',
      app_type: 'web',
      name: 'test app',
      plugin_id: 'com.test.app',
      description: '',
      owner_email: 'test@example.com',
      owner_user_id: 'uid-1',
    })

    expect(runLifecycleOperation).toHaveBeenCalledWith({
      operationType: 'create_dev_session',
      payload: {
        template_id: 'template.web',
        app_type: 'web',
        name: 'test app',
        plugin_id: 'com.test.app',
        description: '',
        owner_email: 'test@example.com',
        owner_user_id: 'uid-1',
      },
      navigationIntent: 'workbench',
      from: '/app/apps/hub',
      uiMode: 'modal',
      completionMessage: '启动完成，打开中...',
    })
  })

  it('startDevSession 使用统一 lifecycle 导航参数', async () => {
    const facade = useBuildHubLifecycleFacade()
    await facade.startDevSession('com.test.app')

    expect(runLifecycleOperation).toHaveBeenCalledWith({
      operationType: 'start_dev_session',
      payload: { plugin_id: 'com.test.app' },
      navigationIntent: 'workbench',
      from: '/app/apps/hub',
      uiMode: 'modal',
      completionMessage: '启动完成，打开中...',
    })
  })
})
