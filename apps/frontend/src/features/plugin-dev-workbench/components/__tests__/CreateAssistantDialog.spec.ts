import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CreateAssistantDialog from '@/features/plugin-dev-workbench/components/CreateAssistantDialog.vue'

describe('CreateAssistantDialog', () => {
  it('emits selected platform when confirming', async () => {
    const wrapper = mount(CreateAssistantDialog, {
      props: {
        visible: true,
        title: 'Create AI Assistant',
        description: 'Create a new assistant',
        nameLabel: 'Assistant name',
        namePlaceholder: 'Enter a name',
        platformLabel: 'Platform',
        platformOptions: [
          { value: 'desktop', label: 'Desktop Assistant' },
          { value: 'web', label: 'Web Assistant' }
        ],
        openAfterCreateLabel: 'Open after create',
        cancelLabel: 'Cancel',
        confirmLabel: 'Create',
        submittingLabel: 'Creating...'
      }
    })

    await wrapper.get('#assistant-name-input').setValue('My Web Assistant')
    await wrapper.get('#assistant-platform-select').setValue('web')
    await wrapper.get('.btn-primary').trigger('click')

    expect(wrapper.emitted('confirm')?.[0]).toEqual([{
      name: 'My Web Assistant',
      openAfterCreate: true,
      platform: 'web'
    }])
  })
})
