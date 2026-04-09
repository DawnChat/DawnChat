import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import WorkbenchHeaderBar from '@/features/plugin-dev-workbench/components/WorkbenchHeaderBar.vue'

const baseProps = {
  activeAppName: 'Demo App',
  pluginId: 'com.demo.app',
  appTypeLabel: 'Web',
  isWebApp: true,
  isMobileApp: false,
  showModeSwitch: true,
  workbenchMode: 'requirements' as const,
  requirementsModeLabel: 'Requirements',
  agentModeLabel: 'Agent',
  buildRunningLabel: 'Building',
  openBuildSessionLabel: 'Open',
  isBuildRunning: false,
  hasBuildSession: false,
  publishWebLabel: 'Publish',
  mobilePreviewQrLabel: 'QR',
  mobileOfflineUploadLabel: 'Offline',
  closeLabel: 'Close',
  editNameLabel: 'Rename app',
  saveNameLabel: 'Save name',
  cancelNameLabel: 'Cancel rename',
  nameInputPlaceholder: 'Enter app name',
  renaming: false,
}

describe('WorkbenchHeaderBar', () => {
  it('点击编辑后可提交新名称', async () => {
    const wrapper = mount(WorkbenchHeaderBar, {
      props: baseProps,
    })
    await wrapper.find('.edit-name-btn').trigger('click')
    const input = wrapper.find('.name-editor-input')
    expect(input.exists()).toBe(true)
    await input.setValue('  New App Name  ')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('renameApp')?.[0]).toEqual(['New App Name'])
  })

  it('按 Escape 取消编辑且不触发提交', async () => {
    const wrapper = mount(WorkbenchHeaderBar, {
      props: baseProps,
    })
    await wrapper.find('.edit-name-btn').trigger('click')
    const input = wrapper.find('.name-editor-input')
    await input.setValue('Temp Name')
    await input.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.name-editor-input').exists()).toBe(false)
    expect(wrapper.emitted('renameApp')).toBeUndefined()
  })

})
