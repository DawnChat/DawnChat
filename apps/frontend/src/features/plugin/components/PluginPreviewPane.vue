<template>
  <div class="preview-pane">
    <div class="preview-toolbar">
      <button class="tool-btn ui-btn ui-btn--neutral" :class="{ active: inspectorEnabled }" :disabled="isLifecycleBusy" @click="toggleInspector">
        {{ inspectorEnabled ? labels.inspectorDisable : labels.inspectorEnable }}
      </button>
      <button class="tool-btn ui-btn ui-btn--neutral" :disabled="isLifecycleBusy" @click="reloadIframe">{{ t.common.refresh }}</button>
      <button class="tool-btn ui-btn ui-btn--neutral" :disabled="isLifecycleBusy" @click="$emit('toggleFullscreen')">
        {{ isCompactSurface ? labels.exitFullscreen : labels.enterFullscreen }}
      </button>
      <button class="tool-btn ui-btn ui-btn--neutral" :disabled="isLifecycleBusy" @click="$emit('restart', pluginId)">
        {{ labels.restart }}
      </button>
      <button
        v-if="showStopButton"
        class="tool-btn ui-btn ui-btn--neutral danger"
        :disabled="isLifecycleBusy"
        @click="$emit('stop', pluginId)"
      >
        {{ t.apps.stop }}
      </button>
    </div>

    <div v-if="pluginUrl" class="preview-frame-wrap">
      <iframe
        :key="iframeKey"
        ref="iframeRef"
        :src="pluginUrl"
        class="preview-iframe"
        frameborder="0"
        @load="handleIframeLoad"
      ></iframe>
      <div v-if="iframeLoading" class="preview-loading preview-loading-overlay">
        <span>{{ iframeLoadTimedOut ? '预览加载超时，请重试' : t.apps.starting }}</span>
        <button v-if="iframeLoadTimedOut" class="retry-btn" @click="reloadIframe">{{ t.common.retry }}</button>
      </div>
      <div v-if="showInstallOverlay" class="install-overlay">
        <div class="install-overlay-card">
          <div class="install-overlay-title">{{ installOverlayText }}</div>
          <div v-if="installStatus === 'failed' && installErrorMessage" class="install-overlay-sub">
            {{ installErrorMessage }}
          </div>
          <div v-if="!isOnline" class="install-overlay-sub">当前网络不可用，请检查网络后重试。</div>
          <button
            v-if="installStatus === 'failed'"
            class="retry-btn install-retry-btn"
            :disabled="isLifecycleBusy"
            @click="$emit('retryInstall')"
          >
            {{ t.common.retry }}
          </button>
        </div>
      </div>
    </div>

    <div v-else class="preview-loading">
      <span>{{ t.apps.starting }}</span>
    </div>

    <div v-if="lifecycleMessage || statusTip" class="status-tip">
      <div>{{ lifecycleMessage || statusTip }}</div>
      <div v-if="lifecycleEta" class="status-sub">约 {{ lifecycleEta }}s</div>
      <div v-for="item in lifecycleDetails" :key="item" class="status-sub">{{ item }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from '@/composables/useI18n'
import type {
  CapabilityInvokeExecutionContext,
  HostInvokeExecutionContext
} from '@/composables/usePluginUiBridge'
import { usePluginUiBridge } from '@/composables/usePluginUiBridge'
import { usePluginHostStyleBridge } from '@/features/plugin/composables/usePluginHostStyleBridge'
import { buildBackendUrl } from '@/utils/backendUrl'
import { logger } from '@/utils/logger'
import type { InspectorSelectPayload } from '@/types/inspector'
import type {
  ContextPushPayload,
  TtsSpeakAcceptedPayload,
  TtsStoppedPayload
} from '@/services/plugin-ui-bridge/messageProtocol'
import type { LifecycleTask } from '@/features/plugin/store'

interface InspectorEventPayload {
  type?: string
  pluginId?: string
  file?: string
  fileRelative?: string
  range?: {
    start?: { line?: number; column?: number }
    end?: { line?: number; column?: number }
  }
  selector?: string
  textSnippet?: string
  htmlSnippet?: string
  message?: string
  ts?: number
  logs?: PluginRuntimeLogEntry[]
}

interface PluginRuntimeLogEntry {
  level?: string
  message?: string
  data?: unknown
  timestamp?: string
}

const props = withDefaults(defineProps<{
  pluginId: string
  pluginUrl: string
  logSessionId?: string
  lifecycleTask?: LifecycleTask | null
  lifecycleBusy?: boolean
  installStatus?: 'idle' | 'running' | 'success' | 'failed'
  installErrorMessage?: string | null
  showStopButton?: boolean
  isCompactSurface?: boolean
  onCapabilityInvokeRequest?: (
    context: CapabilityInvokeExecutionContext
  ) => Promise<Record<string, unknown> | null> | Record<string, unknown> | null
  onHostInvokeRequest?: (
    context: HostInvokeExecutionContext
  ) => Promise<Record<string, unknown>> | Record<string, unknown>
}>(), {
  showStopButton: true,
  isCompactSurface: false,
})

const emit = defineEmits<{
  stop: [appId: string]
  restart: [appId: string]
  toggleFullscreen: []
  retryInstall: []
  inspectorSelect: [payload: InspectorSelectPayload]
  contextPush: [payload: ContextPushPayload]
  ttsSpeakAccepted: [payload: TtsSpeakAcceptedPayload]
  ttsStopped: [payload: TtsStoppedPayload]
}>()

const { t } = useI18n()
const iframeRef = ref<HTMLIFrameElement | null>(null)
const inspectorEnabled = ref(false)
const inspectorReady = ref(false)
const inspectorAvailable = ref(true)
const iframeKey = ref(0)
const statusTip = ref('')
const isOnline = ref(typeof navigator === 'undefined' ? true : navigator.onLine)
const iframeLoading = ref(true)
const iframeLoadTimedOut = ref(false)
let iframeLoadTimer: ReturnType<typeof setTimeout> | null = null
let logFlushTimer: ReturnType<typeof setTimeout> | null = null
const pendingPluginLogs = ref<PluginRuntimeLogEntry[]>([])
const isLifecycleBusy = computed(() => Boolean(props.lifecycleBusy))
const installStatus = computed(() => String(props.installStatus || 'idle'))
const installLoadingText = computed(() => {
  const apps = (t.value as any).apps || {}
  return String(apps.previewInstallDepsRunning || '正在准备完整开发环境，稍后会自动开启实时更新。')
})
const installFailedText = computed(() => {
  const apps = (t.value as any).apps || {}
  return String(apps.previewInstallDepsFailed || '开发环境准备失败，你可以稍后重试。')
})
const showInstallOverlay = computed(() => {
  return installStatus.value === 'running' || installStatus.value === 'failed'
})
const installOverlayText = computed(() => {
  return installStatus.value === 'failed' ? installFailedText.value : installLoadingText.value
})
const handleOnline = () => {
  isOnline.value = true
}
const handleOffline = () => {
  isOnline.value = false
}
const lifecycleMessage = computed(() => {
  if (!props.lifecycleTask) return ''
  return String(props.lifecycleTask.progress?.message || '')
})
const lifecycleEta = computed(() => props.lifecycleTask?.progress?.eta_seconds || null)
const lifecycleDetails = computed(() => {
  if (installStatus.value === 'failed' && props.installErrorMessage) {
    return [String(props.installErrorMessage)]
  }
  if (!props.lifecycleTask) return []
  return Array.isArray(props.lifecycleTask.progress?.details) ? props.lifecycleTask.progress.details.slice(-3) : []
})

const expectedOrigin = computed(() => {
  if (!props.pluginUrl) return ''
  try {
    return new URL(props.pluginUrl).origin
  } catch {
    return ''
  }
})

const labels = computed(() => {
  const apps = (t.value as any).apps || {}
  return {
    inspectorEnable: String(apps.inspectorEnable || '开启圈选'),
    inspectorDisable: String(apps.inspectorDisable || '关闭圈选'),
    restart: String(apps.restart || '重启'),
    enterFullscreen: String(apps.fullscreenEnter || '全屏'),
    exitFullscreen: String(apps.fullscreenExit || '退出全屏'),
    inspectorEnabledTip: String(apps.inspectorEnabledTip || '圈选模式已开启'),
    inspectorDisabledTip: String(apps.inspectorDisabledTip || '圈选模式已关闭'),
    inspectorUnsupported: String(apps.inspectorUnsupported || '当前元素无法定位源码')
  }
})

const postInspectorCommand = (type: string) => {
  const frame = iframeRef.value?.contentWindow
  if (!frame) return
  frame.postMessage(
    {
      type,
      pluginId: props.pluginId,
      ts: Date.now()
    },
    '*'
  )
}

const applyInspectorState = () => {
  if (!inspectorReady.value) return
  postInspectorCommand(inspectorEnabled.value ? 'DAWNCHAT_INSPECTOR_ENABLE' : 'DAWNCHAT_INSPECTOR_DISABLE')
}

const toggleInspector = () => {
  if (!inspectorAvailable.value) {
    statusTip.value = labels.value.inspectorUnsupported
    return
  }
  inspectorEnabled.value = !inspectorEnabled.value
  statusTip.value = inspectorEnabled.value ? labels.value.inspectorEnabledTip : labels.value.inspectorDisabledTip
  applyInspectorState()
}

const reloadIframe = () => {
  inspectorReady.value = false
  setIframeLoadingGuard()
  iframeKey.value += 1
}

const clearIframeTimer = () => {
  if (iframeLoadTimer) {
    clearTimeout(iframeLoadTimer)
    iframeLoadTimer = null
  }
}

const setIframeLoadingGuard = () => {
  clearIframeTimer()
  iframeLoading.value = true
  iframeLoadTimedOut.value = false
  iframeLoadTimer = setTimeout(() => {
    iframeLoadTimedOut.value = true
  }, 15000)
}

const buildSelectPayload = (payload: InspectorEventPayload): InspectorSelectPayload | null => {
  if (!payload.file || !payload.range?.start?.line || !payload.range?.start?.column) {
    return null
  }
  return {
    type: 'DAWNCHAT_INSPECTOR_SELECT',
    pluginId: props.pluginId,
    file: payload.file,
    fileRelative: payload.fileRelative,
    range: {
      start: {
        line: Number(payload.range.start.line),
        column: Number(payload.range.start.column)
      },
      end:
        payload.range.end?.line && payload.range.end?.column
          ? {
              line: Number(payload.range.end.line),
              column: Number(payload.range.end.column)
            }
          : undefined
    },
    selector: payload.selector,
    textSnippet: payload.textSnippet,
    htmlSnippet: payload.htmlSnippet,
    ts: Number(payload.ts || Date.now())
  }
}

const handleMessage = (event: MessageEvent<InspectorEventPayload>) => {
  if (!event.data || typeof event.data !== 'object') return
  if (expectedOrigin.value && event.origin !== expectedOrigin.value) return

  const payload = event.data
  const eventType = String(payload.type || '')
  if (eventType === 'DAWNCHAT_PLUGIN_LOG_BATCH') {
    if (payload.pluginId && payload.pluginId !== props.pluginId) return
    if (Array.isArray(payload.logs) && payload.logs.length > 0) {
      pendingPluginLogs.value.push(...payload.logs.slice(0, 40))
      if (pendingPluginLogs.value.length > 120) {
        pendingPluginLogs.value = pendingPluginLogs.value.slice(-120)
      }
      schedulePluginLogFlush()
    }
    return
  }
  if (!eventType.startsWith('DAWNCHAT_INSPECTOR_')) return
  if (payload.pluginId && payload.pluginId !== props.pluginId) return

  if (eventType === 'DAWNCHAT_INSPECTOR_READY') {
    inspectorReady.value = true
    applyInspectorState()
    return
  }

  if (eventType === 'DAWNCHAT_INSPECTOR_ERROR') {
    statusTip.value = payload.message || labels.value.inspectorUnsupported
    logger.warn('plugin_inspector_error', payload)
    return
  }

  if (!inspectorEnabled.value) {
    return
  }

  if (eventType === 'DAWNCHAT_INSPECTOR_SELECT') {
    const normalized = buildSelectPayload(payload)
    if (!normalized) {
      statusTip.value = labels.value.inspectorUnsupported
      return
    }
    emit('inspectorSelect', normalized)
  }
}

const flushPluginLogs = async () => {
  if (!pendingPluginLogs.value.length) return
  const batch = pendingPluginLogs.value.splice(0, 40)
  try {
    const response = await fetch(buildBackendUrl(`/api/plugins/${encodeURIComponent(props.pluginId)}/logs/ingest`), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        mode: 'preview',
        source: 'frontend',
        session_id: String(props.logSessionId || ''),
        logs: batch
      })
    })
    if (!response.ok) {
      const detail = await response.text().catch(() => '')
      throw new Error(`status=${response.status} detail=${detail}`)
    }
  } catch (error) {
    logger.warn('plugin_preview_log_flush_failed', {
      pluginId: props.pluginId,
      error: String(error || '')
    })
  } finally {
    if (pendingPluginLogs.value.length > 0) {
      schedulePluginLogFlush(200)
    }
  }
}

