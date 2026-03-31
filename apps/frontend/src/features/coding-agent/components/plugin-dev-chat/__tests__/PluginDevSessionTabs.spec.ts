import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PluginDevSessionTabs from '@/features/coding-agent/components/plugin-dev-chat/PluginDevSessionTabs.vue'

describe('PluginDevSessionTabs', () => {
  it('点击 tab 会触发切换事件', async () => {
    const wrapper = mount(PluginDevSessionTabs, {
      props: {
        sessions: [
          { id: 's1', title: '会话 1', createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-01T00:00:00.000Z' },
          { id: 's2', title: '会话 2', createdAt: '2026-01-02T00:00:00.000Z', updatedAt: '2026-01-02T00:00:00.000Z' }
        ],
        activeSessionId: 's1'
      }
    })

    const tabs = wrapper.findAll('.session-tab')
    await tabs[1].trigger('click')

    expect(wrapper.emitted('switch-session')?.[0]).toEqual(['s2'])
  })

  it('点击 + 会触发新建会话事件', async () => {
    const wrapper = mount(PluginDevSessionTabs, {
      props: {
        sessions: [],
        activeSessionId: ''
      }
    })

    const createBtn = wrapper.find('.create-session-btn')
    await createBtn.trigger('click')

    expect(wrapper.emitted('create-session')).toBeTruthy()
  })

  it('按钮顺序为新建、历史、设置', () => {
    const wrapper = mount(PluginDevSessionTabs, {
      props: {
        sessions: [],
        activeSessionId: '',
        engineOptions: [{ id: 'opencode', label: 'OpenCode' }],
        availableAgents: [{ id: 'plan', label: 'Plan' }]
      }
    })

    const actionChildren = Array.from(wrapper.find('.tabs-actions').element.children) as HTMLElement[]
    expect(actionChildren[0]?.className).toContain('create-session-btn')
    expect(actionChildren[1]?.className).toContain('history-wrap')
    expect(actionChildren[2]?.className).toContain('settings-wrap')
  })

  it('设置弹层支持切换引擎与模式', async () => {
    const wrapper = mount(PluginDevSessionTabs, {
      attachTo: document.body,
      props: {
        sessions: [],
        activeSessionId: '',
        selectedEngine: 'opencode',
        selectedEngineHealthStatus: 'healthy',
        selectedEngineHealthTitle: 'OpenCode 已连接',
        selectedAgent: 'plan',
        engineOptions: [
          { id: 'opencode', label: 'OpenCode' },
          { id: 'agentv3', label: 'AgentV3' }
        ],
        availableAgents: [
          { id: 'plan', label: 'Plan' },
          { id: 'build', label: 'Build' }
        ]
      }
    })

    await wrapper.find('.icon-btn-settings').trigger('click')
    expect(wrapper.find('.settings-popover').exists()).toBe(true)

    await wrapper.find('.settings-field-engine .inline-select-trigger').trigger('click')
    let options = Array.from(document.body.querySelectorAll<HTMLButtonElement>('.inline-select-option'))
    await options[1]?.click()

    await wrapper.find('.settings-field-mode .inline-select-trigger').trigger('click')
    options = Array.from(document.body.querySelectorAll<HTMLButtonElement>('.inline-select-option'))
    await options[1]?.click()

    expect(wrapper.emitted('select-engine')?.[0]).toEqual(['agentv3'])
    expect(wrapper.emitted('select-agent')?.[0]).toEqual(['build'])
    wrapper.unmount()
  })
})
