import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

const routeRef = ref({
  params: { pluginId: 'com.test.plugin' },
  query: { from: '/app/apps' },
})

const stopAndExit = vi.fn(async () => {})
const saveCurrentFile = vi.fn(async () => {})
const isDirtyRef = ref(false)
const isStreamingRef = ref(false)
const previewInstalledAppsRef = ref<any[]>([{ id: 'com.test.plugin' }])
const previewActiveAppRef = ref({
  id: 'com.test.plugin',
  name: 'Demo',
  app_type: 'web',
  preview: { url: 'http://127.0.0.1:5173', log_session_id: 'log-1', install_status: 'idle', has_iwp_requirements: true },
})
const facadeLoadAppsMock = vi.fn(async () => {})
const facadeRefreshPreviewStatusMock = vi.fn(async () => {})
const activeLifecycleTaskRef = ref<any>(null)
const {
  onBeforeRouteLeaveMock,
  routerPushMock,
  runLifecycleOperationMock,
  getSessionMock,
  openLifecycleModalMock,
  finalizeActiveLifecycleTaskMock,
  hostTtsStartSpeak,
  hostTtsWaitForPlaybackCompletion,
  getTtsCapabilityMock,
  getTtsTaskStatusMock,
  getAzureTtsConfigStatusMock,
  validateAzureTtsConfigMock,
  saveAzureTtsConfigMock,
  getDawnTtsStatusMock,
} = vi.hoisted(() => ({
  onBeforeRouteLeaveMock: vi.fn(),
  routerPushMock: vi.fn(async () => {}),
  runLifecycleOperationMock: vi.fn(async () => ({
    task_id: 'create-task-1',
    operation_type: 'create_dev_session',
    plugin_id: 'com.test.created-assistant',
    app_type: 'desktop',
    status: 'completed',
    created_at: '',
    updated_at: '',
    elapsed_seconds: 0,
    progress: {
      stage: 'completed',
      stage_label: 'completed',
      progress: 100,
      message: 'done',
    },
    result: { plugin_id: 'com.test.created-assistant' },
  })),
  getSessionMock: vi.fn(async () => ({
    user: { id: 'user-1', email: 'tester@example.com' },
  })),
  openLifecycleModalMock: vi.fn(),
  finalizeActiveLifecycleTaskMock: vi.fn(),
  hostTtsStartSpeak: vi.fn(async () => 'task-voice-1'),
  hostTtsWaitForPlaybackCompletion: vi.fn(async () => {}),
  getTtsCapabilityMock: vi.fn(async () => ({
    status: 'success',
    data: {
      available: true,
    },
  })),
  getTtsTaskStatusMock: vi.fn(async () => ({
    status: 'success',
    data: {
      status: 'completed',
    },
  })),
  getAzureTtsConfigStatusMock: vi.fn(async () => ({
    status: 'success',
    data: {
      configured: false,
      api_key_configured: false,
      region: '',
      voice: 'zh-CN-XiaoxiaoNeural',
      default_voice_zh: 'zh-CN-XiaoxiaoNeural',
      default_voice_en: 'en-US-JennyNeural',
    },
  })),
  validateAzureTtsConfigMock: vi.fn(async () => ({ ok: true })),
  saveAzureTtsConfigMock: vi.fn(async () => ({ ok: true })),
  getDawnTtsStatusMock: vi.fn(async () => ({
    status: 'success',
    data: {
      available: false,
      reason: 'not_logged_in',
      default_voice_zh: 'zh-CN-XiaoxiaoNeural',
      default_voice_en: 'en-US-JennyNeural',
    },
  })),
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeRef.value,
  useRouter: () => ({ replace: vi.fn(), push: routerPushMock }),
  onBeforeRouteLeave: onBeforeRouteLeaveMock,
}))

vi.mock('@/features/plugin-shared/navigation/usePluginBackTarget', () => ({
  usePluginBackTarget: () => ({ redirectToAppsInstalled: vi.fn() }),
}))

vi.mock('@/features/plugin-dev-workbench/services/devWorkbenchFacade', () => ({
  useDevWorkbenchFacade: () => ({
    rememberBuildHubRecentSession: vi.fn(),
    closeApp: vi.fn(),
    updateAppDisplayName: vi.fn(async () => null),
    runLifecycleOperation: runLifecycleOperationMock,
    loadApps: facadeLoadAppsMock,
    refreshPreviewStatus: facadeRefreshPreviewStatusMock,
    activeLifecycleTask: activeLifecycleTaskRef,
    openLifecycleModal: openLifecycleModalMock,
    finalizeActiveLifecycleTask: finalizeActiveLifecycleTaskMock,
  }),
}))