const schedulePluginLogFlush = (delayMs = 300) => {
  if (logFlushTimer) return
  logFlushTimer = setTimeout(() => {
    logFlushTimer = null
    void flushPluginLogs()
  }, delayMs)
}

const handleIframeLoad = () => {
  clearIframeTimer()
  iframeLoading.value = false
  iframeLoadTimedOut.value = false
  inspectorReady.value = false
  inspectorAvailable.value = true
  postInspectorCommand('DAWNCHAT_INSPECTOR_PING')
  notifyIframeLoaded()
  checkInspectorAvailability()
}

const checkInspectorAvailability = async () => {
  try {
    const statusUrl = new URL('/__dawnchat/inspector-status', props.pluginUrl).toString()
    const response = await fetch(statusUrl)
    if (!response.ok) return
    const payload = (await response.json()) as { enabled?: boolean; reason?: string }
    if (payload.enabled === false) {
      inspectorAvailable.value = false
      inspectorEnabled.value = false
      statusTip.value = payload.reason || labels.value.inspectorUnsupported
      logger.warn('plugin_inspector_unavailable', payload)
    }
  } catch (err) {
    logger.warn('plugin_inspector_status_check_failed', { error: String(err) })
  }
}

usePluginUiBridge({
  pluginId: computed(() => props.pluginId),
  iframeRef,
  expectedOrigin,
  onContextPush: (payload) => emit('contextPush', payload),
  onTtsSpeakAccepted: (payload) => emit('ttsSpeakAccepted', payload),
  onTtsStopped: (payload) => emit('ttsStopped', payload),
  onCapabilityInvokeRequest: props.onCapabilityInvokeRequest,
  onHostInvokeRequest: props.onHostInvokeRequest,
})
const { notifyIframeLoaded } = usePluginHostStyleBridge({
  pluginId: computed(() => props.pluginId),
  pluginUrl: computed(() => props.pluginUrl),
  expectedOrigin,
  iframeRef,
})

