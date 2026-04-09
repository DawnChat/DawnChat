import { computed, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const uploadPluginAgentAttachmentMock = vi.fn(async (_pluginId: string, file: File) => ({
  plugin_id: _pluginId,
  filename: file.name,
  stored_path: `user-uploads/${file.name}`,
  size_bytes: file.size
}))

function createMockStore() {
  return {
    selectedEngine: ref('opencode'),
    availableAgents: ref([{ id: 'general', label: 'general' }]),
    availableModels: ref([{ id: 'local/model-a', label: 'Model A', providerID: 'local', modelID: 'model-a' }]),
    engineOptions: ref([
      { id: 'opencode', label: 'OpenCode' },
      { id: 'agentv3', label: 'AgentV3' }
    ]),
    selectedAgent: ref('general'),
    selectedModelId: ref('local/model-a'),
    chatRows: ref([]),
    timelineItems: ref([]),
    activeReasoningItemId: ref(''),
    permissionCards: ref([]),
    questionCards: ref([]),
    activeSessionTodos: ref([]),
    canSwitchPlanToBuild: computed(() => false),
    sessions: ref([]),
    activeSessionId: ref('ses_test_1'),
    isStreaming: ref(false),
    waitingReason: ref(''),
    canInterrupt: ref(false),
    lastError: ref<string | null>(null),
    lastErrorRaw: ref<unknown>(null),
    rulesStatus: ref(null),
    selectEngine: vi.fn(),
    selectAgent: vi.fn(),
    selectModel: vi.fn(),
    ensureReadyWithWorkspace: vi.fn(async () => {}),
    sendText: vi.fn(async () => {}),
    sendPromptParts: vi.fn(async () => {}),
    interruptActiveRun: vi.fn(async () => true),
    replyPermission: vi.fn(async () => {}),
    replyQuestion: vi.fn(async () => {}),
    rejectQuestion: vi.fn(async () => {}),
    createSession: vi.fn(async () => 'ses_test_1'),
    switchSession: vi.fn(async () => {}),
    dispose: vi.fn()
  }
}

let mockStore = createMockStore()

vi.mock('pinia', async () => {
  const actual = await vi.importActual<typeof import('pinia')>('pinia')
  return {
    ...actual,
    storeToRefs: (store: Record<string, unknown>) => store
  }
})

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: ref({
      apps: {
        sharedRulesDisabled: '共享规则: 未启用',
        sharedRulesEnabled: '共享规则: 已启用',
        sharedRulesVersion: '共享规则: v{version}'
      }
    })
  })
}))

vi.mock('@/composables/useEngineHealth', () => ({
  useEngineHealth: () => ({
    engineHealthStatus: ref('healthy'),
    engineHealthTitle: ref('OpenCode 已连接')
  })
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn()
  }
}))

vi.mock('@/features/coding-agent/store/codingAgentStore', () => ({
  useCodingAgentStore: () => mockStore
}))

vi.mock('@dawnchat/host-orchestration-sdk/assistant-client', () => ({
  expandContextTokens: (value: string) => value
}))

vi.mock('@/services/plugins/pluginAgentAttachmentApi', () => ({
  uploadPluginAgentAttachment: (...args: unknown[]) =>
    uploadPluginAgentAttachmentMock(...(args as [string, File]))
}))

vi.mock('@/features/coding-agent/components/plugin-dev-chat/PluginDevSessionTabs.vue', () => ({
  default: {
    name: 'PluginDevSessionTabs',
    emits: ['switch-session', 'create-session'],
    template: `
      <div class="session-tabs-stub">
        <button class="emit-create-session" @click="$emit('create-session')" />
        <button class="emit-switch-session" @click="$emit('switch-session', 'ses_other')" />
      </div>
    `
  }
}))

vi.mock('@/features/coding-agent/components/plugin-dev-chat/PluginDevMessageList.vue', () => ({
  default: {
    name: 'PluginDevMessageList',
    template: '<div class="message-list-stub" />'
  }
}))

vi.mock('@/features/coding-agent/components/plugin-dev-chat/PluginDevComposer.vue', () => ({
  default: {
    name: 'PluginDevComposer',
    props: [
      'blocked',
      'canSend',
      'showEngineSelector',
      'showAgentSelector',
      'showModelSelector',
      'selectedEngine',
      'selectedEngineLabel',
      'selectedEngineHealthStatus',
      'selectedEngineHealthTitle',
      'selectedAgent',
      'selectedModelId',
      'pendingImages',
      'pendingFiles',
      'enableFileAttachment',
      'isUploadingAttachments',
      'filePickerLabel'
    ],
    emits: ['select-engine', 'select-agent', 'select-model', 'send', 'interrupt', 'update:modelValue', 'selection-change', 'paste-image', 'pick-files', 'preview-image', 'remove-image', 'remove-file'],
    template: `
      <div class="composer-stub">
        <span class="engine-flag">{{ showEngineSelector }}</span>
        <span class="agent-flag">{{ showAgentSelector }}</span>
        <span class="model-flag">{{ showModelSelector }}</span>
        <span class="engine-health">{{ selectedEngineLabel }}|{{ selectedEngineHealthStatus }}</span>
        <span class="pending-images">{{ pendingImages?.length || 0 }}</span>
        <button class="emit-engine" @click="$emit('select-engine', 'agentv3')" />
      </div>
    `
  }
}))

