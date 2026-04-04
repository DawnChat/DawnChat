import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'
import { openPluginRuntimeSurface } from '@/app/router/pluginSurfaceNavigation'

const webviewWindowMocks = vi.hoisted(() => {
  const getByLabel = vi.fn()
  const constructor = vi.fn(function WebviewWindowMockConstructor() {
    return {
      once: vi.fn(),
      show: vi.fn().mockResolvedValue(undefined),
      setFocus: vi.fn().mockResolvedValue(undefined),
    }
  })
  const existingWindow = {
    show: vi.fn().mockResolvedValue(undefined),
    setFocus: vi.fn().mockResolvedValue(undefined),
  }
  return { getByLabel, constructor, existingWindow }
})

vi.mock('@tauri-apps/api/webviewWindow', () => {
  const WebviewWindow = webviewWindowMocks.constructor as unknown as {
    new (...args: unknown[]): unknown
    getByLabel: typeof webviewWindowMocks.getByLabel
  }
  WebviewWindow.getByLabel = webviewWindowMocks.getByLabel
  return { WebviewWindow }
})

const createRouterMock = () => {
  const push = vi.fn()
  return {
    push
  } as unknown as Router & { push: ReturnType<typeof vi.fn> }
}

const setTauriRuntime = (enabled: boolean) => {
  if (enabled) {
    ;(window as Window & { __TAURI_INTERNALS__?: { invoke: () => Promise<string> } }).__TAURI_INTERNALS__ = {
      invoke: async () => '',
    }
    return
  }
  delete (window as Window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__
}

describe('plugin runtime surface navigation', () => {
  afterEach(() => {
    setTauriRuntime(false)
    localStorage.removeItem('dawnchat.plugin.runtime.surface.mode')
    webviewWindowMocks.getByLabel.mockReset()
    webviewWindowMocks.constructor.mockClear()
    webviewWindowMocks.existingWindow.show.mockClear()
    webviewWindowMocks.existingWindow.setFocus.mockClear()
  })

  it('falls back to embedded route in non-tauri runtime', async () => {
    localStorage.setItem('dawnchat.plugin.runtime.surface.mode', 'windowed')
    const router = createRouterMock()

    await openPluginRuntimeSurface(router, 'com.demo.plugin', '/app/apps/installed', 'normal')

    expect(router.push).toHaveBeenCalledWith({
      name: 'plugin-fullscreen',
      params: { pluginId: 'com.demo.plugin' },
      query: { from: '/app/apps/installed', mode: 'normal' }
    })
    expect(webviewWindowMocks.constructor).not.toHaveBeenCalled()
  })

  it('reuses existing runtime window when windowed mode enabled', async () => {
    setTauriRuntime(true)
    localStorage.setItem('dawnchat.plugin.runtime.surface.mode', 'windowed')
    webviewWindowMocks.getByLabel.mockReturnValue(webviewWindowMocks.existingWindow)
    const router = createRouterMock()

    await openPluginRuntimeSurface(router, 'com.demo.plugin', '/app/apps/installed', 'normal')

    expect(webviewWindowMocks.getByLabel).toHaveBeenCalledWith('plugin_runtime__com_demo_plugin')
    expect(webviewWindowMocks.existingWindow.show).toHaveBeenCalledTimes(1)
    expect(webviewWindowMocks.existingWindow.setFocus).toHaveBeenCalledTimes(1)
    expect(router.push).not.toHaveBeenCalled()
    expect(webviewWindowMocks.constructor).not.toHaveBeenCalled()
  })

  it('creates runtime window when absent in windowed mode', async () => {
    setTauriRuntime(true)
    localStorage.setItem('dawnchat.plugin.runtime.surface.mode', 'windowed')
    webviewWindowMocks.getByLabel.mockReturnValue(null)
    const router = createRouterMock()

    await openPluginRuntimeSurface(router, 'com.demo.plugin', '/app/apps/installed', 'preview')

    expect(webviewWindowMocks.constructor).toHaveBeenCalledTimes(1)
    expect(webviewWindowMocks.constructor).toHaveBeenCalledWith(
      'plugin_runtime__com_demo_plugin',
      expect.objectContaining({
        url: '/#/fullscreen/plugin/com.demo.plugin?from=%2Fapp%2Fapps%2Finstalled&mode=preview'
      })
    )
    expect(router.push).not.toHaveBeenCalled()
  })
})
