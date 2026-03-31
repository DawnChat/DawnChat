import { computed, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMobilePublishFlow } from '@/features/plugin-dev-workbench/composables/useMobilePublishFlow'
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
    publishWebApp: vi.fn(),
    publishMobileApp: vi.fn(async () => ({ id: 'task-m-1' })),
    refreshMobileSharePayload: vi.fn(async () => {}),
  }
}

describe('useMobilePublishFlow', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('打开离线发布弹窗时加载移动发布状态', () => {
    const facade = createFacade()
    const flow = useMobilePublishFlow({
      pluginId: computed(() => 'com.test.mobile'),
      activeApp: ref<Plugin | null>({ id: 'com.test.mobile', name: 'Mobile Demo' } as Plugin),
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
      showToast: vi.fn(),
    })

    flow.openMobileOfflinePlaceholder()

    expect(flow.mobileOfflineDialogVisible.value).toBe(true)
    expect(facade.loadMobilePublishStatus).toHaveBeenCalledWith('com.test.mobile')
  })

  it('没有 session 时移动发布会设置错误', async () => {
    const facade = createFacade()
    const flow = useMobilePublishFlow({
      pluginId: computed(() => 'com.test.mobile'),
      activeApp: ref<Plugin | null>({ id: 'com.test.mobile', name: 'Mobile Demo' } as Plugin),
      facade,
      getSession: vi.fn(async () => null),
      t: ref({
        apps: {
          publishMissingSession: 'missing session',
          publishSuccess: 'ok {url}',
          publishFailed: 'fail {error}',
        },
        common: { unknown: 'unknown' },
      }),
      showToast: vi.fn(),
    })

    await flow.handleMobilePublish({ version: '1.0.0' })

    expect(flow.mobileQrError.value).toBe('missing session')
  })

  it('打开二维码弹窗时读取分享地址', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        share_url: 'https://share.mobile/app',
        lan_ip: '192.168.1.5',
      }),
    })))

    const facade = createFacade()
    const flow = useMobilePublishFlow({
      pluginId: computed(() => 'com.test.mobile'),
      activeApp: ref<Plugin | null>({ id: 'com.test.mobile', name: 'Mobile Demo' } as Plugin),
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
      showToast: vi.fn(),
    })

    await flow.openMobilePreviewQr()

    expect(flow.mobileQrDialogVisible.value).toBe(true)
    expect(flow.mobileShareUrl.value).toBe('https://share.mobile/app')
    expect(flow.mobileLanIp.value).toBe('192.168.1.5')
    expect(flow.mobileQrLoading.value).toBe(false)
  })
})
