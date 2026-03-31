import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useRuntimeSessionGuard } from '@/features/plugin-runtime/composables/useRuntimeSessionGuard'
import type { RuntimeFacade } from '@/features/plugin-runtime/services/runtimeFacade'
import type { Plugin, PluginRunMode } from '@/features/plugin/types'

const createFacade = (app: Plugin | null): RuntimeFacade => {
  const activeApp = ref<Plugin | null>(app)
  const activeMode = ref<PluginRunMode>('normal')
  const installedApps = ref<Plugin[]>(app ? [app] : [])

  return {
    activeApp,
    activeMode,
    installedApps,
    loadApps: vi.fn(async () => {}),
    openApp: vi.fn((next) => {
      activeApp.value = next
    }),
    closeApp: vi.fn(),
    startPreview: vi.fn(async () => true),
    startAppWithMode: vi.fn(async () => true),
    stopPreview: vi.fn(async () => {}),
    stopApp: vi.fn(async () => {}),
  }
}

describe('useRuntimeSessionGuard', () => {
  it('preview 模式下会启动预览会话', async () => {
    const redirectToAppsInstalled = vi.fn()
    const facade = createFacade({
      id: 'demo.preview',
      name: 'Preview App',
      state: 'stopped',
      preview: { state: 'stopped' },
    } as Plugin)
    const pluginId = computed(() => 'demo.preview')
    const runMode = computed(() => 'preview' as const)

    const guard = useRuntimeSessionGuard(
      { pluginId, runMode, redirectToAppsInstalled },
      facade
    )

    await guard.ensurePluginRunning()

    expect(facade.openApp).toHaveBeenCalled()
    expect(facade.startPreview).toHaveBeenCalledWith('demo.preview')
    expect(redirectToAppsInstalled).not.toHaveBeenCalled()
  })

  it('找不到插件时会执行回退', async () => {
    const redirectToAppsInstalled = vi.fn()
    const facade = createFacade(null)
    const pluginId = computed(() => 'missing.plugin')
    const runMode = computed(() => 'normal' as const)

    const guard = useRuntimeSessionGuard(
      { pluginId, runMode, redirectToAppsInstalled },
      facade
    )

    await guard.ensurePluginRunning()

    expect(redirectToAppsInstalled).toHaveBeenCalled()
  })
})
