import { describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'

vi.mock('@/features/plugin-dev-workbench/composables/usePluginDevWorkbenchOrchestration', () => ({
  usePluginDevWorkbenchOrchestration: () => ({
    t: {
      apps: {
        publishWeb: '发布网页',
        mobilePreviewQr: '移动端预览二维码',
        mobileOfflineUpload: '上传离线包',
        workbenchRequirementsMode: '需求模式',
        workbenchAgentMode: '协作模式',
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
      },
    },
    chatInput: '',
    activeApp: { name: 'Mobile Test', version: '0.1.0', description: '', app_type: 'mobile' },
    pluginId: 'com.test.mobile',
    appTypeLabel: 'Mobile',
    isWebApp: false,
    isMobileApp: true,
    isPreviewRenderable: true,
    previewPaneKey: 1,
    pluginUrl: 'http://127.0.0.1:17961',
    previewLogSessionId: '',
    previewLifecycleTask: null,
    previewLifecycleBusy: false,
    previewInstallStatus: 'idle',
    previewInstallErrorMessage: '',
    previewLoadingText: '启动中',
    workbenchMode: 'requirements',
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
    publishToast: { visible: false, message: '', kind: 'success' },
    openPublishDialog: vi.fn(),
    closePublishDialog: vi.fn(),
    openMobilePreviewQr: vi.fn(),
    openMobileOfflinePlaceholder: vi.fn(),
    closeMobileQr: vi.fn(),
    closeMobileOffline: vi.fn(),
    handleStop: vi.fn(),
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
    centerPaneMode: 'markdown',
    filesLoading: false,
    fileList: [],
    activeFilePath: 'requirements/spec.md',
    markdownContent: '# spec',
    fileLoading: false,
    fileSaving: false,
    buildState: { status: 'idle', sessionId: '', message: '', error: '' },
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
    setWorkbenchMode: vi.fn(),
    setChatInput: vi.fn(),
  })
}))

import PluginDevWorkbenchPage from '@/features/plugin-dev-workbench/views/PluginDevWorkbenchPage.vue'

describe('PluginDevWorkbenchPage (mobile)', () => {
  it('移动端场景下向 Header 传递正确的展示状态', async () => {
    const wrapper = shallowMount(PluginDevWorkbenchPage, {
      global: {
        stubs: {
          WorkbenchCenterPane: true,
          IwpFileDrawer: true,
          WorkbenchPreviewSection: true,
          WorkbenchPublishOverlays: true,
        }
      }
    })
    await Promise.resolve()

    const header = wrapper.findComponent({ name: 'WorkbenchHeaderBar' })
    expect(header.exists()).toBe(true)
    expect(header.props('isMobileApp')).toBe(true)
    expect(header.props('isWebApp')).toBe(false)
    expect(header.props('mobilePreviewQrLabel')).toBe('移动端预览二维码')
    expect(header.props('mobileOfflineUploadLabel')).toBe('上传离线包')
  })
})
