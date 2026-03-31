import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PluginDevQuestionCard from '@/features/coding-agent/components/plugin-dev-chat/PluginDevQuestionCard.vue'

describe('PluginDevQuestionCard', () => {
  it('单选+自定义答案优先使用自定义并发出 question-reply', async () => {
    const wrapper = mount(PluginDevQuestionCard, {
      props: {
        question: {
          id: 'que_1',
          questions: [
            {
              header: 'Q1',
              question: '请选择',
              options: [{ label: 'A', description: '选项A' }],
              multiple: false,
              custom: true
            }
          ]
        },
        agentLabel: 'Agent',
        questionRequiredLabel: 'Question required',
        questionLabel: 'Question',
        customAnswerLabel: 'Custom answer',
        submitLabel: 'Submit',
        rejectLabel: 'Reject'
      }
    })

    await wrapper.find('.question-option-btn').trigger('click')
    await wrapper.find('.question-custom input').setValue('我的答案')
    await wrapper.find('.question-actions .permission-btn').trigger('click')

    expect(wrapper.emitted('question-reply')?.[0]).toEqual(['que_1', [['我的答案']]])
  })

  it('点击拒绝会发出 question-reject', async () => {
    const wrapper = mount(PluginDevQuestionCard, {
      props: {
        question: {
          id: 'que_2',
          questions: [
            {
              header: 'Q2',
              question: '是否继续',
              options: [{ label: '继续', description: '' }]
            }
          ]
        },
        agentLabel: 'Agent',
        questionRequiredLabel: 'Question required',
        questionLabel: 'Question',
        customAnswerLabel: 'Custom answer',
        submitLabel: 'Submit',
        rejectLabel: 'Reject'
      }
    })

    await wrapper.find('.question-actions .permission-btn.danger').trigger('click')
    expect(wrapper.emitted('question-reject')?.[0]).toEqual(['que_2'])
  })
})

