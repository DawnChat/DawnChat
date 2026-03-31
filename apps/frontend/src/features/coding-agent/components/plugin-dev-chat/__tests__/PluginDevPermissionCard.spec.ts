import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PluginDevPermissionCard from '@/features/coding-agent/components/plugin-dev-chat/PluginDevPermissionCard.vue'

describe('PluginDevPermissionCard', () => {
  it('点击按钮会发出 permission 事件', async () => {
    const wrapper = mount(PluginDevPermissionCard, {
      props: {
        permission: { id: 'perm_1', tool: 'edit', detail: '允许编辑', status: 'pending' },
        agentLabel: 'Agent',
        permissionRequiredLabel: 'Permission required',
        allowOnceLabel: 'Allow once',
        alwaysAllowLabel: 'Always allow',
        rejectLabel: 'Reject'
      }
    })

    const buttons = wrapper.findAll('.permission-btn')
    await buttons[0].trigger('click')
    await buttons[1].trigger('click')
    await buttons[2].trigger('click')

    expect(wrapper.emitted('permission')?.[0]).toEqual(['perm_1', 'once'])
    expect(wrapper.emitted('permission')?.[1]).toEqual(['perm_1', 'always', true])
    expect(wrapper.emitted('permission')?.[2]).toEqual(['perm_1', 'reject'])
  })
})

