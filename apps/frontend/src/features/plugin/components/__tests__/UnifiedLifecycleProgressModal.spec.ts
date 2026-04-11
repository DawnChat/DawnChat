import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import UnifiedLifecycleProgressModal from '@/features/plugin/components/UnifiedLifecycleProgressModal.vue'

describe('UnifiedLifecycleProgressModal', () => {
  it('renders task progress and emits done', async () => {
    const wrapper = mount(UnifiedLifecycleProgressModal, {
      props: {
        visible: true,
        task: {
          task_id: 'task_1',
          operation_type: 'create_dev_session',
          plugin_id: 'com.demo.plugin',
          app_type: 'web',
          status: 'completed',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          elapsed_seconds: 10,
          progress: {
            stage: 'finalize',
            stage_label: '完成',
            progress: 100,
            message: '创建完成',
            eta_seconds: null,
            retryable: false,
            details: [],
          },
          result: { plugin_id: 'com.demo.plugin' },
          error: null,
        },
      },
    })

    expect(wrapper.text()).toContain('100%')
    expect(wrapper.text()).toContain('完成')
    expect(wrapper.text()).not.toContain('完成 · 100%')
    await wrapper.get('.btn-primary').trigger('click')
    expect(wrapper.emitted('done')).toBeTruthy()
  })
})

