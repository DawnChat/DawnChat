import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useTheme } from '@/composables/useTheme'
import { useI18n } from '@/composables/useI18n'
import { logger } from '@/utils/logger'
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
import { getTtsCapability, getTtsTaskStatus } from '@/services/tts/ttsClient'
import { isSystemTtsSupported, speakSystemTts, stopSystemTts } from '@/services/tts/systemTtsClient'
import { useSupabase } from '@/shared/composables/supabaseClient'
import type { InspectorSelectPayload } from '@/types/inspector'
import type { PluginWorkbenchLayout, PluginWorkbenchSurfaceMode } from '@/features/plugin/types'
import type { TtsSpeakAcceptedPayload, TtsStoppedPayload } from '@/services/plugin-ui-bridge/messageProtocol'

const WORKBENCH_TTS_ENABLED_KEY = 'plugin-dev-workbench.tts.enabled.v1'
const WORKBENCH_TTS_ENGINE_KEY = 'plugin-dev-workbench.tts.engine.v1'
const HOST_VOICE_TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])
const HOST_VOICE_POLL_INTERVAL_MS = 200
const HOST_VOICE_WAIT_TIMEOUT_MS = 120_000
type WorkbenchTtsEngine = 'python' | 'system'

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
  let publishToastTimer: ReturnType<typeof setTimeout> | null = null
  const pluginId = computed(() => String(route.params.pluginId || ''))
  const { ensureReady: ensureWorkbenchCodingReady } = useWorkbenchCodingRuntime({ pluginId })
  const workbenchMode = ref<'requirements' | 'agent'>('requirements')
  const exitDialogVisible = ref(false)
  const exitBusy = ref(false)
  const exitWarningMessage = ref('')
  const allowRouteLeaveAfterClose = ref(false)
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
    const separator = previewUrl.includes('?') ? '&' : '?'
    return `${previewUrl}${separator}theme=${theme.value}&lang=${locale.value}`
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
  const selectedTtsEngineStored = ref(false)
  const systemTtsStatus = ref<'idle' | 'playing' | 'error'>('idle')
  const systemTtsErrorMessage = ref('')
  const ttsEngineOptions = computed(() => {
    if (ttsBackendAvailable.value) {
      return [
        { id: 'python', label: 'Python TTS' },
        { id: 'system', label: 'System TTS' },
      ]
    }
    return [{ id: 'system', label: 'System TTS' }]
  })
  const { handleCapabilityInvokeRequest } = useAssistantSessionOrchestrator({
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
      if (raw === 'python' || raw === 'system') {
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

  const selectTtsEngine = (value: string) => {
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
      const resolvedTtsEngine: WorkbenchTtsEngine = selectedTtsEngine.value === 'python' && ttsBackendAvailable.value
        ? 'python'
        : 'system'
      if (resolvedTtsEngine === 'python') {
        const taskId = await useHostTtsPlayback().startSpeak({
          plugin_id: pluginId.value,
          text,
          voice: typeof payload.voice === 'string' ? payload.voice : undefined,
          sid: typeof payload.sid === 'number' ? payload.sid : undefined,
          mode: 'manual',
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
      if (selectedTtsEngine.value === 'python' && ttsBackendAvailable.value) {
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
      if (!(selectedTtsEngine.value === 'python' && ttsBackendAvailable.value)) {
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
      await refreshTtsCapability()
    }
  )

  onMounted(async () => {
    initTtsPlayback()
    loadTtsEnabled()
    loadSelectedTtsEngine()
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
    workbenchMode,
    workbenchProfile,
    isAgentPreviewLayout,
    hasIwpRequirements,
    surfaceMode,
    workbenchLayoutVariant,
    isAssistantCompactSurface,
    setWorkbenchMode,
    setChatInput,
    previewWidthPx,
    agentLogHeightPx,
    isResizingPreview,
    isResizingAgentLog,
    startResizePreview,
    startResizeAgentLog,
    ttsEnabled,
    selectedTtsEngine,
    ttsEngineOptions,
    ttsPlaybackState,
    ttsStreamStatus,
    ttsCurrentTaskId,
    toggleTtsEnabled,
    selectTtsEngine,
    stopTtsPlayback,
    handleCapabilityInvokeRequest,
    handleHostInvokeRequest,
  }
}
