import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useWebPublishFlow } from '@/features/plugin-dev-workbench/composables/useWebPublishFlow'
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

const createFacade = (): DevWorkbenchFacade => {
  return {
    activeApp: ref<Plugin | null>(null),
    activeMode: ref<PluginRunMode>('preview'),
    installedApps: ref<Plugin[]>([]),
    activeLifecycleTask: ref<LifecycleTask | null>(null),
    loadApps: vi.fn(async () => {}),
    openApp: vi.fn(),
    closeApp: vi.fn(),
    stopPreview: vi.fn(async () => true),
    refreshPreviewStatus: vi.fn(async () => {}),
    retryPreviewInstall: vi.fn(async () => true),
    runLifecycleOperation: vi.fn(async () => ({ task_id: 'task-1' } as LifecycleTask)),
    rememberBuildHubRecentSession: vi.fn(),
    getPublishState: vi.fn(() => createPublishState()),
    getMobilePublishState: vi.fn(() => createMobilePublishState()),
    loadPublishStatus: vi.fn(async () => createPublishState()),
    loadMobilePublishStatus: vi.fn(async () => createMobilePublishState()),
    publishWebApp: vi.fn(async () => ({
      release: { id: 'release-1' },
      runtime_url: 'https://demo.app',
      artifact_count: 1,
    })),
    publishMobileApp: vi.fn(),
    refreshMobileSharePayload: vi.fn(),
  }
}

describe('useWebPublishFlow', () => {
  it('打开发布弹窗时加载发布状态', async () => {
    const facade = createFacade()
    const showToast = vi.fn()
    const flow = useWebPublishFlow({
      pluginId: computed(() => 'com.test.web'),
      activeApp: ref<Plugin | null>({ id: 'com.test.web', name: 'Web Demo' } as Plugin),
      facade,
      getSession: vi.fn(async () => ({ access_token: 'token-1' })),
      t: ref({
        apps: {
          publishMissingSession: 'missing session',
          publishSuccess: 'ok {url}',
          publishFailed: 'fail {error}',
        },
        common: { unknown: 'unknown' },
      }),
      showToast,
    })

    await flow.openPublishDialog()

    expect(flow.publishDialogVisible.value).toBe(true)
    expect(facade.loadPublishStatus).toHaveBeenCalledWith('com.test.web', 'token-1')
  })

  it('发布成功时弹成功提示', async () => {
    const facade = createFacade()
    const showToast = vi.fn()
    const flow = useWebPublishFlow({
      pluginId: computed(() => 'com.test.web'),
      activeApp: ref<Plugin | null>({ id: 'com.test.web', name: 'Web Demo' } as Plugin),
      facade,
      getSession: vi.fn(async () => ({ access_token: 'token-1', user: { id: 'u-1' } })),
      t: ref({
        apps: {
          publishMissingSession: 'missing session',
          publishSuccess: 'ok {url}',
          publishFailed: 'fail {error}',
        },
        common: { unknown: 'unknown' },
      }),
      showToast,
    })

    await flow.handlePublish({
      slug: 'demo',
      title: 'Demo',
      version: '1.0.0',
      description: 'desc',
      initial_visibility: 'private',
    })

    expect(facade.publishWebApp).toHaveBeenCalled()
    expect(showToast).toHaveBeenCalledWith('ok https://demo.app', 'success')
  })
})