vi.mock('@/features/plugin-dev-workbench/composables/usePreviewSessionGuard', () => ({
  usePreviewSessionGuard: () => ({
    activeApp: previewActiveAppRef,
    activeMode: ref<'normal' | 'preview'>('preview'),
    installedApps: previewInstalledAppsRef,
    previewReady: ref(true),
    previewLoadingText: ref('loading'),
    previewPaneKey: ref(1),
    previewLifecycleTask: ref(null),
    previewLifecycleBusy: ref(false),
    previewInstallStatus: ref('idle'),
    previewInstallErrorMessage: ref(''),
    previewChatBlocked: ref(false),
    shouldPollPreviewStatus: ref(false),
    ensurePreviewRunning: vi.fn(async () => {}),
    syncActiveApp: vi.fn(),
    startPreviewStatusPolling: vi.fn(),
    stopPreviewStatusPolling: vi.fn(),
    restartPreview: vi.fn(async () => {}),
    retryInstall: vi.fn(async () => {}),
    stopAndExit,
  }),
}))

vi.mock('@/features/plugin-dev-workbench/composables/useWebPublishFlow', () => ({
  useWebPublishFlow: () => ({
    publishDialogVisible: ref(false),
    publishState: ref({ loading: false, error: null, last_status: null, active_task: null, last_result: null }),
    openPublishDialog: vi.fn(),
    closePublishDialog: vi.fn(),
    handlePublish: vi.fn(),
  }),
}))

vi.mock('@/features/plugin-dev-workbench/composables/useMobilePublishFlow', () => ({
  useMobilePublishFlow: () => ({
    mobileQrDialogVisible: ref(false),
    mobileOfflineDialogVisible: ref(false),
    mobileShareUrl: ref(''),
    mobileLanIp: ref(''),
    mobileQrLoading: ref(false),
    mobileQrError: ref(null),
    mobilePublishState: ref({ loading: false, error: null, last_status: null, active_task: null, last_result: null }),
    openMobilePreviewQr: vi.fn(),
    openMobileOfflinePlaceholder: vi.fn(),
    closeMobileQr: vi.fn(),
    closeMobileOffline: vi.fn(),
    handleMobilePublish: vi.fn(),
    handleMobileRefreshShare: vi.fn(),
  }),
}))

vi.mock('@/features/plugin-dev-workbench/composables/useComposerContextBridge', () => ({
  useComposerContextBridge: () => ({
    handleComposerSelectionChange: vi.fn(),
    handleInspectorSelect: vi.fn(),
    handleContextPush: vi.fn(),
  }),
}))

vi.mock('@/features/plugin-dev-workbench/composables/useIwpWorkbenchFlow', () => ({
  useIwpWorkbenchFlow: () => ({
    iwpRoot: ref('InstructWare.iw'),
    fileTreeCollapsed: ref(false),
    centerPaneMode: ref<'markdown' | 'readonly'>('markdown'),
    filesLoading: ref(false),
    fileList: ref([]),
    activeFilePath: ref('requirements/spec.md'),
    markdownContent: ref('# spec'),
    fileLoading: ref(false),
    fileSaving: ref(false),
    buildState: ref({ status: 'idle', sessionId: '', stage: '', message: '', error: '' }),
    isDirty: isDirtyRef,
    hasActiveFile: ref(true),
    canBuild: ref(false),
    loadFileList: vi.fn(async () => {}),
    openFile: vi.fn(async () => {}),
    saveCurrentFile,
    updateContent: vi.fn(),
    toggleFileTree: vi.fn(),
    setCenterPaneMode: vi.fn(),
    triggerBuild: vi.fn(async () => {}),
    readonlyFilePath: ref(''),
    readonlyFileLine: ref(0),
    readonlyFileContent: ref(''),
    readonlyLoading: ref(false),
    readonlyError: ref(''),
    openReadonlyByInspector: vi.fn(async () => {}),
    backToMarkdown: vi.fn(),
    reset: vi.fn(),
  }),
}))

vi.mock('@/features/coding-agent/store/codingAgentStore', () => ({
  useCodingAgentStore: () => ({
    isStreaming: isStreamingRef,
    ensureReadyWithWorkspace: vi.fn(async () => {}),
    dispose: vi.fn(),
  }),
}))

