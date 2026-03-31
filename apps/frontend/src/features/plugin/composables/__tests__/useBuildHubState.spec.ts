import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'

const {
  installedApps,
  filteredMarketApps,
  loading,
  marketLoading,
  buildHubFilter,
  routeRef,
  routerReplace,
  hydrateBuildHubRecentSession,
  startStatusPolling,
  stopStatusPolling,
  startPolling,
  stopPolling,
  loadApps,
  loadMarketApps,
  setBuildHubFilter,
  getInstallProgress,
  isPreviewStarting,
} = vi.hoisted(() => ({
  installedApps: { value: [] as unknown[] },
  filteredMarketApps: { value: [] as unknown[] },
  loading: { value: false },
  marketLoading: { value: false },
  buildHubFilter: { value: 'all' as 'all' | 'recent' | 'installed' | 'market' },
  routeRef: { value: {
    params: { section: 'hub' },
    query: {},
  } },
  routerReplace: vi.fn(),
  hydrateBuildHubRecentSession: vi.fn(),
  startStatusPolling: vi.fn(),
  stopStatusPolling: vi.fn(),
  startPolling: vi.fn(),
  stopPolling: vi.fn(),
  loadApps: vi.fn(async () => {}),
  loadMarketApps: vi.fn(async () => {}),
  setBuildHubFilter: vi.fn(),
  getInstallProgress: vi.fn(),
  isPreviewStarting: vi.fn(() => false),
}))

vi.mock('pinia', () => ({
  storeToRefs: () => ({
    installedApps,
    filteredMarketApps,
    loading,
    marketLoading,
    buildHubFilter,
  }),
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeRef.value,
  useRouter: () => ({
    replace: routerReplace,
  }),
}))

vi.mock('@/features/plugin/store', () => ({
  usePluginStore: () => ({
    hydrateBuildHubRecentSession,
    startStatusPolling,
    stopStatusPolling,
    startPolling,
    stopPolling,
    loadApps,
    loadMarketApps,
    setBuildHubFilter,
    getInstallProgress,
    isPreviewStarting,
  }),
}))

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: { value: {
      apps: {
        executionStatusInstalling: '安装中',
        executionStatusPreviewable: '可预览',
        executionStatusPublishable: '可发布',
        executionStatusReady: '就绪',
      },
    } },
  }),
}))

import { useBuildHubState } from '@/features/plugin/composables/useBuildHubState'

const TestHarness = defineComponent({
  setup() {
    useBuildHubState()
    return () => null
  },
})

describe('useBuildHubState polling orchestration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    buildHubFilter.value = 'all'
    routeRef.value = {
      params: { section: 'hub' },
      query: {},
    }
  })

  it('挂载时仅启用 status polling 并同步加载', async () => {
    mount(TestHarness)
    await Promise.resolve()

    expect(hydrateBuildHubRecentSession).toHaveBeenCalledTimes(1)
    expect(startStatusPolling).toHaveBeenCalledTimes(1)
    expect(loadApps).toHaveBeenCalledTimes(1)
    expect(loadMarketApps).toHaveBeenCalledTimes(1)
    expect(startPolling).not.toHaveBeenCalled()
  })

  it('卸载时仅停止 status polling', async () => {
    const wrapper = mount(TestHarness)
    await Promise.resolve()
    wrapper.unmount()

    expect(stopStatusPolling).toHaveBeenCalledTimes(1)
    expect(stopPolling).not.toHaveBeenCalled()
  })
})
