import { computed, onMounted, onUnmounted, watch } from 'vue'
import type { Ref } from 'vue'

interface UsePluginHostStyleBridgeOptions {
  pluginId: Ref<string>
  pluginUrl: Ref<string>
  expectedOrigin: Ref<string>
  iframeRef: Ref<HTMLIFrameElement | null>
}

interface HostStyleEventPayload {
  type?: string
  pluginId?: string
}

const HOST_STYLE_TOKEN_KEYS = [
  '--color-scrollbar-track',
  '--color-scrollbar-thumb',
  '--color-scrollbar-thumb-hover',
] as const

const HOST_STYLE_PREFIX = 'DAWNCHAT_HOST_STYLE_'

export function usePluginHostStyleBridge(options: UsePluginHostStyleBridgeOptions) {
  const hostStyleTokens = computed<Record<string, string>>(() => {
    if (typeof window === 'undefined') return {}
    const rootStyle = window.getComputedStyle(document.documentElement)
    const tokenEntries = HOST_STYLE_TOKEN_KEYS.map((key) => [key, String(rootStyle.getPropertyValue(key) || '').trim()] as const)
      .filter(([, value]) => Boolean(value))
    return Object.fromEntries(tokenEntries)
  })

  const postToIframe = (type: string, extraPayload: Record<string, unknown> = {}) => {
    const frame = options.iframeRef.value?.contentWindow
    if (!frame) return
    frame.postMessage(
      {
        type,
        pluginId: options.pluginId.value,
        ts: Date.now(),
        ...extraPayload,
      },
      '*'
    )
  }

  const syncHostStyles = () => {
    if (!options.pluginUrl.value) return
    postToIframe(`${HOST_STYLE_PREFIX}SYNC`, {
      tokens: hostStyleTokens.value,
    })
  }

  const notifyIframeLoaded = () => {
    postToIframe(`${HOST_STYLE_PREFIX}PING`)
    syncHostStyles()
  }

  const handleMessage = (event: MessageEvent<HostStyleEventPayload>) => {
    if (!event.data || typeof event.data !== 'object') return
    if (options.expectedOrigin.value && event.origin !== options.expectedOrigin.value) return
    const payload = event.data
    const eventType = String(payload.type || '')
    if (eventType !== `${HOST_STYLE_PREFIX}READY`) return
    if (payload.pluginId && payload.pluginId !== options.pluginId.value) return
    syncHostStyles()
  }

  watch(
    () => options.pluginUrl.value,
    () => {
      syncHostStyles()
    }
  )

  onMounted(() => {
    window.addEventListener('message', handleMessage)
  })

  onUnmounted(() => {
    window.removeEventListener('message', handleMessage)
  })

  return {
    notifyIframeLoaded,
    syncHostStyles,
  }
}