vi.mock('@/features/plugin-dev-workbench/composables/useWorkbenchLayoutState', () => ({
  useWorkbenchLayoutState: () => ({
    previewWidthPx: ref(460),
    agentLogHeightPx: ref(188),
    isResizingPreview: ref(false),
    isResizingAgentLog: ref(false),
    startResizePreview: vi.fn(),
    startResizeAgentLog: vi.fn(),
    persistState: vi.fn(),
  }),
}))

vi.mock('@/features/coding-agent/tts/useHostTtsPlayback', () => ({
  useHostTtsPlayback: () => ({
    init: vi.fn(),
    dispose: vi.fn(async () => {}),
    currentTaskId: ref(''),
    streamStatus: ref<'idle' | 'connecting' | 'reconnecting' | 'streaming' | 'closed'>('idle'),
    playbackState: ref('idle'),
    startSpeak: hostTtsStartSpeak,
    attachTask: vi.fn(async () => {}),
    syncStopped: vi.fn(async () => {}),
    stopSpeak: vi.fn(async () => {}),
    waitForPlaybackCompletion: hostTtsWaitForPlaybackCompletion,
  }),
}))

vi.mock('@/services/tts/ttsClient', () => ({
  getAzureTtsConfigStatus: getAzureTtsConfigStatusMock,
  validateAzureTtsConfig: validateAzureTtsConfigMock,
  saveAzureTtsConfig: saveAzureTtsConfigMock,
  getDawnTtsStatus: getDawnTtsStatusMock,
  validateDawnTtsVoiceConfig: vi.fn(async () => ({ ok: true })),
  saveDawnTtsVoiceConfig: vi.fn(async () => ({ ok: true })),
  getTtsCapability: getTtsCapabilityMock,
  getTtsTaskStatus: getTtsTaskStatusMock,
}))

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: ref({
      apps: {
        starting: '启动中',
        workbenchRenameSuccess: '重命名成功',
        workbenchRenameFailed: '重命名失败',
        workbenchRenameNameRequired: '名称不能为空',
        workbenchCloseRunningWarning: '会话会保留但预览会停止',
        workbenchCloseSaveFailed: '保存失败',
        quickCreateAssistantName: '我的 AI 助手',
        workbenchCreateAssistantAuthRequired: '请先登录',
        workbenchCreateAssistantLaunching: '创建完成，打开中...',
        workbenchCreateAssistantCreated: '助手已创建',
        workbenchCreateAssistantPreparingPreview: '助手已创建，正在准备预览...',
        workbenchCreateAssistantPreviewStarting: '正在启动预览...',
        workbenchCreateAssistantPreviewWaitingStage: '等待预览可用',
        workbenchCreateAssistantPreviewWaiting: '正在检查预览...',
        workbenchCreateAssistantPreviewReadyStage: '预览已就绪',
        workbenchCreateAssistantPreviewReady: '预览已就绪，打开中...',
        workbenchCreateAssistantPreviewFailed: '预览未就绪',
        workbenchCreateAssistantFailed: '创建失败',
        workbenchCreateAssistantNavigationFailed: '已创建但跳转失败',
      },
    }),
    locale: ref('zh-CN'),
  }),
}))

vi.mock('@/composables/useTheme', () => ({
  useTheme: () => ({ theme: ref('dark') }),
}))

vi.mock('@/shared/composables/supabaseClient', () => ({
  useSupabase: () => ({ getSession: getSessionMock }),
}))

import { usePluginDevWorkbenchOrchestration } from '../usePluginDevWorkbenchOrchestration'

