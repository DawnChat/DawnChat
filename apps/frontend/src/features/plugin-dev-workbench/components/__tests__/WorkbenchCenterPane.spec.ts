import { describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'
import { shallowMount } from '@vue/test-utils'
import WorkbenchCenterPane from '@/features/plugin-dev-workbench/components/WorkbenchCenterPane.vue'

const ChatPanelStub = defineComponent({
  name: 'PluginDevChatPanel',
  props: [
    'showComposer',
    'showSessionTabs',
    'showEngineSelector',
    'showAgentSelector',
    'showModelSelector',
  ],
  template: '<div />',
})

const baseProps = {
  workbenchMode: 'requirements' as const,
  allowRequirementsMode: true,
  centerPaneMode: 'markdown' as const,
  pluginId: 'com.test.plugin',
  chatInput: '',
  previewChatBlocked: false,
  iwpRoot: 'InstructWare.iw',
  activeFilePath: 'requirements/spec.md',
  markdownContent: '# spec',
  fileLoading: false,
  fileSaving: false,
  canBuild: false,
  isDirty: false,
  hasActiveFile: true,
  buildState: { status: 'idle' as const, sessionId: '', message: '', error: '' },
  saveLabel: 'save',
  savingLabel: 'saving',
  buildButtonLabel: 'build',
  editorLoadingLabel: 'loading',
  editorPlaceholder: 'placeholder',
  emptyPathLabel: 'empty',
  savedLabel: 'saved',
  unsavedLabel: 'unsaved',
  buildSessionLabel: 'session',
  openBuildSessionLabel: 'open',
  readonlyTitle: 'readonly',
  readonlyFilePath: '',
  readonlyFileLine: 0,
  readonlyFileContent: '',
  readonlyLoading: false,
  readonlyError: '',
  backToMarkdownLabel: 'back',
  readonlyLoadingLabel: 'loading',
  readonlyEmptyContentLabel: 'empty',
  agentLogTitle: 'log',
  agentLogEmptyLabel: 'empty',
  agentLogRunningLabel: 'running',
  agentLogIdleLabel: 'idle',
  agentLogHeight: 188,
  isResizingAgentLog: false,
  enableFileAttachments: false,
  ttsEnabled: true,
  ttsPlaybackState: 'idle' as const,
  ttsStreamStatus: 'idle' as const,
  selectedTtsEngine: 'system',
  ttsEngineOptions: [],
}

describe('WorkbenchCenterPane', () => {
  it('协作模式下强制展示输入区', () => {
    const wrapper = shallowMount(WorkbenchCenterPane, {
      props: {
        ...baseProps,
        workbenchMode: 'agent',
      },
      global: {
        stubs: {
          PluginDevChatPanel: ChatPanelStub,
          IwpMarkdownEditorPanel: true,
          ReadonlyCodeViewerPanel: true,
        },
      },
    })
    const chat = wrapper.findComponent(ChatPanelStub)
    expect(chat.props('showComposer')).toBe(true)
    expect(chat.props('showSessionTabs')).toBe(true)
    expect(chat.props('showEngineSelector')).toBe(false)
    expect(chat.props('showAgentSelector')).toBe(false)
    expect(chat.props('showModelSelector')).toBe(true)
  })

  it('需求模式日志流隐藏输入区', () => {
    const wrapper = shallowMount(WorkbenchCenterPane, {
      props: baseProps,
      global: {
        stubs: {
          PluginDevChatPanel: ChatPanelStub,
          IwpMarkdownEditorPanel: true,
          ReadonlyCodeViewerPanel: true,
        },
      },
    })
    const chat = wrapper.findComponent(ChatPanelStub)
    expect(chat.props('showComposer')).toBe(false)
    expect(chat.props('showSessionTabs')).toBe(false)
  })

  it('禁用 requirements 能力时始终展示完整协作面板', () => {
    const wrapper = shallowMount(WorkbenchCenterPane, {
      props: {
        ...baseProps,
        workbenchMode: 'requirements',
        allowRequirementsMode: false,
      },
      global: {
        stubs: {
          PluginDevChatPanel: ChatPanelStub,
          IwpMarkdownEditorPanel: true,
          ReadonlyCodeViewerPanel: true,
        },
      },
    })
    const chat = wrapper.findComponent(ChatPanelStub)
    expect(chat.props('showComposer')).toBe(true)
    expect(chat.props('showSessionTabs')).toBe(true)
    expect(chat.props('showEngineSelector')).toBe(false)
  })
})
