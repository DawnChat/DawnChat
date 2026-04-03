import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PluginDevComposer from '@/features/coding-agent/components/plugin-dev-chat/PluginDevComposer.vue'
import { encodeContextToken } from '@/services/plugin-ui-bridge/contextToken'

describe('PluginDevComposer', () => {
  it('切换引擎会触发 select-engine 事件', async () => {
    const wrapper = mount(PluginDevComposer, {
      attachTo: document.body,
      props: {
        modelValue: '',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [
          { id: 'opencode', label: 'OpenCode' },
          { id: 'agentv3', label: 'AgentV3' }
        ],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: false,
        blocked: false,
        blockedText: 'blocked',
        runLabel: 'Run'
      }
    })
    await wrapper.find('.engine-select .inline-select-trigger').trigger('click')
    const options = Array.from(document.body.querySelectorAll<HTMLButtonElement>('.inline-select-option'))
    await options[1]?.click()
    expect(wrapper.emitted('select-engine')?.[0]).toEqual(['agentv3'])
    wrapper.unmount()
  })

  it('blocked 时禁用输入并展示提示', () => {
    const wrapper = mount(PluginDevComposer, {
      props: {
        modelValue: '',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: false,
        blocked: true,
        blockedText: '请先处理问题',
        runLabel: 'Run'
      }
    })
    expect(wrapper.find('.composer-input').attributes('contenteditable')).toBe('false')
    expect(wrapper.text()).toContain('请先处理问题')
  })

  it('输入框交互会触发 selection-change 事件', async () => {
    const wrapper = mount(PluginDevComposer, {
      props: {
        modelValue: 'hello',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: true,
        blocked: false,
        blockedText: '',
        runLabel: 'Run'
      }
    })
    await wrapper.find('.composer-input').trigger('focus')
    await wrapper.find('.composer-input').trigger('click')
    const payload = wrapper.emitted('selection-change')?.at(-1)?.[0] as { start: number; end: number; focused: boolean }
    expect(typeof payload.focused).toBe('boolean')
  })

  it('modelValue 含 context token 时会渲染 chip', async () => {
    const token = encodeContextToken('App.vue(L18:C7)', 'App.vue(L18:C7)\nconst a = 1')
    const wrapper = mount(PluginDevComposer, {
      props: {
        modelValue: `hello ${token}`,
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: true,
        blocked: false,
        blockedText: '',
        runLabel: 'Run'
      }
    })
    expect(wrapper.find('.context-chip').exists()).toBe(true)
    expect(wrapper.find('.context-chip').text()).toContain('App.vue(L18:C7)')
  })

  it('隐藏引擎选择时仍展示当前引擎健康状态点', () => {
    const wrapper = mount(PluginDevComposer, {
      props: {
        modelValue: '',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedEngineLabel: 'OpenCode',
        selectedEngineHealthStatus: 'healthy',
        selectedEngineHealthTitle: 'OpenCode 已连接',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: false,
        blocked: false,
        blockedText: '',
        runLabel: 'Run',
        showEngineSelector: false,
        showAgentSelector: false,
        showModelSelector: true
      }
    })

    expect(wrapper.find('.engine-select').exists()).toBe(false)
    expect(wrapper.find('.engine-status-dot').classes()).toContain('is-healthy')
  })

  it('仅当前选中的引擎选项展示健康状态点', async () => {
    const wrapper = mount(PluginDevComposer, {
      attachTo: document.body,
      props: {
        modelValue: '',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedEngineLabel: 'OpenCode',
        selectedEngineHealthStatus: 'healthy',
        selectedEngineHealthTitle: 'OpenCode 已连接',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [
          { id: 'opencode', label: 'OpenCode' },
          { id: 'agentv3', label: 'AgentV3' }
        ],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: false,
        blocked: false,
        blockedText: '',
        runLabel: 'Run'
      }
    })

    await wrapper.find('.engine-select .inline-select-trigger').trigger('click')
    const options = Array.from(document.body.querySelectorAll<HTMLElement>('.inline-select-option'))
    expect(options[0]?.querySelector('.inline-select-status-dot')).not.toBeNull()
    expect(options[1]?.querySelector('.inline-select-status-dot')).toBeNull()
    wrapper.unmount()
  })

  it('输入法组合态按回车不会触发发送', async () => {
    const wrapper = mount(PluginDevComposer, {
      props: {
        modelValue: '你好',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: true,
        blocked: false,
        blockedText: '',
        runLabel: 'Run'
      }
    })

    await wrapper.find('.composer-input').trigger('compositionstart')
    await wrapper.find('.composer-input').trigger('keydown', { key: 'Enter', isComposing: true })

    expect(wrapper.emitted('send')).toBeUndefined()
  })

  it('粘贴时只写入纯文本内容', async () => {
    const wrapper = mount(PluginDevComposer, {
      attachTo: document.body,
      props: {
        modelValue: '',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: true,
        blocked: false,
        blockedText: '',
        runLabel: 'Run'
      }
    })

    const editable = wrapper.find('.composer-input').element as HTMLDivElement
    const selection = window.getSelection()
    const range = document.createRange()
    range.selectNodeContents(editable)
    range.collapse(false)
    selection?.removeAllRanges()
    selection?.addRange(range)

    await wrapper.find('.composer-input').trigger('paste', {
      clipboardData: {
        getData: vi.fn((type: string) => (type === 'text/plain' ? 'hello\nworld' : '<b>hello</b>'))
      }
    })

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['hello\nworld'])
    wrapper.unmount()
  })

  it('粘贴图片时会触发 paste-image 事件', async () => {
    const originalFileReader = globalThis.FileReader
    class MockFileReader {
      result: string | ArrayBuffer | null = null
      error: DOMException | null = null
      onload: ((this: FileReader, ev: ProgressEvent<FileReader>) => any) | null = null
      onerror: ((this: FileReader, ev: ProgressEvent<FileReader>) => any) | null = null

      readAsDataURL(_file: Blob) {
        this.result = 'data:image/png;base64,AAAA'
        this.onload?.call(this as unknown as FileReader, {} as ProgressEvent<FileReader>)
      }
    }
    vi.stubGlobal('FileReader', MockFileReader as unknown as typeof FileReader)

    const wrapper = mount(PluginDevComposer, {
      attachTo: document.body,
      props: {
        modelValue: '',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: true,
        blocked: false,
        blockedText: '',
        runLabel: 'Run'
      }
    })

    const fakeFile = new File(['x'], 'shot.png', { type: 'image/png' })
    await wrapper.find('.composer-input').trigger('paste', {
      clipboardData: {
        items: [
          {
            kind: 'file',
            type: 'image/png',
            getAsFile: () => fakeFile
          }
        ],
        files: [fakeFile],
        getData: vi.fn(() => '')
      }
    })

    await vi.waitFor(() => {
      expect(wrapper.emitted('paste-image')?.length).toBe(1)
    })
    expect(wrapper.emitted('paste-image')?.[0]?.[0]).toEqual([
      {
        type: 'file',
        mime: 'image/png',
        filename: 'shot.png',
        url: 'data:image/png;base64,AAAA'
      }
    ])
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    wrapper.unmount()
    vi.unstubAllGlobals()
    if (originalFileReader) {
      vi.stubGlobal('FileReader', originalFileReader)
    }
  })

  it('点击标签移除按钮会整块删除上下文 token', async () => {
    const token = encodeContextToken('App.vue(L18:C7)', 'const a = 1')
    const wrapper = mount(PluginDevComposer, {
      props: {
        modelValue: `hello ${token}`,
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: true,
        blocked: false,
        blockedText: '',
        runLabel: 'Run'
      }
    })

    await wrapper.find('.chip-remove').trigger('click')

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['hello '])
  })

  it('选择文件会触发 pick-files 事件', async () => {
    const wrapper = mount(PluginDevComposer, {
      props: {
        modelValue: '',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: true,
        blocked: false,
        blockedText: '',
        runLabel: 'Run',
        enableFileAttachment: true
      }
    })

    const input = wrapper.find('input[type="file"]')
    const fileA = new File(['a'], 'a.txt', { type: 'text/plain' })
    const fileB = new File(['b'], 'b.txt', { type: 'text/plain' })
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [fileA, fileB]
    })
    await input.trigger('change')

    const payload = wrapper.emitted('pick-files')?.[0]?.[0] as File[]
    expect(payload).toHaveLength(2)
    expect(payload[0]?.name).toBe('a.txt')
    expect(payload[1]?.name).toBe('b.txt')
  })

  it('运行中展示可取消按钮并触发 interrupt 事件', async () => {
    const wrapper = mount(PluginDevComposer, {
      props: {
        modelValue: '',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: false,
        canInterrupt: true,
        isRunning: true,
        blocked: false,
        blockedText: '',
        runLabel: 'Run'
      }
    })

    expect(wrapper.find('.send-btn').classes()).toContain('state-interrupt')
    await wrapper.find('.send-btn').trigger('click')
    expect(wrapper.emitted('interrupt')?.length).toBe(1)
  })

  it('不可发送时展示禁用态图标按钮', () => {
    const wrapper = mount(PluginDevComposer, {
      props: {
        modelValue: '',
        placeholder: 'input',
        selectedEngine: 'opencode',
        selectedAgent: 'build',
        selectedModelId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'build', label: 'build' }],
        availableModels: [],
        canSend: false,
        canInterrupt: false,
        isRunning: false,
        blocked: false,
        blockedText: '',
        runLabel: 'Run'
      }
    })

    const button = wrapper.find('.send-btn')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.classes()).toContain('state-disabled')
  })
})