describe('usePluginDevWorkbenchOrchestration close flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    isDirtyRef.value = false
    isStreamingRef.value = false
    hostTtsStartSpeak.mockResolvedValue('task-voice-1')
    hostTtsWaitForPlaybackCompletion.mockResolvedValue(undefined)
    getTtsCapabilityMock.mockResolvedValue({
      status: 'success',
      data: {
        available: true,
      },
    })
    getTtsTaskStatusMock.mockResolvedValue({
      status: 'success',
      data: {
        status: 'completed',
      },
    })
    getAzureTtsConfigStatusMock.mockResolvedValue({
      status: 'success',
      data: {
        configured: false,
        api_key_configured: false,
        region: '',
        voice: 'zh-CN-XiaoxiaoNeural',
        default_voice_zh: 'zh-CN-XiaoxiaoNeural',
        default_voice_en: 'en-US-JennyNeural',
      },
    })
    routeRef.value.params.pluginId = 'com.test.plugin'
    previewInstalledAppsRef.value = [{ id: 'com.test.plugin' }]
    previewActiveAppRef.value = {
      id: 'com.test.plugin',
      name: 'Demo',
      app_type: 'web',
      preview: { url: 'http://127.0.0.1:5173', log_session_id: 'log-1', install_status: 'idle', has_iwp_requirements: true },
    }
    activeLifecycleTaskRef.value = null
    facadeLoadAppsMock.mockReset()
    facadeRefreshPreviewStatusMock.mockReset()
    openLifecycleModalMock.mockReset()
    finalizeActiveLifecycleTaskMock.mockReset()
  })

  it('无阻断时直接退出', async () => {
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })
    const wrapper = mount(Harness)
    const result = await (wrapper.vm as any).handleCloseWorkbench()
    expect(result).toBe(true)
    expect(stopAndExit).toHaveBeenCalledWith('com.test.plugin')
  })

  it('有未保存与运行中时弹窗并支持保存后退出', async () => {
    isDirtyRef.value = true
    isStreamingRef.value = true
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })
    const wrapper = mount(Harness)
    const closePromise = (wrapper.vm as any).handleCloseWorkbench()
    await nextTick()

    expect((wrapper.vm as any).exitDialogVisible).toBe(true)
    expect((wrapper.vm as any).exitWarningMessage).toBeTruthy()

    ;(wrapper.vm as any).handleExitSaveAndClose()
    const result = await closePromise
    expect(result).toBe(true)
    expect(saveCurrentFile).toHaveBeenCalled()
    expect(stopAndExit).toHaveBeenCalledWith('com.test.plugin')
  })

  it('阻断未确认关闭的异常路由离开', async () => {
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })
    mount(Harness)
    const leaveGuard = onBeforeRouteLeaveMock.mock.calls.at(-1)?.[0]
    expect(leaveGuard).toBeTypeOf('function')
    const allowed = await leaveGuard({ name: 'apps', fullPath: '/app/apps/hub' })
    expect(allowed).toBe(false)
    expect(stopAndExit).not.toHaveBeenCalled()
  })

  it('允许登录路由离开', async () => {
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })
    mount(Harness)
    const leaveGuard = onBeforeRouteLeaveMock.mock.calls.at(-1)?.[0]
    expect(leaveGuard).toBeTypeOf('function')
    const allowed = await leaveGuard({ name: 'login', fullPath: '/login' })
    expect(allowed).toBe(true)
  })

  it('dawnchat.host.voice.speak 会在播放完成后才返回成功', async () => {
    let resolvePlayback: (() => void) | null = null
    hostTtsWaitForPlaybackCompletion.mockImplementation(
      async () =>
        await new Promise<void>((resolve) => {
          resolvePlayback = resolve
        })
    )
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })
    const wrapper = mount(Harness)
    await vi.waitFor(() => {
      const options = (wrapper.vm as any).ttsEngineOptions.map((item: { id: string }) => item.id)
      expect(options).toContain('python')
    })
    await (wrapper.vm as any).selectTtsEngine('python')
    await Promise.resolve()
    let settled = false
    const invokePromise = (wrapper.vm as any).handleHostInvokeRequest({
      invoke: {
        functionName: 'dawnchat.host.voice.speak',
        payload: {
          text: '长讲解文本',
        },
      },
    }).then((result: Record<string, unknown>) => {
      settled = true
      return result
    })
    await vi.waitFor(() => {
      expect(hostTtsStartSpeak).toHaveBeenCalledWith(
        expect.objectContaining({
          plugin_id: 'com.test.plugin',
          text: '长讲解文本',
        })
      )
    })
    expect(settled).toBe(false)
    expect(getTtsTaskStatusMock).toHaveBeenCalledWith('task-voice-1')
    await vi.waitFor(() => {
      expect(hostTtsWaitForPlaybackCompletion).toHaveBeenCalledWith('task-voice-1', 120000)
    })
    const playbackResolver = resolvePlayback as (() => void) | null
    expect(playbackResolver).toBeTypeOf('function')
    if (playbackResolver) {
      playbackResolver()
    }
    await expect(invokePromise).resolves.toEqual(
      expect.objectContaining({
        ok: true,
        data: expect.objectContaining({
          task_id: 'task-voice-1',
          status: 'completed',
          engine: 'python',
        }),
      })
    )
  })
})
