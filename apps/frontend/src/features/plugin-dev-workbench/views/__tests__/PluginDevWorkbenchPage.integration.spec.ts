import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { shallowMount } from '@vue/test-utils'

const orchestrationMock = {
  t: {
    common: {
      cancel: '取消',
    },
    apps: {
      publishWeb: '发布网页',
      mobilePreviewQr: '移动端预览二维码',
      mobileOfflineUpload: '上传离线包',
      workbenchRequirementsMode: '需求模式',
      workbenchAgentMode: '协作模式',
      workbenchClose: '关闭',
      workbenchCloseConfirmTitle: '关闭开发工作台',
      workbenchCloseConfirmMessage: '确认关闭',
      workbenchCloseSaveAndExit: '保存并退出',
      workbenchCloseExitDirectly: '直接退出',
      workbenchCloseCancel: '取消',
      workbenchRenameAction: '修改应用名称',
      workbenchRenameSave: '保存名称',
      workbenchRenameCancel: '取消修改',
      workbenchRenamePlaceholder: '请输入应用名称',
      iwpOpenBuildSession: '打开会话',
      iwpSave: '保存',
      iwpSaving: '保存中',
      iwpBuild: 'Build',
      iwpLoadingFile: '加载中',
      iwpEditorPlaceholder: 'placeholder',
      iwpEmptyFile: 'empty',
      iwpSaved: 'saved',
      iwpUnsaved: 'unsaved',
      iwpBuildSessionLabel: 'Build 会话: {id}',
      iwpReadonlyTitle: '只读',
      iwpBackToMarkdown: '返回',
      iwpReadonlyLoading: '加载源码',
      iwpReadonlyEmpty: 'empty',
      workbenchAgentLogTitle: '日志',
      workbenchAgentLogEmpty: '空',
      workbenchAgentLogRunning: '运行中',
      workbenchAgentLogIdle: '空闲',
      iwpFilesTitle: '文件',
      iwpLoadingFiles: '加载列表',
      iwpNoFiles: '空文件',
      iwpBuilding: '构建中',
      blockedByDepsInstall: '依赖准备中',
    },
  },
  chatInput: '',
  activeApp: { name: 'Test App', version: '1.0.0', description: 'desc', app_type: 'web' },
  pluginId: 'com.test.app',
  appTypeLabel: 'Web',
  isWebApp: true,
  isMobileApp: false,
  isPreviewRenderable: true,
  previewPaneKey: 1,
  pluginUrl: 'http://127.0.0.1:17961',
  previewLogSessionId: '',
  previewLifecycleTask: null,
  previewLifecycleBusy: false,
  previewInstallStatus: 'idle' as const,
  previewInstallErrorMessage: '',
  previewLoadingText: '启动中',
  workbenchMode: 'requirements' as const,
  workbenchProfile: {
    isAgentPreview: false,
  },
  workbenchLayoutVariant: 'split_with_iwp' as const,
  hasIwpRequirements: true,
  isAssistantCompactSurface: false,
  previewChatBlocked: false,
  publishDialogVisible: false,
  publishState: { loading: false, error: null, last_status: null, active_task: null, last_result: null },
  mobileQrDialogVisible: false,
  mobileShareUrl: '',
  mobileLanIp: '',
  mobileQrLoading: false,
  mobileQrError: null,
  mobileOfflineDialogVisible: false,
  mobilePublishState: { loading: false, error: null, last_status: null, active_task: null, last_result: null },
  publishToast: { visible: false, message: '', kind: 'success' as const },
  openPublishDialog: vi.fn(),
  closePublishDialog: vi.fn(),
  openMobilePreviewQr: vi.fn(),
  openMobileOfflinePlaceholder: vi.fn(),
  closeMobileQr: vi.fn(),
  closeMobileOffline: vi.fn(),
  handleCloseWorkbench: vi.fn(),
  handleExitSaveAndClose: vi.fn(),
  handleExitDirectly: vi.fn(),
  handleExitCancel: vi.fn(),
  exitDialogVisible: false,
  exitBusy: false,
  exitWarningMessage: '',
  handleRestartPreview: vi.fn(),
  handleRetryInstall: vi.fn(),
  handleInspectorSelect: vi.fn(),
  handleContextPush: vi.fn(),
  handleComposerSelectionChange: vi.fn(),
  handlePublish: vi.fn(),
  handleMobilePublish: vi.fn(),
  handleMobileRefreshShare: vi.fn(),
  iwpRoot: 'InstructWare.iw',
  fileTreeCollapsed: false,
  centerPaneMode: 'markdown' as const,
  filesLoading: false,
  fileList: [],
  activeFilePath: 'requirements/spec.md',
  markdownContent: '# spec',
  fileLoading: false,
  fileSaving: false,
  buildState: { status: 'idle' as const, sessionId: '', message: '', error: '' },
  isDirty: false,
  hasActiveFile: true,
  canBuild: false,
  loadFileList: vi.fn(),
  openFile: vi.fn(),
  saveCurrentFile: vi.fn(),
  updateContent: vi.fn(),
  toggleFileTree: vi.fn(),
  setCenterPaneMode: vi.fn(),
  triggerBuild: vi.fn(),
  readonlyFilePath: '',
  readonlyFileLine: 0,
  readonlyFileContent: '',
  readonlyLoading: false,
  readonlyError: '',
  backToMarkdown: vi.fn(),
  openBuildSession: vi.fn(),
  hasBuildSession: false,
  isBuildRunning: false,
  renamingApp: false,
  renameActiveApp: vi.fn(async () => true),
  setWorkbenchMode: vi.fn(),
  setChatInput: vi.fn(),
  togglePreviewFullscreen: vi.fn(),
  previewWidthPx: 460,
  agentLogHeightPx: 188,
  isResizingPreview: false,
  isResizingAgentLog: false,
  startResizePreview: vi.fn(),
  startResizeAgentLog: vi.fn(),
}

