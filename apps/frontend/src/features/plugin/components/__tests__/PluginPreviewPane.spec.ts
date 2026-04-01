import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import PluginPreviewPane from '../PluginPreviewPane.vue'
import { logger } from '../../../../utils/logger'

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: ref({
      common: {
        refresh: '刷新',
        retry: '重试'
      },
      apps: {
        stop: '停止',
        starting: '启动中'
      }
    })
  })
}))

vi.mock('@/composables/usePluginUiBridge', () => ({
  usePluginUiBridge: () => {}
}))

vi.mock('@/features/plugin/composables/usePluginHostStyleBridge', () => ({
  usePluginHostStyleBridge: () => ({
    notifyIframeLoaded: () => {},
    syncHostStyles: () => {}
  })
}))

vi.mock('@/utils/backendUrl', () => ({
  buildBackendUrl: (path = '') => path
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    warn: vi.fn(),
    info: vi.fn()
  }
}))

describe('PluginPreviewPane', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(window, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ success: true })
    } as Response)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('转发 preview iframe 的插件日志到插件日志 API', async () => {
    mount(PluginPreviewPane, {
      props: {
        pluginId: 'com.dawnchat.preview-log',
        pluginUrl: 'http://127.0.0.1:17961/',
        logSessionId: 'preview-session-1'
      }
    })

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'http://127.0.0.1:17961',
        data: {
          type: 'DAWNCHAT_PLUGIN_LOG_BATCH',
          pluginId: 'com.dawnchat.preview-log',
          logs: [{ level: 'ERROR', message: 'boom' }]
        }
      })
    )
    await vi.advanceTimersByTimeAsync(350)

    expect(window.fetch).toHaveBeenCalledWith(
      '/api/plugins/com.dawnchat.preview-log/logs/ingest',
      expect.objectContaining({
        method: 'POST'
      })
    )
    const options = vi.mocked(window.fetch).mock.calls[0]?.[1] as RequestInit
    const payload = JSON.parse(String(options.body || '{}'))
    expect(payload.session_id).toBe('preview-session-1')
  })

  it('忽略 origin 不匹配的日志消息', async () => {
    mount(PluginPreviewPane, {
      props: {
        pluginId: 'com.dawnchat.preview-log',
        pluginUrl: 'http://127.0.0.1:17961/'
      }
    })

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'http://malicious.example',
        data: {
          type: 'DAWNCHAT_PLUGIN_LOG_BATCH',
          pluginId: 'com.dawnchat.preview-log',
          logs: [{ level: 'ERROR', message: 'boom' }]
        }
      })
    )
    await vi.advanceTimersByTimeAsync(350)

    expect(window.fetch).not.toHaveBeenCalled()
  })

  it('当日志上报接口返回非 2xx 时记录告警', async () => {
    vi.mocked(window.fetch).mockResolvedValueOnce({
      ok: false,
      status: 500,
      text: async () => 'internal error'
    } as Response)

    mount(PluginPreviewPane, {
      props: {
        pluginId: 'com.dawnchat.preview-log',
        pluginUrl: 'http://127.0.0.1:17961/'
      }
    })

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'http://127.0.0.1:17961',
        data: {
          type: 'DAWNCHAT_PLUGIN_LOG_BATCH',
          pluginId: 'com.dawnchat.preview-log',
          logs: [{ level: 'ERROR', message: 'boom' }]
        }
      })
    )
    await vi.advanceTimersByTimeAsync(350)
    expect(logger.warn).toHaveBeenCalledWith(
      'plugin_preview_log_flush_failed',
      expect.objectContaining({
        pluginId: 'com.dawnchat.preview-log'
      })
    )
  })

  it('点击右侧全屏图标时触发 toggleFullscreen 事件', async () => {
    const wrapper = mount(PluginPreviewPane, {
      props: {
        pluginId: 'com.dawnchat.preview-log',
        pluginUrl: 'http://127.0.0.1:17961/'
      }
    })
    const fullscreenButton = wrapper.find('.preview-toolbar .fullscreen-icon-btn')
    expect(fullscreenButton.exists()).toBe(true)
    await fullscreenButton.trigger('click')
    expect(wrapper.emitted('toggleFullscreen')?.length).toBe(1)
  })

  it('根据 compact 状态切换全屏按钮文案语义', () => {
    const enterWrapper = mount(PluginPreviewPane, {
      props: {
        pluginId: 'com.dawnchat.preview-log',
        pluginUrl: 'http://127.0.0.1:17961/'
      }
    })
    const enterButton = enterWrapper.find('.preview-toolbar .fullscreen-icon-btn')
    expect(enterButton.attributes('title')).toBe('全屏')

    const exitWrapper = mount(PluginPreviewPane, {
      props: {
        pluginId: 'com.dawnchat.preview-log',
        pluginUrl: 'http://127.0.0.1:17961/',
        isCompactSurface: true
      }
    })
    const exitButton = exitWrapper.find('.preview-toolbar .fullscreen-icon-btn')
    expect(exitButton.attributes('title')).toBe('退出全屏')
  })

  it('compact 模式渲染顶部悬停唤出热区', () => {
    const wrapper = mount(PluginPreviewPane, {
      props: {
        pluginId: 'com.dawnchat.preview-log',
        pluginUrl: 'http://127.0.0.1:17961/',
        isCompactSurface: true
      }
    })
    expect(wrapper.find('.preview-pane').classes()).toContain('compact-surface')
    expect(wrapper.find('.toolbar-reveal-hotzone').exists()).toBe(true)
  })
})
