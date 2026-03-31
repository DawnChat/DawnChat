import { describe, expect, it, vi, beforeEach } from 'vitest'
import { nextTick, ref } from 'vue'

const {
  installedApps,
  loadApps,
  loadMarketApps,
  openApp,
  startPolling,
  stopPolling,
  openPluginFullscreen,
} = vi.hoisted(() => ({
  installedApps: { value: [{ id: 'com.test.app', name: 'Test App' }] as Array<{ id: string; name: string }> },
  loadApps: vi.fn(),
  loadMarketApps: vi.fn(),
  openApp: vi.fn(),
  startPolling: vi.fn(),
  stopPolling: vi.fn(),
  openPluginFullscreen: vi.fn(),
}))

vi.mock('pinia', () => ({
  storeToRefs: () => ({ installedApps }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({}),
}))

vi.mock('@/features/plugin/store', () => ({
  usePluginStore: () => ({
    loadApps,
    loadMarketApps,
    openApp,
    startPolling,
    stopPolling,
  }),
}))

vi.mock('@/app/router/navigation', () => ({
  openPluginFullscreen,
}))

import { useAppsView } from '@/composables/useAppsView'

describe('useAppsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    installedApps.value = [{ id: 'com.test.app', name: 'Test App' }]
  })

  it('根据 section 变化加载 installed/market 数据', async () => {
    const section = ref<string | undefined>('installed')
    useAppsView(section)
    await nextTick()
    expect(loadApps).toHaveBeenCalledTimes(1)
    expect(loadMarketApps).not.toHaveBeenCalled()

    section.value = 'market'
    await nextTick()
    expect(loadMarketApps).toHaveBeenCalledTimes(1)
  })

  it('不再在 composable 内触发全局 start/stop polling', async () => {
    const section = ref<string | undefined>('installed')
    useAppsView(section)
    await nextTick()
    expect(startPolling).not.toHaveBeenCalled()
    expect(stopPolling).not.toHaveBeenCalled()
  })

  it('可从 market 已安装项打开全屏', async () => {
    const section = ref<string | undefined>('installed')
    const { openInstalledFromMarket } = useAppsView(section)
    await openInstalledFromMarket('com.test.app')
    expect(openApp).toHaveBeenCalledWith({ id: 'com.test.app', name: 'Test App' })
    expect(openPluginFullscreen).toHaveBeenCalled()
  })
})