vi.mock('@/features/plugin-dev-workbench/composables/usePluginDevWorkbenchOrchestration', () => ({
  usePluginDevWorkbenchOrchestration: () => orchestrationMock,
}))

import PluginDevWorkbenchPage from '@/features/plugin-dev-workbench/views/PluginDevWorkbenchPage.vue'

const HeaderStub = defineComponent({
  name: 'WorkbenchHeaderBar',
  props: ['isWebApp', 'isMobileApp', 'appTypeLabel', 'showModeSwitch'],
  emits: ['openWebPublish', 'openMobileQr', 'openMobileOffline', 'switchMode', 'openBuildSession', 'close', 'renameApp'],
  template: '<div />',
})

const PreviewStub = defineComponent({
  name: 'WorkbenchPreviewSection',
  props: ['isPreviewRenderable', 'previewLoadingText', 'showCompactShell'],
  emits: ['restart', 'toggleFullscreen', 'retryInstall', 'inspectorSelect', 'contextPush'],
  template: '<div />',
})

const OverlaysStub = defineComponent({
  name: 'WorkbenchPublishOverlays',
  emits: [
    'closeWebPublish',
    'closeMobileQr',
    'closeMobileOffline',
    'submitWebPublish',
    'submitMobilePublish',
    'refreshMobileShare',
  ],
  template: '<div />',
})

const SplitWithIwpStub = defineComponent({
  name: 'WorkbenchSplitWithIwpLayout',
  emits: [
    'toggleFileTree',
    'openFile',
    'composerSelectionChange',
    'updateChatInput',
    'updateMarkdown',
    'saveMarkdown',
    'triggerBuild',
    'openBuildSession',
    'backToMarkdown',
    'startResizeAgentLog',
  ],
  template: '<div />',
})