watch(
  () => props.pluginUrl,
  () => {
    if (props.pluginUrl) {
      setIframeLoadingGuard()
    } else {
      clearIframeTimer()
      iframeLoading.value = true
      iframeLoadTimedOut.value = false
    }
    inspectorReady.value = false
    inspectorAvailable.value = true
    statusTip.value = ''
  }
)

onMounted(() => {
  if (props.pluginUrl) {
    setIframeLoadingGuard()
  }
  window.addEventListener('online', handleOnline)
  window.addEventListener('offline', handleOffline)
  window.addEventListener('message', handleMessage)
})

onUnmounted(() => {
  clearIframeTimer()
  if (logFlushTimer) {
    clearTimeout(logFlushTimer)
    logFlushTimer = null
  }
  pendingPluginLogs.value = []
  window.removeEventListener('online', handleOnline)
  window.removeEventListener('offline', handleOffline)
  window.removeEventListener('message', handleMessage)
})
</script>

<style scoped>
.preview-pane {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-surface-1);
}

.preview-toolbar {
  height: 52px;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0 0.75rem;
}

.tool-btn {
  min-height: 34px;
  border-radius: 8px;
  padding: 0.48rem 0.78rem;
}

.tool-btn:not(.ui-btn) {
  border: 1px solid var(--color-border);
  background: var(--color-surface-3);
  color: var(--color-text);
  border-radius: 8px;
  cursor: pointer;
}

