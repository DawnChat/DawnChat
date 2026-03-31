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

vi.mock('vue-router', () => ({
  useRoute: () => routeRef.value,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  onBeforeRouteLeave: vi.fn(),
}))

vi.mock('@/features/plugin-shared/navigation/usePluginBackTarget', () => ({
  usePluginBackTarget: () => ({ redirectToAppsInstalled: vi.fn() }),
}))

vi.mock('@/features/plugin-dev-workbench/services/devWorkbenchFacade', () => ({
  useDevWorkbenchFacade: () => ({
    rememberBuildHubRecentSession,
    closeApp,
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
        workbenchCloseRunningWarning: '运行中',
        workbenchCloseSaveFailed: '保存失败',
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

vi.mock('@/services/tts/ttsClient', () => ({
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
    activeModeRef.value = 'normal'
    installedAppsRef.value = [
      {
        id: 'com.test.plugin',
        preview: { workbench_layout: 'default', has_iwp_requirements: true },
      },
    ]
    shouldPollPreviewStatusRef.value = false
    routeRef.value.query = { from: '/app/apps' }
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
})