vi.mock('@/shared/ui/FloatingPopover.vue', () => ({
  default: {
    name: 'FloatingPopover',
    props: ['visible'],
    emits: ['outside-click'],
    template: `
      <div v-if="visible" class="floating-popover-stub">
        <slot />
      </div>
    `
  }
}))

import CodingChatShell from '@/features/coding-agent/components/CodingChatShell.vue'

describe('CodingChatShell', () => {
  beforeEach(() => {
    mockStore = createMockStore()
    mockStore.ensureReadyWithWorkspace.mockClear()
    mockStore.selectEngine.mockClear()
    mockStore.selectAgent.mockClear()
    mockStore.dispose.mockClear()
    mockStore.selectedEngine.value = 'opencode'
    mockStore.selectedAgent.value = 'general'
    mockStore.selectedModelId.value = 'local/model-a'
    uploadPluginAgentAttachmentMock.mockClear()
  })

  it('挂载时会按 workspace target 初始化运行时', async () => {
    mount(CodingChatShell, {
      props: {
        modelValue: '',
        workspaceTarget: {
          id: 'workbench:proj_1',
          kind: 'workbench-general',
          displayName: 'Project 1',
          appType: 'chat',
          workspacePath: '/tmp/project-1',
          preferredEntry: '',
          preferredDirectories: [],
          hints: [],
          defaultAgent: 'general',
          sessionStrategy: 'single',
          projectId: 'proj_1'
        },
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new',
        showSessionTabs: false,
        showEngineSelector: true,
        showAgentSelector: false,
        showModelSelector: true
      }
    })

    await flushPromises()

    expect(mockStore.ensureReadyWithWorkspace).toHaveBeenCalledWith({
      workspaceTarget: expect.objectContaining({
        kind: 'workbench-general',
        projectId: 'proj_1',
        workspacePath: '/tmp/project-1'
      }),
      pluginId: undefined,
      forceRestart: false
    })
  })

  it('新建会话时会显式携带当前 workspace 选项', async () => {
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: '',
        pluginId: 'com.dawnchat.hello-world-vue',
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new'
      }
    })

    await flushPromises()
    await wrapper.find('.emit-create-session').trigger('click')
    await flushPromises()

    expect(mockStore.createSession).toHaveBeenCalledWith(
      'new',
      true,
      expect.objectContaining({
        pluginId: 'com.dawnchat.hello-world-vue',
        forceRestart: false
      })
    )
  })

  it('切换 session 时会显式携带当前 workspace 选项', async () => {
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: '',
        pluginId: 'com.dawnchat.hello-world-vue',
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new'
      }
    })

    await flushPromises()
    await wrapper.find('.emit-switch-session').trigger('click')
    await flushPromises()

    expect(mockStore.switchSession).toHaveBeenCalledWith(
      'ses_other',
      expect.objectContaining({
        pluginId: 'com.dawnchat.hello-world-vue',
        forceRestart: false
      })
    )
  })

  it('切换引擎时会刷新运行时且保留 workbench 的 general agent 约束', async () => {
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: '',
        workspaceTarget: {
          id: 'workbench:proj_1',
          kind: 'workbench-general',
          displayName: 'Project 1',
          appType: 'chat',
          workspacePath: '/tmp/project-1',
          preferredEntry: '',
          preferredDirectories: [],
          hints: [],
          defaultAgent: 'general',
          sessionStrategy: 'single',
          projectId: 'proj_1'
        },
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new',
        showSessionTabs: false,
        showEngineSelector: true,
        showAgentSelector: false,
        showModelSelector: true,
        forceAgent: 'general'
      }
    })

    await flushPromises()
    await wrapper.find('.emit-engine').trigger('click')
    await flushPromises()

    expect(mockStore.selectEngine).toHaveBeenCalledWith('agentv3')
    expect(mockStore.ensureReadyWithWorkspace).toHaveBeenLastCalledWith({
      workspaceTarget: expect.objectContaining({
        kind: 'workbench-general',
        projectId: 'proj_1'
      }),
      pluginId: undefined,
      forceRestart: false
    })
    expect(mockStore.selectedAgent.value).toBe('general')
  })

  it('会把当前引擎健康状态传给 composer 展示层', async () => {
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: '',
        pluginId: 'com.dawnchat.hello-world-vue',
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new'
      }
    })

    await flushPromises()

    expect(wrapper.find('.engine-health').text()).toContain('OpenCode|healthy')
  })

  it('运行中触发发送动作时会优先执行中断', async () => {
    mockStore.isStreaming.value = true
    mockStore.canInterrupt.value = true
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: 'hello',
        pluginId: 'com.dawnchat.hello-world-vue',
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new'
      }
    })
    await flushPromises()

    wrapper.findComponent({ name: 'PluginDevComposer' }).vm.$emit('send')
    await flushPromises()

    expect(mockStore.interruptActiveRun).toHaveBeenCalledTimes(1)
    expect(mockStore.sendPromptParts).not.toHaveBeenCalled()
  })

  it('存在 permission 卡片时不阻塞输入与发送', async () => {
    mockStore.permissionCards.value = [
      {
        id: 'perm_1',
        sessionID: 'ses_test_1',
        messageID: 'msg_1',
        callID: 'call_1',
        tool: 'read_file',
        status: 'pending',
        detail: '需要读取文件'
      }
    ]
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: 'hello',
        pluginId: 'com.dawnchat.hello-world-vue',
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new'
      }
    })
    await flushPromises()

    const composer = wrapper.findComponent({ name: 'PluginDevComposer' })
    expect(composer.props('blocked')).toBe(false)
    expect(composer.props('canSend')).toBe(true)
  })

  it('接收图片粘贴后可直接发送 file part', async () => {
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: '',
        pluginId: 'com.dawnchat.hello-world-vue',
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new'
      }
    })
    await flushPromises()

    const composer = wrapper.findComponent({ name: 'PluginDevComposer' })
    composer.vm.$emit('paste-image', [
      {
        type: 'file',
        mime: 'image/png',
        filename: 'shot.png',
        url: 'data:image/png;base64,AAAA'
      }
    ])
    composer.vm.$emit('send')
    await flushPromises()

    expect(mockStore.sendPromptParts).toHaveBeenCalledWith(
      [
        {
          type: 'file',
          mime: 'image/png',
          filename: 'shot.png',
          url: 'data:image/png;base64,AAAA'
        }
      ],
      {
        workspaceTarget: null,
        pluginId: 'com.dawnchat.hello-world-vue',
        forceRestart: false
      }
    )
    expect(composer.props('pendingImages')).toEqual([])
  })

  it('图片标签支持删除，并同步更新待发送附件列表', async () => {
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: '',
        pluginId: 'com.dawnchat.hello-world-vue',
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new'
      }
    })
    await flushPromises()

    const composer = wrapper.findComponent({ name: 'PluginDevComposer' })
    composer.vm.$emit('paste-image', [
      {
        type: 'file',
        mime: 'image/png',
        filename: 'shot.png',
        url: 'data:image/png;base64,AAAA'
      }
    ])
    await flushPromises()
    expect(composer.props('pendingImages')).toHaveLength(1)

    composer.vm.$emit('remove-image', 0)
    await flushPromises()
    expect(composer.props('pendingImages')).toEqual([])
  })

  it('点击图片标签预览会展示图片预览浮层', async () => {
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: '',
        pluginId: 'com.dawnchat.hello-world-vue',
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new'
      }
    })
    await flushPromises()

    const composer = wrapper.findComponent({ name: 'PluginDevComposer' })
    composer.vm.$emit('paste-image', [
      {
        type: 'file',
        mime: 'image/png',
        filename: 'shot.png',
        url: 'data:image/png;base64,AAAA'
      }
    ])
    await flushPromises()

    composer.vm.$emit('preview-image', { index: 0, anchorEl: null })
    await flushPromises()
    expect(wrapper.find('.floating-popover-stub').exists()).toBe(true)
  })

  it('发送前会上传附件并把相对路径注入 text part', async () => {
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: '请帮我分析附件',
        pluginId: 'com.dawnchat.hello-world-vue',
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new',
        enableFileAttachments: true
      }
    })
    await flushPromises()

    const composer = wrapper.findComponent({ name: 'PluginDevComposer' })
    composer.vm.$emit('pick-files', [new File(['abc'], 'report.md', { type: 'text/markdown' })])
    composer.vm.$emit('send')
    await flushPromises()

    expect(uploadPluginAgentAttachmentMock).toHaveBeenCalledTimes(1)
    expect(mockStore.sendPromptParts).toHaveBeenCalledWith(
      [
        {
          type: 'text',
          text: '请帮我分析附件\n\nAttached files:\n- user-uploads/report.md'
        }
      ],
      {
        workspaceTarget: null,
        pluginId: 'com.dawnchat.hello-world-vue',
        forceRestart: false
      }
    )
  })

  it('存在 question 卡片时仍阻塞输入与发送', async () => {
    mockStore.questionCards.value = [
      {
        id: 'q_1',
        sessionID: 'ses_test_1',
        messageID: 'msg_1',
        questions: [],
        status: 'pending',
        toolCallID: 'call_1'
      }
    ]
    const wrapper = mount(CodingChatShell, {
      props: {
        modelValue: 'hello',
        pluginId: 'com.dawnchat.hello-world-vue',
        emptyText: 'empty',
        placeholder: 'placeholder',
        streamingText: 'streaming',
        blockedText: 'blocked',
        runLabel: 'run',
        newChatLabel: 'new'
      }
    })
    await flushPromises()

    const composer = wrapper.findComponent({ name: 'PluginDevComposer' })
    expect(composer.props('blocked')).toBe(true)
    expect(composer.props('canSend')).toBe(false)
  })
})