const SplitNoIwpStub = defineComponent({
  name: 'WorkbenchSplitNoIwpLayout',
  emits: [
    'composerSelectionChange',
    'updateChatInput',
    'updateMarkdown',
    'saveMarkdown',
    'triggerBuild',
    'openBuildSession',
    'backToMarkdown',
    'startResizeAgentLog',
  ],
  template: '<div />',
})

describe('PluginDevWorkbenchPage integration', () => {
  beforeEach(() => {
    orchestrationMock.isWebApp = true
    orchestrationMock.isMobileApp = false
    orchestrationMock.appTypeLabel = 'Web'
    orchestrationMock.activeApp = { name: 'Test App', version: '1.0.0', description: 'desc', app_type: 'web' }
    orchestrationMock.isPreviewRenderable = true
    orchestrationMock.workbenchProfile = {
      isAgentPreview: false,
    }
    orchestrationMock.workbenchLayoutVariant = 'split_with_iwp'
    orchestrationMock.hasIwpRequirements = true
    orchestrationMock.isAssistantCompactSurface = false
    vi.clearAllMocks()
  })

  it('转发 Header 事件到 orchestration', async () => {
    const wrapper = shallowMount(PluginDevWorkbenchPage, {
      global: {
        stubs: {
          WorkbenchHeaderBar: HeaderStub,
          WorkbenchPreviewSection: PreviewStub,
          WorkbenchPublishOverlays: OverlaysStub,
          WorkbenchSplitWithIwpLayout: SplitWithIwpStub,
          WorkbenchSplitNoIwpLayout: SplitNoIwpStub,
        },
      },
    })

    const header = wrapper.findComponent(HeaderStub)
    header.vm.$emit('openWebPublish')
    header.vm.$emit('openMobileQr')
    header.vm.$emit('openMobileOffline')
    header.vm.$emit('switchMode', 'agent')
    header.vm.$emit('openBuildSession')
    header.vm.$emit('renameApp', 'New App')
    header.vm.$emit('close')
    await Promise.resolve()

    expect(orchestrationMock.openPublishDialog).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.openMobilePreviewQr).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.openMobileOfflinePlaceholder).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.setWorkbenchMode).toHaveBeenCalledWith('agent')
    expect(orchestrationMock.openBuildSession).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.renameActiveApp).toHaveBeenCalledWith('New App')
    expect(orchestrationMock.handleCloseWorkbench).toHaveBeenCalledTimes(1)
  })

  it('转发 Preview 和 Chat 事件到 orchestration', async () => {
    const wrapper = shallowMount(PluginDevWorkbenchPage, {
      global: {
        stubs: {
          WorkbenchHeaderBar: HeaderStub,
          WorkbenchPreviewSection: PreviewStub,
          WorkbenchPublishOverlays: OverlaysStub,
          WorkbenchSplitWithIwpLayout: SplitWithIwpStub,
          WorkbenchSplitNoIwpLayout: SplitNoIwpStub,
        },
      },
    })

    const preview = wrapper.findComponent(PreviewStub)
    const split = wrapper.findComponent(SplitWithIwpStub)
    const inspectorPayload = { file: 'a.vue', line: 12, column: 8 }
    const contextPayload = { content: 'ctx', source: 'inspector' }
    const selectionPayload = { text: 'selected', range: [0, 8] }

    preview.vm.$emit('restart', 'com.test.app')
    preview.vm.$emit('toggleFullscreen')
    preview.vm.$emit('retryInstall')
    preview.vm.$emit('inspectorSelect', inspectorPayload)
    preview.vm.$emit('contextPush', contextPayload)
    split.vm.$emit('composerSelectionChange', selectionPayload)
    split.vm.$emit('updateMarkdown', '# updated')
    split.vm.$emit('saveMarkdown')
    split.vm.$emit('triggerBuild')
    split.vm.$emit('backToMarkdown')
    split.vm.$emit('startResizeAgentLog', new PointerEvent('pointerdown'))
    await Promise.resolve()

    expect(orchestrationMock.handleRestartPreview).toHaveBeenCalledWith('com.test.app')
    expect(orchestrationMock.togglePreviewFullscreen).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.handleRetryInstall).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.handleInspectorSelect).toHaveBeenCalledWith(inspectorPayload)
    expect(orchestrationMock.handleContextPush).toHaveBeenCalledWith(contextPayload)
    expect(orchestrationMock.handleComposerSelectionChange).toHaveBeenCalledWith(selectionPayload)
    expect(orchestrationMock.updateContent).toHaveBeenCalledWith('# updated')
    expect(orchestrationMock.saveCurrentFile).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.triggerBuild).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.backToMarkdown).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.startResizeAgentLog).toHaveBeenCalledTimes(1)
  })

  it('转发 PublishOverlays 事件到 orchestration', async () => {
    const wrapper = shallowMount(PluginDevWorkbenchPage, {
      global: {
        stubs: {
          WorkbenchHeaderBar: HeaderStub,
          WorkbenchPreviewSection: PreviewStub,
          WorkbenchPublishOverlays: OverlaysStub,
          WorkbenchSplitWithIwpLayout: SplitWithIwpStub,
          WorkbenchSplitNoIwpLayout: SplitNoIwpStub,
        },
      },
    })

    const overlays = wrapper.findComponent(OverlaysStub)
    const webPayload = {
      slug: 'test-app',
      title: 'Test App',
      version: '1.0.0',
      description: 'desc',
      initial_visibility: 'public' as const,
    }
    const mobilePayload = { version: '1.0.1' }

    overlays.vm.$emit('closeWebPublish')
    overlays.vm.$emit('closeMobileQr')
    overlays.vm.$emit('closeMobileOffline')
    overlays.vm.$emit('submitWebPublish', webPayload)
    overlays.vm.$emit('submitMobilePublish', mobilePayload)
    overlays.vm.$emit('refreshMobileShare')
    await Promise.resolve()

    expect(orchestrationMock.closePublishDialog).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.closeMobileQr).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.closeMobileOffline).toHaveBeenCalledTimes(1)
    expect(orchestrationMock.handlePublish).toHaveBeenCalledWith(webPayload)
    expect(orchestrationMock.handleMobilePublish).toHaveBeenCalledWith(mobilePayload)
    expect(orchestrationMock.handleMobileRefreshShare).toHaveBeenCalledTimes(1)
  })

  it('在 web/mobile/desktop 场景传递稳定展示状态', () => {
    const scenarios = [
      { isWebApp: true, isMobileApp: false, appTypeLabel: 'Web' },
      { isWebApp: false, isMobileApp: true, appTypeLabel: 'Mobile' },
      { isWebApp: false, isMobileApp: false, appTypeLabel: 'Desktop' },
    ]

    for (const scenario of scenarios) {
      orchestrationMock.isWebApp = scenario.isWebApp
      orchestrationMock.isMobileApp = scenario.isMobileApp
      orchestrationMock.appTypeLabel = scenario.appTypeLabel
      const wrapper = shallowMount(PluginDevWorkbenchPage, {
        global: {
          stubs: {
            WorkbenchHeaderBar: HeaderStub,
            WorkbenchPreviewSection: PreviewStub,
            WorkbenchPublishOverlays: OverlaysStub,
            WorkbenchSplitWithIwpLayout: SplitWithIwpStub,
            WorkbenchSplitNoIwpLayout: SplitNoIwpStub,
          },
        },
      })
      const header = wrapper.findComponent(HeaderStub)
      expect(header.props('isWebApp')).toBe(scenario.isWebApp)
      expect(header.props('isMobileApp')).toBe(scenario.isMobileApp)
      expect(header.props('appTypeLabel')).toBe(scenario.appTypeLabel)
    }
  })

  it('在不可渲染预览时向 PreviewSection 传递 loading 分支参数', () => {
    orchestrationMock.isPreviewRenderable = false
    orchestrationMock.previewLoadingText = '预览启动中'
    const wrapper = shallowMount(PluginDevWorkbenchPage, {
      global: {
        stubs: {
          WorkbenchHeaderBar: HeaderStub,
          WorkbenchPreviewSection: PreviewStub,
          WorkbenchPublishOverlays: OverlaysStub,
          WorkbenchSplitWithIwpLayout: SplitWithIwpStub,
          WorkbenchSplitNoIwpLayout: SplitNoIwpStub,
        },
      },
    })
    const preview = wrapper.findComponent(PreviewStub)
    expect(preview.props('isPreviewRenderable')).toBe(false)
    expect(preview.props('previewLoadingText')).toBe('预览启动中')
  })

  it('无 IWP 能力时隐藏文件树并关闭模式切换入口', () => {
    orchestrationMock.workbenchProfile = {
      isAgentPreview: true,
    }
    orchestrationMock.workbenchLayoutVariant = 'agent_preview'
    orchestrationMock.hasIwpRequirements = false
    const wrapper = shallowMount(PluginDevWorkbenchPage, {
      global: {
        stubs: {
          WorkbenchHeaderBar: HeaderStub,
          WorkbenchPreviewSection: PreviewStub,
          WorkbenchPublishOverlays: OverlaysStub,
          WorkbenchSplitWithIwpLayout: SplitWithIwpStub,
          WorkbenchSplitNoIwpLayout: SplitNoIwpStub,
        },
      },
    })
    const header = wrapper.findComponent(HeaderStub)
    expect(header.props('showModeSwitch')).toBe(false)
    expect(wrapper.findComponent(SplitWithIwpStub).exists()).toBe(false)
    expect(wrapper.findComponent(SplitNoIwpStub).exists()).toBe(true)
    expect(wrapper.find('.plugin-dev-workbench').classes()).toContain('agent-preview-layout')
  })

  it('assistant_compact 形态下隐藏中栏并启用 compact shell', () => {
    orchestrationMock.workbenchLayoutVariant = 'compact'
    orchestrationMock.isAssistantCompactSurface = true
    orchestrationMock.hasIwpRequirements = false
    const wrapper = shallowMount(PluginDevWorkbenchPage, {
      global: {
        stubs: {
          WorkbenchHeaderBar: HeaderStub,
          WorkbenchPreviewSection: PreviewStub,
          WorkbenchPublishOverlays: OverlaysStub,
          WorkbenchSplitWithIwpLayout: SplitWithIwpStub,
          WorkbenchSplitNoIwpLayout: SplitNoIwpStub,
        },
      },
    })
    expect(wrapper.findComponent(SplitWithIwpStub).exists()).toBe(false)
    expect(wrapper.findComponent(SplitNoIwpStub).exists()).toBe(false)
    expect(wrapper.findComponent(HeaderStub).exists()).toBe(false)
    const preview = wrapper.findComponent(PreviewStub)
    expect(preview.props('showCompactShell')).toBe(true)
    expect(wrapper.find('.plugin-dev-workbench').classes()).toContain('assistant-compact-layout')
    expect(wrapper.find('.plugin-dev-workbench').classes()).toContain('preview-fullscreen-layout')
  })

  it('split_with_iwp 形态仅渲染三栏容器', () => {
    orchestrationMock.workbenchLayoutVariant = 'split_with_iwp'
    const wrapper = shallowMount(PluginDevWorkbenchPage, {
      global: {
        stubs: {
          WorkbenchHeaderBar: HeaderStub,
          WorkbenchPreviewSection: PreviewStub,
          WorkbenchPublishOverlays: OverlaysStub,
          WorkbenchSplitWithIwpLayout: SplitWithIwpStub,
          WorkbenchSplitNoIwpLayout: SplitNoIwpStub,
        },
      },
    })
    expect(wrapper.findComponent(SplitWithIwpStub).exists()).toBe(true)
    expect(wrapper.findComponent(SplitNoIwpStub).exists()).toBe(false)
  })
})
