import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import PluginDevPartText from '@/features/coding-agent/components/plugin-dev-chat/PluginDevPartText.vue'

describe('PluginDevPartText', () => {
  it('会渲染 markdown 基础语法', () => {
    const wrapper = mount(PluginDevPartText, {
      props: {
        text: '**Bold**\n\n- item-a'
      }
    })

    expect(wrapper.find('strong').exists()).toBe(true)
    expect(wrapper.find('li').text()).toContain('item-a')
  })

  it('支持流式增量更新时即时重渲染', async () => {
    const wrapper = mount(PluginDevPartText, {
      props: {
        text: '```ts\nconst a = 1'
      }
    })

    await wrapper.setProps({ text: '```ts\nconst a = 1\n```' })
    await nextTick()
    expect(wrapper.find('pre code').exists()).toBe(true)
    expect(wrapper.text()).toContain('const a = 1')
  })
})
