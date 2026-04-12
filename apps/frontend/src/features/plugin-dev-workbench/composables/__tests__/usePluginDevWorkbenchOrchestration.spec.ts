import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

const routeRef = ref<any>({
  params: { pluginId: 'com.test.plugin' },
  query: { from: '/app/apps' },
})

const ensurePreviewRunning = vi.fn(async () => {})
const syncActiveApp = vi.fn()
const startPreviewStatusPolling = vi.fn()
const stopPreviewStatusPolling = vi.fn()
const restartPreview = vi.fn(async () => {})
const retryInstall = vi.fn(async () => {})
const stopAndExit = vi.fn(async () => {})
const rememberBuildHubRecentSession = vi.fn()
const closeApp = vi.fn()

const activeModeRef = ref<'normal' | 'preview'>('normal')
const installedAppsRef = ref<any[]>([
  {
    id: 'com.test.plugin',
    preview: { workbench_layout: 'default', has_iwp_requirements: true },
  },
])
const shouldPollPreviewStatusRef = ref(false)
const activeAppRef = ref({
  id: 'com.test.plugin',
  name: 'Demo',
  app_type: 'web',
  preview: {
    url: 'http://127.0.0.1:5173',
    log_session_id: 'log-1',
    install_status: 'idle',
    workbench_layout: 'default',
    has_iwp_requirements: true,
  },
})
const loadFileList = vi.fn(async () => {})
const routerReplace = vi.fn(async () => {})
const routerPush = vi.fn(async () => {})
const facadeLoadApps = vi.fn(async () => {})
const facadeRefreshPreviewStatus = vi.fn(async () => {})
const lifecycleRunMock = vi.fn(async () => ({
  task_id: 'task-1',
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
  error: null,
}))
const openLifecycleModalMock = vi.fn()
const finalizeActiveLifecycleTaskMock = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => routeRef.value,
  useRouter: () => ({ replace: routerReplace, push: routerPush }),
  onBeforeRouteLeave: vi.fn(),
}))

vi.mock('@/features/plugin-shared/navigation/usePluginBackTarget', () => ({
  usePluginBackTarget: () => ({ redirectToAppsInstalled: vi.fn() }),
}))

vi.mock('@/features/plugin-dev-workbench/services/devWorkbenchFacade', () => ({
  useDevWorkbenchFacade: () => ({
    rememberBuildHubRecentSession,
    closeApp,
    updateAppDisplayName: vi.fn(async () => null),
    loadApps: facadeLoadApps,
    refreshPreviewStatus: facadeRefreshPreviewStatus,
    activeLifecycleTask: ref(null),
    openLifecycleModal: openLifecycleModalMock,
    finalizeActiveLifecycleTask: finalizeActiveLifecycleTaskMock,
    runLifecycleOperation: lifecycleRunMock,
  }),
}))

vi.mock('@/features/plugin-dev-workbench/composables/usePreviewSessionGuard', () => ({
  usePreviewSessionGuard: () => ({
    activeApp: activeAppRef,
    activeMode: activeModeRef,
    installedApps: installedAppsRef,
    previewReady: ref(true),
    previewLoadingText: ref('loading'),
    previewPaneKey: ref(1),
    previewLifecycleTask: ref(null),
    previewLifecycleBusy: ref(false),
    previewInstallStatus: ref('idle'),
    previewInstallErrorMessage: ref(''),
    previewChatBlocked: ref(false),
    shouldPollPreviewStatus: shouldPollPreviewStatusRef,
    ensurePreviewRunning,
    syncActiveApp,
    startPreviewStatusPolling,
    stopPreviewStatusPolling,
    restartPreview,
    retryInstall,
    stopAndExit,
  }),
}))

vi.mock('@/features/plugin-dev-workbench/composables/useWebPublishFlow', () => ({
  useWebPublishFlow: () => ({
    publishDialogVisible: ref(false),
    publishState: ref({
      loading: false,
      error: null,
      last_status: null,
      active_task: null,
      last_result: null,
    }),
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
    mobilePublishState: ref({
      loading: false,
      error: null,
      last_status: null,
      active_task: null,
      last_result: null,
    }),
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
    isDirty: ref(false),
    hasActiveFile: ref(true),
    canBuild: ref(false),
    loadFileList,
    openFile: vi.fn(async () => {}),
    saveCurrentFile: vi.fn(async () => {}),
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

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: ref({
      apps: {
        starting: '启动中',
        publishWeb: '发布网页',
        mobilePreviewQr: '二维码',
        mobileOfflineUpload: '离线包',
        workbenchRenameSuccess: '重命名成功',
        workbenchRenameFailed: '重命名失败',
        workbenchRenameNameRequired: '名称不能为空',
        workbenchCloseRunningWarning: '运行中',
        workbenchCloseSaveFailed: '保存失败',
        quickCreateAssistantName: '我的 AI 助手',
      },
    }),
    locale: ref('zh-CN'),
  }),
}))