.tool-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.tool-btn.active {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.tool-btn.danger {
  color: #ef4444;
}

.preview-iframe {
  border: none;
  flex: 1;
  width: 100%;
}

.preview-frame-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
}

.install-overlay {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 1rem;
  display: flex;
  justify-content: center;
  pointer-events: none;
  z-index: 11;
}

.install-overlay-card {
  pointer-events: auto;
  width: min(680px, calc(100% - 2rem));
  border-radius: 12px;
  padding: 0.62rem 0.85rem;
  background: rgba(18, 18, 20, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #fff;
  backdrop-filter: blur(6px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.28);
}

.install-overlay-title {
  font-size: 0.85rem;
  font-weight: 600;
}

.install-overlay-sub {
  margin-top: 0.3rem;
  color: rgba(255, 255, 255, 0.88);
  font-size: 0.78rem;
}

.install-retry-btn {
  margin-top: 0.5rem;
}

.preview-loading {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  color: var(--color-text-secondary);
}

.preview-loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.08);
  backdrop-filter: blur(1px);
  flex-direction: column;
  gap: 0.75rem;
}

.retry-btn {
  border: 1px solid var(--color-border);
  background: var(--color-surface-3);
  color: var(--color-text);
  padding: 0.4rem 0.7rem;
  border-radius: 8px;
  cursor: pointer;
}

.status-tip {
  border-top: 1px solid var(--color-border);
  padding: 0.45rem 0.75rem;
  font-size: 0.8rem;
  color: var(--color-text);
  background: var(--color-surface-2);
}

.status-sub {
  margin-top: 0.25rem;
  color: var(--color-text-secondary);
}

</style>
