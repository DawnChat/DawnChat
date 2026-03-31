import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { usePreviewSessionGuard } from '@/features/plugin-dev-workbench/composables/usePreviewSessionGuard'
import type { DevWorkbenchFacade } from '@/features/plugin-dev-workbench/services/devWorkbenchFacade'
import type { Plugin, PluginRunMode } from '@/features/plugin/types'
import type { LifecycleTask, MobilePublishState, WebPublishState } from '@/features/plugin/store'

const createPublishState = (): WebPublishState => ({
  loading: false,
  error: null,
  last_result: null,
  last_status: null,
  active_task: null,
})

const createMobilePublishState = (): MobilePublishState => ({
  loading: false,
  error: null,
  last_result: null,
  last_status: null,
  active_task: null,
})

const createFacade = (app: Plugin | null): DevWorkbenchFacade => {
  const activeApp = ref<Plugin | null>(app)
  const activeMode = ref<PluginRunMode>('preview')
  const installedApps = ref<Plugin[]>(app ? [app] : [])
  const activeLifecycleTask = ref<LifecycleTask | null>(null)

  return {
    activeApp,
    activeMode,
    installedApps,
    activeLifecycleTask,
    loadApps: vi.fn(async () => {}),
    openApp: vi.fn((next) => {
      activeApp.value = next
    }),
    closeApp: vi.fn(),
    stopPreview: vi.fn(async () => true),
    refreshPreviewStatus: vi.fn(async () => {}),
    retryPreviewInstall: vi.fn(async () => true),
    runLifecycleOperation: vi.fn(async () => ({ task_id: 't1', status: 'completed' } as LifecycleTask)),
    rememberBuildHubRecentSession: vi.fn(),
    getPublishState: vi.fn(() => createPublishState()),
    getMobilePublishState: vi.fn(() => createMobilePublishState()),
    loadPublishStatus: vi.fn(async () => createPublishState()),
    loadMobilePublishStatus: vi.fn(async () => createMobilePublishState()),
    publishWebApp: vi.fn(),
    publishMobileApp: vi.fn(),
    refreshMobileSharePayload: vi.fn(),
  }
}

describe('usePreviewSessionGuard', () => {
  it('插件存在且预览未运行时会触发 start_dev_session', async () => {
    const facade = createFacade({
      id: 'com.test.preview',
      name: 'Preview App',
      state: 'stopped',
      preview: { state: 'stopped', url: '' },
    } as Plugin)
    const redirectToAppsInstalled = vi.fn()

    const guard = usePreviewSessionGuard(
      {
        pluginId: computed(() => 'com.test.preview'),
        redirectToAppsInstalled,
      },
      facade
    )

    await guard.ensurePreviewRunning()

    expect(facade.loadApps).toHaveBeenCalled()
    expect(facade.runLifecycleOperation).toHaveBeenCalledWith({
      operationType: 'start_dev_session',
      payload: { plugin_id: 'com.test.preview' },
      navigationIntent: 'none',
      uiMode: 'inline',
      completionMessage: '预览已就绪'
    })
    expect(redirectToAppsInstalled).not.toHaveBeenCalled()
  })

  it('插件不存在时会执行回退', async () => {
    const facade = createFacade(null)
    const redirectToAppsInstalled = vi.fn()
    const guard = usePreviewSessionGuard(
      {
        pluginId: computed(() => 'missing.plugin'),
        redirectToAppsInstalled,
      },
      facade
    )

    await guard.ensurePreviewRunning()

    expect(redirectToAppsInstalled).toHaveBeenCalled()
  })

  it('dist 前端模式下会要求轮询预览状态', () => {
    const facade = createFacade({
      id: 'com.test.preview',
      name: 'Preview App',
      state: 'running',
      preview: {
        state: 'running',
        url: 'http://127.0.0.1:5173',
        frontend_mode: 'dist',
        install_status: 'idle',
      },
    } as Plugin)

    const guard = usePreviewSessionGuard(
      {
        pluginId: computed(() => 'com.test.preview'),
        redirectToAppsInstalled: vi.fn(),
      },
      facade
    )

    expect(guard.shouldPollPreviewStatus.value).toBe(true)
  })
})
