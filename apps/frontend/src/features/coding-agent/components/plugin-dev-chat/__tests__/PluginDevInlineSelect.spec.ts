import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PluginDevInlineSelect from '@/features/coding-agent/components/plugin-dev-chat/PluginDevInlineSelect.vue'

describe('PluginDevInlineSelect', () => {
  it('点击触发器后会展开 Teleport 菜单并限制最大高度', async () => {
    const options = Array.from({ length: 24 }).map((_, index) => ({
      value: `opt-${index}`,
      label: `Option ${index}`,
    }))
    const wrapper = mount(PluginDevInlineSelect, {
      attachTo: document.body,
      props: {
        modelValue: 'opt-0',
        options,
        label: 'Engine',
      },
    })

    await wrapper.find('.inline-select-trigger').trigger('click')
    const menu = document.body.querySelector<HTMLElement>('.inline-select-menu')
    expect(menu).not.toBeNull()
    expect(menu?.style.maxHeight).not.toBe('')

    wrapper.unmount()
  })

  it('点击外部区域会关闭菜单', async () => {
    const wrapper = mount(PluginDevInlineSelect, {
      attachTo: document.body,
      props: {
        modelValue: 'a',
        options: [
          { value: 'a', label: 'A' },
          { value: 'b', label: 'B' },
        ],
        label: 'Agent',
      },
    })

    await wrapper.find('.inline-select-trigger').trigger('click')
    expect(document.body.querySelector('.inline-select-menu')).not.toBeNull()
    document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(document.body.querySelector('.inline-select-menu')).toBeNull()

    wrapper.unmount()
  })

  it('键盘选择会触发 update:modelValue', async () => {
    const wrapper = mount(PluginDevInlineSelect, {
      attachTo: document.body,
      props: {
        modelValue: 'a',
        options: [
          { value: 'a', label: 'A' },
          { value: 'b', label: 'B' },
        ],
        label: 'Model',
      },
    })

    const trigger = wrapper.find('.inline-select-trigger')
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    await trigger.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['b'])

    wrapper.unmount()
  })
})
