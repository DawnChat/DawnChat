import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { usePluginHostStyleBridge } from '../usePluginHostStyleBridge'

describe('usePluginHostStyleBridge', () => {
  beforeEach(() => {
    document.documentElement.style.setProperty('--color-scrollbar-track', '#111111')
    document.documentElement.style.setProperty('--color-scrollbar-thumb', '#222222')
    document.documentElement.style.setProperty('--color-scrollbar-thumb-hover', '#333333')
  })

  afterEach(() => {
    document.documentElement.style.removeProperty('--color-scrollbar-track')
    document.documentElement.style.removeProperty('--color-scrollbar-thumb')
    document.documentElement.style.removeProperty('--color-scrollbar-thumb-hover')
  })

  it('在 iframe load 时发送样式同步消息', async () => {
    const postMessage = vi.fn()
    let notifyIframeLoaded: () => void = () => {}
    mount(
      defineComponent({
        setup() {
          const pluginId = ref('plugin.demo')
          const pluginUrl = ref('http://plugin.local/')
          const expectedOrigin = ref('http://plugin.local')
          const iframeRef = ref({
            contentWindow: {
              postMessage,
            },
          } as unknown as HTMLIFrameElement)
          const bridge = usePluginHostStyleBridge({
            pluginId,
            pluginUrl,
            expectedOrigin,
            iframeRef,
          })
          notifyIframeLoaded = bridge.notifyIframeLoaded
          return () => null
        },
      })
    )

    notifyIframeLoaded()

    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'DAWNCHAT_HOST_STYLE_PING',
        pluginId: 'plugin.demo',
      }),
      '*'
    )
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'DAWNCHAT_HOST_STYLE_SYNC',
        pluginId: 'plugin.demo',
        tokens: {
          '--color-scrollbar-track': '#111111',
          '--color-scrollbar-thumb': '#222222',
          '--color-scrollbar-thumb-hover': '#333333',
        },
      }),
      '*'
    )
  })

  it('收到 READY 消息后再次发送样式同步', async () => {
    const postMessage = vi.fn()
    mount(
      defineComponent({
        setup() {
          const pluginId = ref('plugin.demo')
          const pluginUrl = ref('http://plugin.local/')
          const expectedOrigin = ref('http://plugin.local')
          const iframeRef = ref({
            contentWindow: {
              postMessage,
            },
          } as unknown as HTMLIFrameElement)
          usePluginHostStyleBridge({
            pluginId,
            pluginUrl,
            expectedOrigin,
            iframeRef,
          })
          return () => null
        },
      })
    )

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'http://plugin.local',
        data: {
          type: 'DAWNCHAT_HOST_STYLE_READY',
          pluginId: 'plugin.demo',
        },
      })
    )

    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'DAWNCHAT_HOST_STYLE_SYNC',
        pluginId: 'plugin.demo',
      }),
      '*'
    )
  })
})
