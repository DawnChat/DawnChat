import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import PluginDevAssistantWaiting from '@/features/coding-agent/components/plugin-dev-chat/PluginDevAssistantWaiting.vue'

describe('PluginDevAssistantWaiting', () => {
  it('用户发出消息后但 assistant 尚未开始回复时显示初始等待态', () => {
    const wrapper = mount(PluginDevAssistantWaiting, {
      props: {
        timelineItems: [
          {
            id: 'user_1',
            kind: 'part',
            role: 'user',
            item: { id: 'part_user_1', type: 'text', text: 'hello', isStreaming: false }
          }
        ],
        isStreaming: true,
        hasPendingPlayback: false,
        text: '正在生成中'
      }
    })

    expect(wrapper.find('.waiting-placeholder').exists()).toBe(true)
    expect(wrapper.find('.waiting-placeholder').classes()).toContain('is-initial')
  })

  it('assistant 打字完成后若持续卡顿超过阈值则显示 stalled 等待态', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mount(PluginDevAssistantWaiting, {
        props: {
          timelineItems: [
            {
              id: 'user_1',
              kind: 'part',
              role: 'user',
              item: { id: 'part_user_1', type: 'text', text: 'hello', isStreaming: false }
            },
            {
              id: 'assistant_1',
              kind: 'part',
              role: 'assistant',
              item: { id: 'part_assistant_1', type: 'text', text: 'ok', isStreaming: true }
            }
          ],
          isStreaming: true,
          hasPendingPlayback: false,
          text: '正在生成中'
        }
      })

      expect(wrapper.find('.waiting-placeholder').exists()).toBe(false)
      await vi.advanceTimersByTimeAsync(1100)
      await nextTick()
      expect(wrapper.find('.waiting-placeholder').exists()).toBe(true)
      expect(wrapper.find('.waiting-placeholder').classes()).toContain('is-stalled')
    } finally {
      vi.useRealTimers()
    }
  })
})
