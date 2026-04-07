import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import type { LocationQueryRaw } from 'vue-router'
import { useTheme } from '@/composables/useTheme'
import { useI18n } from '@/composables/useI18n'
import { logger } from '@/utils/logger'
import { openPluginDevWorkbench } from '@/app/router/navigation'
import { useCodingAgentStore } from '@/features/coding-agent/store/codingAgentStore'
import { usePluginBackTarget } from '@/features/plugin-shared/navigation/usePluginBackTarget'
import { useDevWorkbenchFacade } from '@/features/plugin-dev-workbench/services/devWorkbenchFacade'
import { usePreviewSessionGuard } from '@/features/plugin-dev-workbench/composables/usePreviewSessionGuard'
import { useWebPublishFlow } from '@/features/plugin-dev-workbench/composables/useWebPublishFlow'
import { useMobilePublishFlow } from '@/features/plugin-dev-workbench/composables/useMobilePublishFlow'
import { useComposerContextBridge } from '@/features/plugin-dev-workbench/composables/useComposerContextBridge'
import { useIwpWorkbenchFlow } from '@/features/plugin-dev-workbench/composables/useIwpWorkbenchFlow'
import { useWorkbenchLayoutState } from '@/features/plugin-dev-workbench/composables/useWorkbenchLayoutState'
import { useWorkbenchCodingRuntime } from '@/features/plugin-dev-workbench/composables/useWorkbenchCodingRuntime'
import { useAssistantSessionOrchestrator } from '@/features/plugin-dev-workbench/composables/useAssistantSessionOrchestrator'
import type { HostInvokeExecutionContext } from '@/composables/usePluginUiBridge'
import { getWorkbenchLayoutProfile } from '@/features/plugin-dev-workbench/services/workbenchLayoutProfile'
import { resolveWorkbenchLayoutVariant } from '@/features/plugin-dev-workbench/services/workbenchLayoutVariant'
import { useHostTtsPlayback } from '@/features/coding-agent/tts/useHostTtsPlayback'
import { AI_ASSISTANT_TEMPLATE_ID } from '@/config/appTemplates'
import {
  getAzureTtsConfigStatus,
  getTtsCapability,
  getTtsTaskStatus,
  saveAzureTtsConfig,
  validateAzureTtsConfig,
} from '@/services/tts/ttsClient'
import { isSystemTtsSupported, speakSystemTts, stopSystemTts } from '@/services/tts/systemTtsClient'
import { useSupabase } from '@/shared/composables/supabaseClient'
import type { InspectorSelectPayload } from '@/types/inspector'
import type { PluginWorkbenchLayout, PluginWorkbenchSurfaceMode } from '@/features/plugin/types'
import type {
  TtsSpeakAcceptedPayload,
  TtsStoppedPayload
} from '@/services/plugin-ui-bridge/messageProtocol'

const WORKBENCH_TTS_ENABLED_KEY = 'plugin-dev-workbench.tts.enabled.v1'
const WORKBENCH_TTS_ENGINE_KEY = 'plugin-dev-workbench.tts.engine.v1'
const HOST_VOICE_TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])
const HOST_VOICE_POLL_INTERVAL_MS = 200
const HOST_VOICE_WAIT_TIMEOUT_MS = 120_000
type WorkbenchTtsEngine = 'azure' | 'python' | 'system'
const toSlug = (value: string) =>
  String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[._-]+|[._-]+$/g, '')

const buildOwnerPrefix = (email: string, userId: string): string => {
  const normalizedEmail = String(email || '').toLowerCase()
  const normalizedUserId = String(userId || 'uid').trim() || 'uid'
  if (!normalizedEmail.includes('@')) return `com.local.user.${normalizedUserId.slice(0, 12)}`
  const [localPart, domainPart] = normalizedEmail.split('@')
  const domain = String(domainPart || 'local')
    .split('.')
    .reverse()
    .map((item) => item.replace(/[^a-z0-9]+/g, '-'))
    .filter(Boolean)
  const local = String(localPart || 'user').replace(/[^a-z0-9]+/g, '-')
  return ['com', ...domain, local, normalizedUserId.slice(0, 12)].join('.')
}

const AZURE_ZH_VOICE_OPTIONS = [
  { value: 'zh-CN-XiaoxiaoNeural', label: 'Xiaoxiao (女声)' },
  { value: 'zh-CN-YunxiNeural', label: 'Yunxi (男声)' },
  { value: 'zh-CN-XiaochenNeural', label: 'Xiaochen (女声)' },
  { value: 'zh-CN-YunjianNeural', label: 'Yunjian (男声)' },
]
const AZURE_EN_VOICE_OPTIONS = [
  { value: 'en-US-JennyNeural', label: 'Jenny (女声)' },
  { value: 'en-US-AriaNeural', label: 'Aria (女声)' },
  { value: 'en-US-GuyNeural', label: 'Guy (男声)' },
  { value: 'en-US-DavisNeural', label: 'Davis (男声)' },
]

