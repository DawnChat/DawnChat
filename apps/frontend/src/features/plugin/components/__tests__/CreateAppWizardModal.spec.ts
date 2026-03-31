import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CreateAppWizardModal from '@/features/plugin/components/CreateAppWizardModal.vue'

describe('CreateAppWizardModal', () => {
  it('切换到 web 类型后会触发 appTypeChange 并带着 web 提交', async () => {
    const wrapper = mount(CreateAppWizardModal, {
      props: {
        visible: true,
        creating: false,
        templateInfo: {
          template_id: 'com.dawnchat.web-starter-vue',
          template_name: 'web-starter-vue',
          version: '0.1.0',
          source_dir: '/tmp/template',
          cached: true
        },
        user: {
          id: 'user_123',
          email: 'demo@example.com'
        }
      }
    })

    const typeButtons = wrapper.findAll('.type-btn')
    await typeButtons[1].trigger('click')

    expect(wrapper.emitted('appTypeChange')?.at(-1)).toEqual(['web'])

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('Landing Page')
    await wrapper.find('.btn-primary').trigger('click')

    const payload = wrapper.emitted('confirm')?.at(-1)?.[0] as {
      appType: string
      name: string
      pluginId: string
      description: string
    }
    expect(payload.appType).toBe('web')
    expect(payload.name).toBe('Landing Page')
    expect(payload.pluginId).toContain('.landing-page')
  })

  it('切换到 mobile 类型后会触发 appTypeChange 并带着 mobile 提交', async () => {
    const wrapper = mount(CreateAppWizardModal, {
      props: {
        visible: true,
        creating: false,
        templateInfo: {
          template_id: 'com.dawnchat.mobile-starter-ionic',
          template_name: 'mobile-starter-ionic',
          version: '0.1.0',
          source_dir: '/tmp/template',
          cached: true
        },
        user: {
          id: 'user_123',
          email: 'demo@example.com'
        }
      }
    })

    const typeButtons = wrapper.findAll('.type-btn')
    await typeButtons[2].trigger('click')

    expect(wrapper.emitted('appTypeChange')?.at(-1)).toEqual(['mobile'])

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('Mobile Lab')
    await wrapper.find('.btn-primary').trigger('click')

    const payload = wrapper.emitted('confirm')?.at(-1)?.[0] as {
      appType: string
      name: string
      pluginId: string
      description: string
    }
    expect(payload.appType).toBe('mobile')
    expect(payload.name).toBe('Mobile Lab')
    expect(payload.pluginId).toContain('.mobile-lab')
  })
})
