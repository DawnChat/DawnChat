import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { shallowMount } from '@vue/test-utils'

const routeRef = ref({
  params: { pluginId: 'com.test.runtime' },
  query: { mode: 'preview', from: '/app/apps' },
})
const routerReplace = vi.fn()
const activeAppRef = ref<any>(null)
const activeModeRef = ref<'normal' | 'preview'>('normal')
const installedAppsRef = ref<any[]>([])

const pluginStoreMock = {
  loadApps: vi.fn(async () => {}),
  openApp: vi.fn((app: any) => {
    activeAppRef.value = app
  }),
  closeApp: vi.fn(),
  startPreview: vi.fn(async () => true),
  startAppWithMode: vi.fn(async () => true),
  stopPreview: vi.fn(async () => {}),
  stopApp: vi.fn(async () => {}),
}

vi.mock('pinia', async () => {
  const actual = await vi.importActual<typeof import('pinia')>('pinia')
  return {
    ...actual,
    storeToRefs: () => ({
      activeApp: activeAppRef,
      activeMode: activeModeRef,
      installedApps: installedAppsRef,
    }),
  }
})

vi.mock('vue-router', () => ({
  useRoute: () => routeRef.value,
  useRouter: () => ({
    replace: routerReplace,
  }),
}))

vi.mock('@/stores/plugin', () => ({
  usePluginStore: () => pluginStoreMock,
}))

vi.mock('@/composables/useTheme', () => ({
  useTheme: () => ({ theme: ref('dark') }),
}))

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: ref({ apps: { starting: '启动中' } }),
    locale: ref('zh-CN'),
  }),
}))

vi.mock('@/app/router/deepLink', () => ({
  resolveFullscreenBackTarget: () => '/app/apps',
}))

import PluginRuntimeFullscreenPage from '@/features/plugin-runtime/views/PluginRuntimeFullscreenPage.vue'

describe('PluginRuntimeFullscreenPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    activeAppRef.value = null
    activeModeRef.value = 'normal'
    installedAppsRef.value = [
      {
        id: 'com.test.runtime',
        name: 'Runtime App',
        state: 'stopped',
        preview: { state: 'stopped', url: '' },
        runtime: { gradio_url: 'http://127.0.0.1:7860' },
      },
    ]
    routeRef.value = {
      params: { pluginId: 'com.test.runtime' },
      query: { mode: 'preview', from: '/app/apps' },
    }
  })

  it('preview 模式会尝试启动 preview 会话', async () => {
    shallowMount(PluginRuntimeFullscreenPage, {
      global: {
        stubs: {
          ActiveAppFrame: true,
        },
      },
    })
    await vi.waitFor(() => {
      expect(pluginStoreMock.loadApps).toHaveBeenCalled()
      expect(pluginStoreMock.startPreview).toHaveBeenCalledWith('com.test.runtime')
    })
    expect(pluginStoreMock.startAppWithMode).not.toHaveBeenCalled()
  })

  it('normal 模式启动失败会回退到 apps', async () => {
    routeRef.value = {
      params: { pluginId: 'com.test.runtime' },
      query: { mode: 'normal', from: '/app/apps' },
    }
    pluginStoreMock.startAppWithMode.mockResolvedValueOnce(false)

    shallowMount(PluginRuntimeFullscreenPage, {
      global: {
        stubs: {
          ActiveAppFrame: true,
        },
      },
    })
    await vi.waitFor(() => {
      expect(pluginStoreMock.startAppWithMode).toHaveBeenCalledWith('com.test.runtime', 'normal')
      expect(routerReplace).toHaveBeenCalledWith('/app/apps')
    })
  })
})