export const usePluginDevWorkbenchOrchestration = () => {
  const route = useRoute()
  const router = useRouter()
  const { redirectToAppsInstalled } = usePluginBackTarget(route, router)
  const facade = useDevWorkbenchFacade()
  const { t, locale } = useI18n()
  const { theme } = useTheme()
  const { getSession } = useSupabase()
  const codingAgentStore = useCodingAgentStore()
  const { isStreaming } = storeToRefs(codingAgentStore)

  const chatInput = ref('')
  const publishToast = ref<{ visible: boolean; message: string; kind: 'success' | 'error' }>({
    visible: false,
    message: '',
    kind: 'success'
  })
  const renamingApp = ref(false)
  let publishToastTimer: ReturnType<typeof setTimeout> | null = null
  const pluginId = computed(() => String(route.params.pluginId || ''))
  const { ensureReady: ensureWorkbenchCodingReady } = useWorkbenchCodingRuntime({ pluginId })
  const workbenchMode = ref<'requirements' | 'agent'>('requirements')
  const exitDialogVisible = ref(false)
  const exitBusy = ref(false)
  const exitWarningMessage = ref('')
  const allowRouteLeaveAfterClose = ref(false)
  const allowLifecycleWorkbenchNavigation = ref(false)
  const creatingAssistant = ref(false)
  const pendingExitAction = ref<((choice: 'save' | 'direct' | 'cancel') => void) | null>(null)

  const {
    activeApp,
    activeMode,
    installedApps,
    previewReady,
    previewLoadingText,
    previewPaneKey,
    previewLifecycleTask,
    previewLifecycleBusy,
    previewInstallStatus,
    previewInstallErrorMessage,
    previewChatBlocked,
    shouldPollPreviewStatus,
    ensurePreviewRunning,
    syncActiveApp,
    startPreviewStatusPolling,
    stopPreviewStatusPolling,
    restartPreview,
    handlePreviewRecoverEscalate,
    retryInstall,
    stopAndExit,
  } = usePreviewSessionGuard({
    pluginId,
    redirectToAppsInstalled,
  }, facade)

  const previewLogSessionId = computed(() => String(activeApp.value?.preview?.log_session_id || ''))
  const isPreviewRenderable = computed(() => Boolean(activeApp.value && pluginUrl.value && previewReady.value))
  const installedAppByRoute = computed(() => {
    return installedApps.value.find((item) => item.id === pluginId.value) || null
  })
  const workbenchLayout = computed<PluginWorkbenchLayout>(() => {
    const layout = String(
      activeApp.value?.preview?.workbench_layout
      || installedAppByRoute.value?.preview?.workbench_layout
      || route.query.layout
      || 'default'
    )
    return layout === 'agent_preview' ? 'agent_preview' : 'default'
  })
  const workbenchProfile = computed(() => getWorkbenchLayoutProfile(workbenchLayout.value))
  const isAgentPreviewLayout = computed(() => workbenchProfile.value.isAgentPreview)
  const showCreateAssistantAction = computed(() => workbenchLayout.value === 'agent_preview')
  const hasIwpRequirements = computed(() => {
    const fromActive = activeApp.value?.preview?.has_iwp_requirements
    if (typeof fromActive === 'boolean') return fromActive
    const fromInstalled = installedAppByRoute.value?.preview?.has_iwp_requirements
    if (typeof fromInstalled === 'boolean') return fromInstalled
    return false
  })
  const surfaceMode = computed<PluginWorkbenchSurfaceMode>(() => {
    const raw = route.query.surface
    const normalized = String(Array.isArray(raw) ? raw[0] || '' : raw || '').trim().toLowerCase()
    return normalized === 'assistant_compact' ? 'assistant_compact' : 'dev_split'
  })
  const isAssistantCompactSurface = computed(() => surfaceMode.value === 'assistant_compact')
  const workbenchLayoutVariant = computed(() => {
    return resolveWorkbenchLayoutVariant({
      isAssistantCompactSurface: isAssistantCompactSurface.value,
      isAgentPreviewLayout: isAgentPreviewLayout.value,
      hasIwpRequirements: hasIwpRequirements.value,
    })
  })
  const isWebApp = computed(() => String(activeApp.value?.app_type || 'desktop') === 'web')
  const isMobileApp = computed(() => String(activeApp.value?.app_type || 'desktop') === 'mobile')
  const appTypeLabel = computed(() => {
    if (isWebApp.value) return 'Web'
    if (isMobileApp.value) return 'Mobile'
    return ''
  })

  const pluginUrl = computed(() => {
    const previewUrl = activeApp.value?.preview?.url || ''
    if (!previewUrl) return ''
    const currentPluginId = String(pluginId.value || '').trim()
    try {
      const url = new URL(previewUrl)
      url.searchParams.set('theme', String(theme.value || ''))
      url.searchParams.set('lang', String(locale.value || ''))
      if (currentPluginId) {
        url.searchParams.set('plugin_id', currentPluginId)
      }
      return url.toString()
    } catch {
      const separator = previewUrl.includes('?') ? '&' : '?'
      const query = [
        `theme=${encodeURIComponent(String(theme.value || ''))}`,
        `lang=${encodeURIComponent(String(locale.value || ''))}`,
        currentPluginId ? `plugin_id=${encodeURIComponent(currentPluginId)}` : '',
      ].filter(Boolean).join('&')
      return `${previewUrl}${separator}${query}`
    }
  })
  const previewFrontendMode = computed<'dev' | 'dist'>(() => {
    const raw = String(activeApp.value?.preview?.frontend_mode || 'dev')
    return raw === 'dist' ? 'dist' : 'dev'
  })
  const previewFrontendReachable = computed<boolean | null>(() => {
    const reachable = activeApp.value?.preview?.frontend_reachable
    if (reachable === true) return true
    if (reachable === false) return false
    return null
  })

  const showPublishToast = (message: string, kind: 'success' | 'error') => {
    publishToast.value = { visible: true, message, kind }
    if (publishToastTimer) {
      clearTimeout(publishToastTimer)
    }
    publishToastTimer = setTimeout(() => {
      publishToast.value.visible = false
      publishToastTimer = null
    }, 2600)
  }

  const {
    publishDialogVisible,
    publishState,
    openPublishDialog,
    closePublishDialog,
    handlePublish,
  } = useWebPublishFlow({
    pluginId,
    activeApp,
    facade,
    getSession,
    t,
    showToast: showPublishToast,
  })

  const {
    mobileQrDialogVisible,
    mobileOfflineDialogVisible,
    mobileShareUrl,
    mobileLanIp,
    mobileQrLoading,
    mobileQrError,
    mobilePublishState,
    openMobilePreviewQr,
    openMobileOfflinePlaceholder,
    closeMobileQr,
    closeMobileOffline,
    handleMobilePublish,
    handleMobileRefreshShare,
  } = useMobilePublishFlow({
    pluginId,
    activeApp,
    facade,
    getSession,
    t,
    showToast: showPublishToast,
  })

  const {
    handleComposerSelectionChange,
    handleInspectorSelect: pushInspectorContext,
    handleContextPush,
  } = useComposerContextBridge({
    chatInput,
  })

  const {
    iwpRoot,
    fileTreeCollapsed,
    centerPaneMode,
    filesLoading,
    fileList,
    activeFilePath,
    markdownContent,
    fileLoading,
    fileSaving,
    buildState,
    isDirty,
    hasActiveFile,
    canBuild,
    loadFileList,
    openFile,
    saveCurrentFile,
    updateContent,
    toggleFileTree,
    setCenterPaneMode,
    triggerBuild,
    readonlyFilePath,
    readonlyFileLine,
    readonlyFileContent,
    readonlyLoading,
    readonlyError,
    openReadonlyByInspector,
    backToMarkdown,
    reset: resetIwpFlow,
  } = useIwpWorkbenchFlow({
    pluginId: () => pluginId.value,
    t,
  })

  const isBuildRunning = computed(() => buildState.value.status === 'running')
  const hasBuildSession = computed(() => Boolean(buildState.value.sessionId))
  const hasUnsavedMarkdown = computed(() => {
    return workbenchMode.value === 'requirements' && centerPaneMode.value === 'markdown' && isDirty.value
  })
  const hasRunningSession = computed(() => {
    return isBuildRunning.value || isStreaming.value
  })

  const {
    previewWidthPx,
    agentLogHeightPx,
    isResizingPreview,
    isResizingAgentLog,
    startResizePreview,
    startResizeAgentLog,
  } = useWorkbenchLayoutState({
    profile: workbenchProfile,
    layoutVariant: workbenchLayoutVariant,
  })
  const {
    init: initTtsPlayback,
    dispose: disposeTtsPlayback,
    currentTaskId: ttsCurrentTaskId,
    streamStatus: ttsStreamStatus,
    playbackState: ttsPlaybackState,
    attachTask: attachTtsTask,
    syncStopped: syncTtsStopped,
    stopSpeak: stopTtsSpeak,
    waitForPlaybackCompletion: waitForTtsPlaybackCompletion,
  } = useHostTtsPlayback()
  const ttsEnabled = ref(true)
  const ttsBackendAvailable = ref(false)
  const selectedTtsEngine = ref<WorkbenchTtsEngine>('system')
  const ttsEngineBeforeAzureDialog = ref<WorkbenchTtsEngine>('system')
  const selectedTtsEngineStored = ref(false)
  const systemTtsStatus = ref<'idle' | 'playing' | 'error'>('idle')
  const systemTtsErrorMessage = ref('')
  const azureTtsDialogVisible = ref(false)
  const azureTtsSaving = ref(false)
  const azureTtsErrorMessage = ref('')
  const azureTtsApiKey = ref('')
  const azureTtsRegion = ref('')
  const azureTtsDefaultVoiceZh = ref('zh-CN-XiaoxiaoNeural')
  const azureTtsDefaultVoiceEn = ref('en-US-JennyNeural')
  const azureTtsApiKeyConfigured = ref(false)
  const azureTtsZhVoiceOptions = AZURE_ZH_VOICE_OPTIONS
  const azureTtsEnVoiceOptions = AZURE_EN_VOICE_OPTIONS
  const ttsEngineOptions = computed(() => {
    const options: Array<{ id: WorkbenchTtsEngine; label: string }> = [
      { id: 'azure', label: 'Azure TTS' },
      { id: 'system', label: 'System TTS' },
    ]
    if (ttsBackendAvailable.value) {
      options.splice(1, 0, { id: 'python', label: 'Python TTS' })
    }
    return options
  })
  const { handleCapabilityInvokeRequest, handleAssistantRuntimeEvent } = useAssistantSessionOrchestrator({
    pluginId,
  })

  const loadTtsEnabled = () => {
    try {
      const raw = localStorage.getItem(WORKBENCH_TTS_ENABLED_KEY)
      if (raw === null) {
        ttsEnabled.value = true
        return
      }
      ttsEnabled.value = raw !== 'false'
    } catch {
      ttsEnabled.value = true
    }
  }

  const persistTtsEnabled = () => {
    try {
      localStorage.setItem(WORKBENCH_TTS_ENABLED_KEY, ttsEnabled.value ? 'true' : 'false')
    } catch {
    }
  }

  const loadSelectedTtsEngine = () => {
    selectedTtsEngineStored.value = false
    try {
      const raw = String(localStorage.getItem(WORKBENCH_TTS_ENGINE_KEY) || '').trim()
      if (raw === 'python' || raw === 'system' || raw === 'azure') {
        selectedTtsEngine.value = raw
        selectedTtsEngineStored.value = true
      } else {
        selectedTtsEngine.value = 'system'
      }
    } catch {
      selectedTtsEngine.value = 'system'
    }
  }

  const persistSelectedTtsEngine = () => {
    try {
      localStorage.setItem(WORKBENCH_TTS_ENGINE_KEY, selectedTtsEngine.value)
    } catch {
    }
  }

  const applyDefaultTtsEngine = () => {
    if (ttsBackendAvailable.value) {
      if (!selectedTtsEngineStored.value) {
        selectedTtsEngine.value = 'python'
      }
    } else if (selectedTtsEngine.value === 'python') {
      selectedTtsEngine.value = 'system'
    }
    persistSelectedTtsEngine()
  }

  const refreshTtsCapability = async () => {
    try {
      const capability = await getTtsCapability(pluginId.value)
      ttsBackendAvailable.value = Boolean(capability.data?.available)
    } catch (error) {
      ttsBackendAvailable.value = false
      logger.warn('plugin_dev_workbench_tts_capability_failed', {
        pluginId: pluginId.value,
        error: String(error)
      })
    }
    applyDefaultTtsEngine()
  }

  const refreshAzureTtsStatus = async () => {
    try {
      const response = await getAzureTtsConfigStatus()
      azureTtsApiKeyConfigured.value = Boolean(response.data.api_key_configured)
      azureTtsRegion.value = String(response.data.region || '').trim()
      azureTtsDefaultVoiceZh.value = String(response.data.default_voice_zh || '').trim() || 'zh-CN-XiaoxiaoNeural'
      azureTtsDefaultVoiceEn.value = String(response.data.default_voice_en || '').trim() || 'en-US-JennyNeural'
    } catch (error) {
      logger.warn('plugin_dev_workbench_azure_tts_status_failed', {
        pluginId: pluginId.value,
        error: String(error),
      })
    }
  }

  const openAzureTtsDialog = async () => {
    azureTtsErrorMessage.value = ''
    azureTtsApiKey.value = ''
    ttsEngineBeforeAzureDialog.value = selectedTtsEngine.value
    await refreshAzureTtsStatus()
    azureTtsDialogVisible.value = true
  }

  const openAzureTtsSettings = async () => {
    await openAzureTtsDialog()
  }

  const closeAzureTtsDialog = () => {
    azureTtsDialogVisible.value = false
    azureTtsSaving.value = false
    azureTtsErrorMessage.value = ''
    if (selectedTtsEngine.value !== 'azure') {
      selectedTtsEngine.value = ttsEngineBeforeAzureDialog.value
      persistSelectedTtsEngine()
    }
  }

  const submitAzureTtsDialog = async () => {
    const region = String(azureTtsRegion.value || '').trim()
    const defaultVoiceZh = String(azureTtsDefaultVoiceZh.value || '').trim() || 'zh-CN-XiaoxiaoNeural'
    const defaultVoiceEn = String(azureTtsDefaultVoiceEn.value || '').trim() || 'en-US-JennyNeural'
    const apiKey = String(azureTtsApiKey.value || '').trim()
    if (!region) {
      azureTtsErrorMessage.value = 'Region 不能为空'
      return
    }
    if (!apiKey && !azureTtsApiKeyConfigured.value) {
      azureTtsErrorMessage.value = '请填写 Azure API Key'
      return
    }
    azureTtsSaving.value = true
    azureTtsErrorMessage.value = ''
    try {
      await validateAzureTtsConfig({
        api_key: apiKey,
        region,
        voice: '',
        default_voice_zh: defaultVoiceZh,
        default_voice_en: defaultVoiceEn,
      })
      await saveAzureTtsConfig({
        api_key: apiKey,
        region,
        voice: '',
        default_voice_zh: defaultVoiceZh,
        default_voice_en: defaultVoiceEn,
      })
      selectedTtsEngine.value = 'azure'
      persistSelectedTtsEngine()
      azureTtsApiKeyConfigured.value = true
      azureTtsDialogVisible.value = false
      azureTtsApiKey.value = ''
    } catch (error) {
      azureTtsErrorMessage.value = String(error)
      logger.warn('plugin_dev_workbench_azure_tts_config_failed', {
        pluginId: pluginId.value,
        error: String(error),
      })
    } finally {
      azureTtsSaving.value = false
    }
  }

  const selectTtsEngine = async (value: string) => {
    if (value === 'azure') {
      await openAzureTtsDialog()
      return
    }
    selectedTtsEngine.value = value === 'python' ? 'python' : 'system'
    persistSelectedTtsEngine()
  }

  const stopTtsPlayback = async () => {
    await stopTtsSpeak(ttsCurrentTaskId.value || undefined)
  }

  const toggleTtsEnabled = async () => {
    const next = !ttsEnabled.value
    ttsEnabled.value = next
    persistTtsEnabled()
    if (!next) {
      await stopTtsPlayback()
    }
  }

  const handleTtsSpeakAccepted = async (payload: TtsSpeakAcceptedPayload) => {
    if (!ttsEnabled.value) {
      logger.info('plugin_dev_workbench_tts_skip_disabled', { pluginId: pluginId.value })
      return
    }
    const taskId = String(payload.task_id || '').trim()
    if (!taskId) {
      logger.warn('plugin_dev_workbench_tts_skip_empty_task', { pluginId: pluginId.value })
      return
    }
    try {
      logger.info('plugin_dev_workbench_tts_attach', { pluginId: pluginId.value, taskId })
      await attachTtsTask(taskId)
    } catch (error) {
      logger.warn('plugin_dev_workbench_tts_attach_failed', {
        pluginId: pluginId.value,
        taskId,
        error: String(error)
      })
    }
  }

  const handleTtsStopped = async (payload: TtsStoppedPayload) => {
    const taskId = String(payload.task_id || '').trim()
    await syncTtsStopped(taskId || undefined)
  }

  const waitForHostVoiceTerminal = async (taskId: string): Promise<string> => {
    const normalizedTaskId = String(taskId || '').trim()
    if (!normalizedTaskId) {
      return 'unknown'
    }
    const startedAt = Date.now()
    while (Date.now() - startedAt < HOST_VOICE_WAIT_TIMEOUT_MS) {
      const response = await getTtsTaskStatus(normalizedTaskId)
      const data = response.data as Record<string, unknown>
      const status = String(data.status || '').trim()
      if (HOST_VOICE_TERMINAL_STATUSES.has(status)) {
        return status
      }
      await new Promise<void>((resolve) => {
        window.setTimeout(resolve, HOST_VOICE_POLL_INTERVAL_MS)
      })
    }
    throw new Error(`host voice wait timeout: ${normalizedTaskId}`)
  }

  const handleHostInvokeRequest = async (
    context: HostInvokeExecutionContext
  ): Promise<Record<string, unknown>> => {
    const functionName = String(context.invoke.functionName || '').trim()
    const payload = context.invoke.payload || {}
    if (functionName === 'dawnchat.host.voice.speak') {
      const text = String(payload.text || '').trim()
      if (!text) {
        return {
          ok: false,
          error_code: 'invalid_arguments',
          message: 'text is required',
        }
      }
      const resolvedTtsEngine: WorkbenchTtsEngine = selectedTtsEngine.value === 'azure'
        ? 'azure'
        : (selectedTtsEngine.value === 'python' && ttsBackendAvailable.value ? 'python' : 'system')
      if (resolvedTtsEngine === 'python' || resolvedTtsEngine === 'azure') {
        const taskId = await useHostTtsPlayback().startSpeak({
          plugin_id: pluginId.value,
          text,
          voice: typeof payload.voice === 'string' ? payload.voice : undefined,
          sid: typeof payload.sid === 'number' ? payload.sid : undefined,
          mode: 'manual',
          engine: resolvedTtsEngine,
          interrupt: payload.interrupt !== false,
        })
        const status = await waitForHostVoiceTerminal(taskId)
        if (status !== 'completed') {
          return {
            ok: false,
            error_code: 'voice_task_not_completed',
            message: `voice task terminal status: ${status}`,
            data: {
              task_id: taskId,
              status,
              engine: resolvedTtsEngine,
            },
          }
        }
        await waitForTtsPlaybackCompletion(taskId, HOST_VOICE_WAIT_TIMEOUT_MS)
        return {
          ok: true,
          data: {
            task_id: taskId,
            status,
            engine: resolvedTtsEngine,
          },
        }
      }
      if (!isSystemTtsSupported()) {
        return {
          ok: false,
          error_code: 'system_tts_not_supported',
          message: 'System TTS is not supported in current runtime',
        }
      }
      systemTtsStatus.value = 'playing'
      systemTtsErrorMessage.value = ''
      try {
        await speakSystemTts({
          text,
          voice: typeof payload.voice === 'string' ? payload.voice : undefined,
        })
      } catch (error) {
        systemTtsStatus.value = 'error'
        systemTtsErrorMessage.value = String(error)
        throw error
      }
      systemTtsStatus.value = 'idle'
      return {
        ok: true,
        data: {
          task_id: `system-${Date.now()}`,
          status: 'completed',
          engine: resolvedTtsEngine,
        },
      }
    }
    if (functionName === 'dawnchat.host.voice.stop') {
      const taskId = typeof payload.task_id === 'string' ? payload.task_id : undefined
      if (selectedTtsEngine.value === 'azure' || (selectedTtsEngine.value === 'python' && ttsBackendAvailable.value)) {
        await stopTtsSpeak(taskId || undefined)
      } else {
        stopSystemTts()
        systemTtsStatus.value = 'idle'
      }
      return {
        ok: true,
        data: {
          stopped: true,
          task_id: taskId || ttsCurrentTaskId.value || '',
        },
      }
    }
    if (functionName === 'dawnchat.host.voice.status') {
      if (
        selectedTtsEngine.value !== 'azure'
        && !(selectedTtsEngine.value === 'python' && ttsBackendAvailable.value)
      ) {
        return {
          ok: true,
          data: {
            engine: 'system',
            status: systemTtsStatus.value,
            error: systemTtsErrorMessage.value,
          },
        }
      }
      const taskId = typeof payload.task_id === 'string' ? payload.task_id.trim() : ''
      const targetTaskId = taskId || ttsCurrentTaskId.value
      if (!targetTaskId) {
        return {
          ok: false,
          error_code: 'task_not_found',
          message: 'task_id is required',
        }
      }
      const response = await getTtsTaskStatus(targetTaskId)
      return {
        ok: true,
        data: {
          task_id: targetTaskId,
          ...response.data,
        },
      }
    }
    return {
      ok: false,
      error_code: 'unsupported_host_function',
      message: `unsupported host function: ${functionName}`,
    }
  }

  const setWorkbenchMode = (mode: 'requirements' | 'agent') => {
    if (!hasIwpRequirements.value && mode === 'requirements') return
    workbenchMode.value = mode
  }

  const setChatInput = (value: string) => {
    chatInput.value = value
  }

  const setSurfaceMode = async (mode: PluginWorkbenchSurfaceMode) => {
    const nextQuery: LocationQueryRaw = {
      ...route.query,
    }
    if (mode === 'assistant_compact') {
      nextQuery.surface = 'assistant_compact'
    } else {
      delete nextQuery.surface
    }
    await router.replace({
      name: String(route.name || 'plugin-dev-workbench'),
      params: route.params,
      query: nextQuery,
    })
  }

  const togglePreviewFullscreen = async () => {
    const next = surfaceMode.value === 'assistant_compact' ? 'dev_split' : 'assistant_compact'
    await setSurfaceMode(next)
  }

  const openBuildSession = () => {
    if (!buildState.value.sessionId) return
    workbenchMode.value = 'agent'
  }

  const resolveExitPrompt = async () => {
    if (!hasUnsavedMarkdown.value && !hasRunningSession.value) {
      return 'direct' as const
    }
    exitWarningMessage.value = hasRunningSession.value ? t.value.apps.workbenchCloseRunningWarning : ''
    exitDialogVisible.value = true
    const choice = await new Promise<'save' | 'direct' | 'cancel'>((resolve) => {
      pendingExitAction.value = resolve
    })
    pendingExitAction.value = null
    exitDialogVisible.value = false
    return choice
  }

  const handleExitSaveAndClose = () => {
    pendingExitAction.value?.('save')
  }

  const handleExitDirectly = () => {
    pendingExitAction.value?.('direct')
  }

  const handleExitCancel = () => {
    pendingExitAction.value?.('cancel')
  }

  const handleCloseWorkbench = async () => {
    if (exitBusy.value || allowRouteLeaveAfterClose.value || !pluginId.value) {
      return false
    }
    exitBusy.value = true
    try {
      const choice = await resolveExitPrompt()
      if (choice === 'cancel') {
        return false
      }
      if (choice === 'save' && hasUnsavedMarkdown.value) {
        try {
          await saveCurrentFile()
        } catch (error) {
          showPublishToast(t.value.apps.workbenchCloseSaveFailed, 'error')
          return false
        }
      }
      allowRouteLeaveAfterClose.value = true
      await stopAndExit(pluginId.value)
      return true
    } finally {
      exitBusy.value = false
    }
  }

  const handleRestartPreview = async (appId: string) => {
    await restartPreview(appId)
  }

  const handleRetryInstall = async () => {
    await retryInstall()
  }

  const handlePreviewRecoverEscalation = async (payload: { reason: string; retries: number }) => {
    await handlePreviewRecoverEscalate(payload)
  }

  const renameActiveApp = async (nextName: string): Promise<boolean> => {
    const id = pluginId.value
    if (!id || renamingApp.value) return false
    const normalizedName = String(nextName || '').trim()
    if (!normalizedName) {
      showPublishToast(t.value.apps.workbenchRenameNameRequired, 'error')
      return false
    }
    if (normalizedName === String(activeApp.value?.name || '').trim()) {
      return true
    }
    renamingApp.value = true
    try {
      await facade.updateAppDisplayName(id, normalizedName)
      showPublishToast(t.value.apps.workbenchRenameSuccess, 'success')
      return true
    } catch (error) {
      showPublishToast(t.value.apps.workbenchRenameFailed, 'error')
      logger.warn('plugin_dev_workbench_rename_failed', {
        pluginId: id,
        error: String(error),
      })
      return false
    } finally {
      renamingApp.value = false
    }
  }

  const createAssistantFromWorkbench = async () => {
    if (creatingAssistant.value) return
    creatingAssistant.value = true
    const session = await getSession()
    const userId = String(session?.user?.id || '').trim()
    const userEmail = String(session?.user?.email || '').trim()
    if (!userId || !userEmail) {
      showPublishToast(t.value.apps.workbenchCreateAssistantAuthRequired, 'error')
      creatingAssistant.value = false
      return
    }
    const ownerPrefix = buildOwnerPrefix(userEmail, userId)
    const suffix = toSlug(`ai-assistant-${Date.now().toString().slice(-6)}`) || `ai-assistant-${Date.now()}`
    try {
      allowLifecycleWorkbenchNavigation.value = true
      const task = await facade.runLifecycleOperation({
        operationType: 'create_dev_session',
        payload: {
          template_id: AI_ASSISTANT_TEMPLATE_ID,
          app_type: 'desktop',
          name: t.value.apps.quickCreateAssistantName,
          plugin_id: `${ownerPrefix}.${suffix}`,
          description: '',
          owner_email: userEmail,
          owner_user_id: userId,
          is_main_assistant: false,
        },
        navigationIntent: 'workbench',
        from: String(route.fullPath || ''),
        uiMode: 'modal',
        completionMessage: t.value.apps.workbenchCreateAssistantLaunching,
      })
      const createdPluginId = String(task.result?.plugin_id || task.plugin_id || '').trim()
      const currentPluginId = String(route.params.pluginId || '').trim()
      if (createdPluginId && currentPluginId === pluginId.value) {
        // Guard fallback: if lifecycle navigation was blocked, do one explicit retry.
        allowLifecycleWorkbenchNavigation.value = true
        await openPluginDevWorkbench(router, createdPluginId, String(route.fullPath || ''))
        const afterRetryPluginId = String(route.params.pluginId || '').trim()
        if (afterRetryPluginId !== createdPluginId) {
          showPublishToast(t.value.apps.workbenchCreateAssistantNavigationFailed, 'error')
        }
      }
    } catch (error) {
      showPublishToast(t.value.apps.workbenchCreateAssistantFailed, 'error')
      logger.warn('plugin_dev_workbench_create_assistant_failed', {
        pluginId: pluginId.value,
        error: String(error),
      })
    } finally {
      allowLifecycleWorkbenchNavigation.value = false
      creatingAssistant.value = false
    }
  }

  const handleInspectorSelect = async (payload: InspectorSelectPayload) => {
    pushInspectorContext(payload)
    if (hasIwpRequirements.value) {
      await openReadonlyByInspector(payload)
      workbenchMode.value = 'requirements'
    }
  }

  const handleTriggerBuild = async () => {
    await triggerBuild()
    if (hasIwpRequirements.value) {
      workbenchMode.value = 'requirements'
    }
  }

  onBeforeRouteLeave(async (to) => {
    if (allowRouteLeaveAfterClose.value) {
      return true
    }
    if (allowLifecycleWorkbenchNavigation.value && String(to.name || '') === 'plugin-dev-workbench') {
      return true
    }
    if (!pluginId.value) {
      return true
    }
    const targetName = String(to.name || '')
    if (targetName === 'login' || targetName === 'auth-callback') {
      return true
    }
    logger.warn('plugin_dev_workbench_block_unexpected_leave', {
      pluginId: pluginId.value,
      to: String(to.fullPath || ''),
    })
    return false
  })

  watch(
    () => installedApps.value,
    () => {
      syncActiveApp()
    },
    { deep: true }
  )

  watch(
    () => shouldPollPreviewStatus.value,
    (next) => {
      if (next) {
        startPreviewStatusPolling()
      } else {
        stopPreviewStatusPolling()
      }
    },
    { immediate: true }
  )

  watch(
    () => pluginId.value,
    async (next, prev) => {
      if (!prev || next === prev) return
      await syncTtsStopped()
      await refreshAzureTtsStatus()
      await refreshTtsCapability()
    }
  )

  onMounted(async () => {
    initTtsPlayback()
    loadTtsEnabled()
    loadSelectedTtsEngine()
    await refreshAzureTtsStatus()
    await refreshTtsCapability()
    activeMode.value = 'preview'
    previewLoadingText.value = t.value.apps.starting
    if (pluginId.value) {
      facade.rememberBuildHubRecentSession(pluginId.value)
    }
    await ensurePreviewRunning()
    await ensureWorkbenchCodingReady('preview_ready')
    if (hasIwpRequirements.value) {
      await loadFileList()
    } else {
      workbenchMode.value = 'agent'
    }
  })

  onUnmounted(() => {
    void disposeTtsPlayback()
    resetIwpFlow()
    stopPreviewStatusPolling()
    if (publishToastTimer) {
      clearTimeout(publishToastTimer)
      publishToastTimer = null
    }
    logger.info('plugin_dev_workbench_exit', { pluginId: pluginId.value })
    if (!allowRouteLeaveAfterClose.value) {
      facade.closeApp()
    }
  })

  return {
    t,
    chatInput,
    activeApp,
    pluginId,
    appTypeLabel,
    isWebApp,
    isMobileApp,
    isPreviewRenderable,
    previewPaneKey,
    pluginUrl,
    previewFrontendMode,
    previewFrontendReachable,
    previewLogSessionId,
    previewLifecycleTask,
    previewLifecycleBusy,
    previewInstallStatus,
    previewInstallErrorMessage,
    previewLoadingText,
    previewChatBlocked,
    publishDialogVisible,
    publishState,
    mobileQrDialogVisible,
    mobileShareUrl,
    mobileLanIp,
    mobileQrLoading,
    mobileQrError,
    mobileOfflineDialogVisible,
    mobilePublishState,
    publishToast,
    openPublishDialog,
    closePublishDialog,
    openMobilePreviewQr,
    openMobileOfflinePlaceholder,
    closeMobileQr,
    closeMobileOffline,
    handleCloseWorkbench,
    handleExitSaveAndClose,
    handleExitDirectly,
    handleExitCancel,
    exitDialogVisible,
    exitBusy,
    exitWarningMessage,
    handleRestartPreview,
    handlePreviewRecoverEscalation,
    handleRetryInstall,
    handleInspectorSelect,
    handleContextPush,
    handleTtsSpeakAccepted,
    handleTtsStopped,
    handleComposerSelectionChange,
    handlePublish,
    handleMobilePublish,
    handleMobileRefreshShare,
    iwpRoot,
    fileTreeCollapsed,
    centerPaneMode,
    filesLoading,
    fileList,
    activeFilePath,
    markdownContent,
    fileLoading,
    fileSaving,
    buildState,
    isDirty,
    hasActiveFile,
    canBuild,
    loadFileList,
    openFile,
    saveCurrentFile,
    updateContent,
    toggleFileTree,
    setCenterPaneMode,
    triggerBuild: handleTriggerBuild,
    readonlyFilePath,
    readonlyFileLine,
    readonlyFileContent,
    readonlyLoading,
    readonlyError,
    backToMarkdown,
    openBuildSession,
    hasBuildSession,
    isBuildRunning,
    renamingApp,
    renameActiveApp,
    workbenchMode,
    workbenchProfile,
    isAgentPreviewLayout,
    hasIwpRequirements,
    showCreateAssistantAction,
    creatingAssistant,
    surfaceMode,
    workbenchLayoutVariant,
    isAssistantCompactSurface,
    setWorkbenchMode,
    setChatInput,
    togglePreviewFullscreen,
    previewWidthPx,
    agentLogHeightPx,
    isResizingPreview,
    isResizingAgentLog,
    startResizePreview,
    startResizeAgentLog,
    ttsEnabled,
    selectedTtsEngine,
    ttsEngineOptions,
    azureTtsDialogVisible,
    azureTtsSaving,
    azureTtsErrorMessage,
    azureTtsApiKey,
    azureTtsApiKeyConfigured,
    azureTtsRegion,
    azureTtsDefaultVoiceZh,
    azureTtsDefaultVoiceEn,
    azureTtsZhVoiceOptions,
    azureTtsEnVoiceOptions,
    ttsPlaybackState,
    ttsStreamStatus,
    ttsCurrentTaskId,
    toggleTtsEnabled,
    selectTtsEngine,
    openAzureTtsSettings,
    closeAzureTtsDialog,
    submitAzureTtsDialog,
    stopTtsPlayback,
    handleCapabilityInvokeRequest,
    handleAssistantRuntimeEvent,
    handleHostInvokeRequest,
    createAssistantFromWorkbench,
  }
}
