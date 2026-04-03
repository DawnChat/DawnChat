import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DesktopTemplateQuickSelectModal from '@/features/plugin/components/DesktopTemplateQuickSelectModal.vue'

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: {
      apps: {
        desktopTemplateSelectTitle: '选择桌面模板',
        desktopTemplateSelectDescription: '请选择模板',
        desktopTemplateHelloWorldName: '空工程',
        desktopTemplateAssistantName: '智能助理',
        desktopHelloWorldTemplateDescription: 'hello 描述',
        desktopAssistantTemplateDescription: 'assistant 描述',
      },
      common: {
        cancel: '取消',
        confirm: '确认',
      },
    },
  }),
}))

describe('DesktopTemplateQuickSelectModal', () => {
  it('选择 assistant 后确认会回传 assistant template id', async () => {
    const wrapper = mount(DesktopTemplateQuickSelectModal, {
      props: {
        visible: true,
      },
    })

    const options = wrapper.findAll('.option-card')
    await options[1].trigger('click')
    await wrapper.find('.btn-primary').trigger('click')

    expect(wrapper.emitted('confirm')?.at(-1)).toEqual(['com.dawnchat.desktop-ai-assistant'])
  })

  it('每次重新打开默认选中 AI assistant 模板', async () => {
    const wrapper = mount(DesktopTemplateQuickSelectModal, {
      props: {
        visible: true,
      },
    })

    const options = wrapper.findAll('.option-card')
    await options[1].trigger('click')
    await wrapper.setProps({ visible: false })
    await wrapper.setProps({ visible: true })
    await wrapper.find('.btn-primary').trigger('click')

    expect(wrapper.emitted('confirm')?.at(-1)).toEqual(['com.dawnchat.desktop-ai-assistant'])
  })

  it('存在记忆选择时优先使用记忆值', async () => {
    const wrapper = mount(DesktopTemplateQuickSelectModal, {
      props: {
        visible: true,
        selectedTemplateId: 'com.dawnchat.desktop-hello-world',
      },
    })

    await wrapper.find('.btn-primary').trigger('click')
    expect(wrapper.emitted('confirm')?.at(-1)).toEqual(['com.dawnchat.desktop-hello-world'])
  })
})
