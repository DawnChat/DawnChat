import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PluginDevMessagePartRenderer from '@/features/coding-agent/components/plugin-dev-chat/PluginDevMessagePartRenderer.vue'

describe('PluginDevMessagePartRenderer', () => {
  it('text 类型会渲染文本部件', () => {
    const wrapper = mount(PluginDevMessagePartRenderer, {
      props: {
        item: {
          id: 'p1',
          type: 'text',
          text: 'hello'
        },
        reasoningExpanded: false
      }
    })

    expect(wrapper.text()).toContain('hello')
  })

  it('reasoning 类型可转发 toggle 事件', async () => {
    const wrapper = mount(PluginDevMessagePartRenderer, {
      props: {
        item: {
          id: 'p2',
          type: 'reasoning',
          text: '**thinking**'
        },
        reasoningExpanded: true
      }
    })

    expect(wrapper.html()).toContain('<strong>thinking</strong>')
    await wrapper.find('.reasoning-toggle').trigger('click')
    expect(wrapper.emitted('toggle-reasoning')).toBeTruthy()
  })

})
