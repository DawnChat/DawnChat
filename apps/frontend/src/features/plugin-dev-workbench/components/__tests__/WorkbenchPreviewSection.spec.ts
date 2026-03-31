import { describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import WorkbenchPreviewSection from '@/features/plugin-dev-workbench/components/WorkbenchPreviewSection.vue'

const PreviewPaneStub = defineComponent({
  name: 'PluginPreviewPane',
  emits: ['restart', 'retryInstall', 'inspectorSelect', 'contextPush', 'ttsSpeakAccepted', 'ttsStopped'],
  template: '<div class="preview-pane-stub"></div>',
})

const CompactShellStub = defineComponent({
  name: 'AssistantCompactShell',
  emits: ['update-model-value', 'composer-selection-change', 'toggle-tts-enabled', 'stop-tts'],
  template: '<div class="compact-shell-stub"></div>',
})

const baseProps = {
  isPreviewRenderable: true,
  showCompactShell: false,
  previewPaneKey: 1,
  pluginId: 'com.test.app',
  pluginUrl: 'http://127.0.0.1:5173',
  previewLogSessionId: 'log-1',
  previewLifecycleTask: null,
  previewLifecycleBusy: false,
  previewInstallStatus: 'idle' as const,
  previewInstallErrorMessage: '',
  previewLoadingText: 'loading',
  chatInput: '',
  previewChatBlocked: false,
  previewBlockedText: 'blocked',
  ttsEnabled: true,
  ttsPlaybackState: 'idle' as const,
  ttsStreamStatus: 'idle' as const,
}

describe('WorkbenchPreviewSection', () => {
  it('转发 PreviewPane 事件', async () => {
    const wrapper = mount(WorkbenchPreviewSection, {
      props: baseProps,
      global: {
        stubs: {
          PluginPreviewPane: PreviewPaneStub,
          AssistantCompactShell: CompactShellStub,
        },
      },
    })

    const pane = wrapper.findComponent(PreviewPaneStub)
    pane.vm.$emit('restart', 'com.test.app')
    pane.vm.$emit('retryInstall')
    pane.vm.$emit('inspectorSelect', { file: 'a.vue' })
    pane.vm.$emit('contextPush', { source: 'inspector', content: 'ctx' })
    pane.vm.$emit('ttsSpeakAccepted', { task_id: 't1' })
    pane.vm.$emit('ttsStopped', { task_id: 't1' })
    await Promise.resolve()

    expect(wrapper.emitted('restart')?.[0]).toEqual(['com.test.app'])
    expect(wrapper.emitted('retryInstall')?.length).toBe(1)
    expect(wrapper.emitted('inspectorSelect')?.length).toBe(1)
    expect(wrapper.emitted('contextPush')?.length).toBe(1)
    expect(wrapper.emitted('ttsSpeakAccepted')?.length).toBe(1)
    expect(wrapper.emitted('ttsStopped')?.length).toBe(1)
  })

  it('compact 模式下渲染 AssistantCompactShell 并转发输入事件', async () => {
    const wrapper = mount(WorkbenchPreviewSection, {
      props: {
        ...baseProps,
        showCompactShell: true,
        chatInput: 'hello',
      },
      global: {
        stubs: {
          PluginPreviewPane: PreviewPaneStub,
          AssistantCompactShell: CompactShellStub,
        },
      },
    })

    const compact = wrapper.findComponent(CompactShellStub)
    expect(compact.exists()).toBe(true)
    compact.vm.$emit('update-model-value', 'next')
    compact.vm.$emit('composer-selection-change', { start: 1, end: 2, focused: true })
    compact.vm.$emit('toggle-tts-enabled')
    compact.vm.$emit('stop-tts')
    await Promise.resolve()

    expect(wrapper.emitted('updateChatInput')?.[0]).toEqual(['next'])
    expect(wrapper.emitted('composerSelectionChange')?.length).toBe(1)
    expect(wrapper.emitted('toggleTtsEnabled')?.length).toBe(1)
    expect(wrapper.emitted('stopTts')?.length).toBe(1)
  })
})