vi.mock('@/composables/useTheme', () => ({
  useTheme: () => ({ theme: ref('dark') }),
}))

vi.mock('@/shared/composables/supabaseClient', () => ({
  useSupabase: () => ({ getSession: vi.fn(async () => null) }),
}))

vi.mock('@/features/coding-agent/store/codingAgentStore', () => ({
  useCodingAgentStore: () => ({
    isStreaming: ref(false),
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
    streamStatus: ref('idle'),
    playbackState: ref('idle'),
    startSpeak: vi.fn(async () => 'task-voice-1'),
    attachTask: vi.fn(async () => {}),
    syncStopped: vi.fn(async () => {}),
    stopSpeak: vi.fn(async () => {}),
    waitForPlaybackCompletion: vi.fn(async () => {}),
  }),
}))

const ttsClientMocks = vi.hoisted(() => ({
  getDawnTtsStatus: vi.fn(async () => ({
    status: 'success',
    data: {
      available: true,
      reason: '',
      default_voice_zh: 'zh-CN-XiaoxiaoNeural',
      default_voice_en: 'en-US-JennyNeural',
    },
  })),
}))

vi.mock('@/services/tts/ttsClient', () => ({
  getAzureTtsConfigStatus: vi.fn(async () => ({
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
  getDawnTtsStatus: ttsClientMocks.getDawnTtsStatus,
  validateDawnTtsVoiceConfig: vi.fn(async () => ({ ok: true })),
  saveDawnTtsVoiceConfig: vi.fn(async () => ({ ok: true })),
  validateAzureTtsConfig: vi.fn(async () => ({ ok: true })),
  saveAzureTtsConfig: vi.fn(async () => ({ ok: true })),
  getTtsCapability: vi.fn(async () => ({
    status: 'success',
    data: {
      available: true,
    },
  })),
  getTtsTaskStatus: vi.fn(async () => ({
    status: 'success',
    data: {
      status: 'completed',
    },
  })),
}))

import { usePluginDevWorkbenchOrchestration } from '../usePluginDevWorkbenchOrchestration'

describe('usePluginDevWorkbenchOrchestration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    activeModeRef.value = 'normal'
    installedAppsRef.value = [
      {
        id: 'com.test.plugin',
        preview: { workbench_layout: 'default', has_iwp_requirements: true },
      },
    ]
    shouldPollPreviewStatusRef.value = false
    routeRef.value.query = { from: '/app/apps' }
    facadeLoadApps.mockClear()
    facadeRefreshPreviewStatus.mockClear()
    lifecycleRunMock.mockClear()
    openLifecycleModalMock.mockClear()
    finalizeActiveLifecycleTaskMock.mockClear()
    activeAppRef.value = {
      id: 'com.test.plugin',
      name: 'Demo',
      app_type: 'web',
      preview: {
        url: 'http://127.0.0.1:5173',
        log_session_id: 'log-1',
        install_status: 'idle',
        workbench_layout: 'default',
        has_iwp_requirements: true,
      },
    }
  })

  it('挂载时执行初始化链路', async () => {
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })

    mount(Harness)
    await vi.waitFor(() => {
      expect(activeModeRef.value).toBe('preview')
    })

    expect(rememberBuildHubRecentSession).toHaveBeenCalledWith('com.test.plugin')
    expect(ensurePreviewRunning).toHaveBeenCalled()
    expect(loadFileList).toHaveBeenCalled()
  })

  it('轮询条件变化时触发 start/stop', async () => {
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })

    const wrapper = mount(Harness)
    const initialStopCalls = stopPreviewStatusPolling.mock.calls.length
    expect(initialStopCalls).toBeGreaterThan(0)

    shouldPollPreviewStatusRef.value = true
    await nextTick()
    expect(startPreviewStatusPolling).toHaveBeenCalled()

    shouldPollPreviewStatusRef.value = false
    await nextTick()
    expect(stopPreviewStatusPolling.mock.calls.length).toBeGreaterThan(initialStopCalls)
    wrapper.unmount()
  })

  it('卸载时执行清理链路', () => {
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })

    const wrapper = mount(Harness)
    wrapper.unmount()

    expect(stopPreviewStatusPolling).toHaveBeenCalled()
    expect(closeApp).toHaveBeenCalled()
  })

  it('无 IWP 能力时默认进入 agent 并跳过文件列表加载', async () => {
    activeAppRef.value = {
      ...activeAppRef.value,
      preview: {
        ...activeAppRef.value.preview,
        workbench_layout: 'agent_preview',
        has_iwp_requirements: false,
      },
    }
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })

    const wrapper = mount(Harness)
    await vi.waitFor(() => {
      expect((wrapper.vm as any).workbenchMode).toBe('agent')
    })

    expect((wrapper.vm as any).isAgentPreviewLayout).toBe(true)
    expect((wrapper.vm as any).hasIwpRequirements).toBe(false)
    expect((wrapper.vm as any).workbenchMode).toBe('agent')
    expect(loadFileList).not.toHaveBeenCalled()
  })

  it('activeApp 未就绪时可从 installedApps 回退读取布局策略', async () => {
    activeAppRef.value = null as any
    installedAppsRef.value = [
      {
        id: 'com.test.plugin',
        preview: {
          workbench_layout: 'agent_preview',
          has_iwp_requirements: false,
        },
      },
    ]
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })

    const wrapper = mount(Harness)
    await vi.waitFor(() => {
      expect((wrapper.vm as any).workbenchMode).toBe('agent')
    })

    expect((wrapper.vm as any).isAgentPreviewLayout).toBe(true)
    expect((wrapper.vm as any).workbenchMode).toBe('agent')
  })

  it('surface=assistant_compact 时进入压缩运行形态', async () => {
    routeRef.value.query = { from: '/app/apps', surface: 'assistant_compact' }
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })

    const wrapper = mount(Harness)
    await vi.waitFor(() => {
      expect((wrapper.vm as any).surfaceMode).toBe('assistant_compact')
    })

    expect((wrapper.vm as any).surfaceMode).toBe('assistant_compact')
    expect((wrapper.vm as any).isAssistantCompactSurface).toBe(true)
  })

  it('TTS 下拉包含 Dawn（可用时首位）、Azure 与 System', async () => {
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })
    const wrapper = mount(Harness)
    await vi.waitFor(() => {
      expect((wrapper.vm as any).dawnTtsAvailable).toBe(true)
    })
    const options = (wrapper.vm as any).ttsEngineOptions.map((item: { id: string }) => item.id)
    expect(options[0]).toBe('dawn-tts')
    expect(options).toContain('azure')
    expect(options).toContain('system')
  })

  it('选择 Dawn TTS 会打开音色弹窗而不是立即切换', async () => {
    localStorage.setItem('plugin-dev-workbench.tts.engine.v1', 'python')
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })
    const wrapper = mount(Harness)
    await vi.waitFor(() => {
      expect((wrapper.vm as any).ttsEngineOptions.length).toBeGreaterThan(0)
    })
    expect((wrapper.vm as any).selectedTtsEngine).toBe('python')
    await (wrapper.vm as any).selectTtsEngine('dawn-tts')
    expect((wrapper.vm as any).azureTtsDialogVisible).toBe(true)
    expect((wrapper.vm as any).ttsVoiceConfigMode).toBe('dawn')
    expect((wrapper.vm as any).selectedTtsEngine).toBe('python')
  })

  it('选择 Azure 会打开配置弹窗而不是立即切换', async () => {
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })
    const wrapper = mount(Harness)
    await (wrapper.vm as any).selectTtsEngine('azure')
    expect((wrapper.vm as any).azureTtsDialogVisible).toBe(true)
    expect((wrapper.vm as any).selectedTtsEngine).not.toBe('azure')
  })

  it('切换预览全屏时通过 query 持久化 surface', async () => {
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })
    const wrapper = mount(Harness)
    await (wrapper.vm as any).togglePreviewFullscreen()
    expect(routerReplace).toHaveBeenCalledWith(expect.objectContaining({
      query: expect.objectContaining({
        surface: 'assistant_compact',
      }),
    }))

    routeRef.value.query = { from: '/app/apps', surface: 'assistant_compact' }
    await (wrapper.vm as any).togglePreviewFullscreen()
    expect(routerReplace).toHaveBeenLastCalledWith(expect.objectContaining({
      query: expect.not.objectContaining({
        surface: expect.anything(),
      }),
    }))
  })

  it('切换到新的 pluginId 时会重新初始化预览链路', async () => {
    const Harness = defineComponent({
      setup() {
        return usePluginDevWorkbenchOrchestration()
      },
      template: '<div />',
    })
    mount(Harness)
    await vi.waitFor(() => {
      expect(ensurePreviewRunning).toHaveBeenCalled()
    })

    ensurePreviewRunning.mockClear()
    rememberBuildHubRecentSession.mockClear()

    routeRef.value.params.pluginId = 'com.test.next-plugin'
    routeRef.value.query = { from: '/app/apps' }
    activeAppRef.value = {
      id: 'com.test.next-plugin',
      name: 'Next Demo',
      app_type: 'web',
      preview: {
        url: 'http://127.0.0.1:5174',
        log_session_id: 'log-2',
        install_status: 'idle',
        workbench_layout: 'default',
        has_iwp_requirements: false,
      },
    }
    installedAppsRef.value = [
      {
        id: 'com.test.next-plugin',
        preview: { workbench_layout: 'default', has_iwp_requirements: false },
      },
    ] as any
    await nextTick()

    await vi.waitFor(() => {
      expect(ensurePreviewRunning.mock.calls.length).toBeGreaterThan(0)
    })
    expect(rememberBuildHubRecentSession).toHaveBeenCalledWith('com.test.next-plugin')
  })
})
