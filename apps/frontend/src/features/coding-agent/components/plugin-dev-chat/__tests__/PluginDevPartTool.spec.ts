import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PluginDevPartTool from '@/features/coding-agent/components/plugin-dev-chat/PluginDevPartTool.vue'

describe('PluginDevPartTool', () => {
  it('高频工具默认按 inline 样式渲染，不使用卡片气泡', () => {
    const wrapper = mount(PluginDevPartTool, {
      props: {
        tool: 'read',
        display: {
          kind: 'read',
          renderMode: 'inline',
          toolName: 'read',
          argsText: 'App.vue',
          title: 'read App.vue',
          summary: '',
          detailsText: '',
          command: '',
          outputTail: '',
          diffStat: '',
          patchPreview: ''
        }
      }
    })

    expect(wrapper.find('.tool-line').exists()).toBe(true)
    expect(wrapper.find('.tool-toggle').exists()).toBe(false)
    expect(wrapper.find('.tool-name').text()).toBe('read App.vue')
    expect(wrapper.find('.tool-args').text()).toContain('App.vue')
    expect(wrapper.find('.tool-pre').exists()).toBe(false)
  })

  it('通用工具可折叠显示详情且不重复标题文案', async () => {
    const wrapper = mount(PluginDevPartTool, {
      props: {
        tool: 'glob',
        display: {
          kind: 'other',
          renderMode: 'collapsible',
          toolName: 'glob',
          argsText: '**/*.spec.ts apps/frontend/src',
          title: 'glob 匹配文件',
          summary: 'glob 匹配文件: **/*.spec.ts in apps/frontend/src',
          detailBody: '/abs/path/a.spec.ts\n/abs/path/b.spec.ts',
          detailsText: '/abs/path/a.spec.ts\n/abs/path/b.spec.ts',
          command: '',
          outputTail: '',
          diffStat: '',
          patchPreview: ''
        }
      }
    })

    expect(wrapper.find('.tool-toggle').exists()).toBe(true)
    expect(wrapper.find('.tool-details').exists()).toBe(false)
    await wrapper.find('.tool-toggle').trigger('click')
    expect(wrapper.find('.tool-details').exists()).toBe(true)
    expect(wrapper.find('.tool-name').text()).toBe('glob 匹配文件')
    expect(wrapper.find('.tool-args').text()).toContain('**/*.spec.ts apps/frontend/src')
    expect(wrapper.text()).toContain('a.spec.ts')
    expect(wrapper.find('.tool-summary').exists()).toBe(false)
  })

  it('当没有详情信息时，即使 renderMode=collapsible 也不显示折叠按钮', () => {
    const wrapper = mount(PluginDevPartTool, {
      props: {
        tool: 'search',
        display: {
          kind: 'search',
          renderMode: 'collapsible',
          toolName: 'search',
          argsText: 'keyword',
          argsPreview: 'keyword',
          hasDetails: false,
          title: 'search keyword',
          summary: '',
          detailsText: '',
          command: '',
          outputTail: '',
          diffStat: '',
          patchPreview: ''
        }
      }
    })

    expect(wrapper.find('.tool-toggle').exists()).toBe(false)
    expect(wrapper.find('.tool-line').exists()).toBe(true)
  })

  it('兼容旧字段 detailsText（未提供 detailBody 时仍能展示详情）', async () => {
    const wrapper = mount(PluginDevPartTool, {
      props: {
        tool: 'glob',
        display: {
          kind: 'other',
          renderMode: 'collapsible',
          toolName: 'glob',
          argsText: '**/*.ts apps/frontend/src',
          title: 'glob',
          summary: 'glob 匹配文件',
          detailsText: '/a.ts\n/b.ts',
          command: '',
          outputTail: '',
          diffStat: '',
          patchPreview: ''
        }
      }
    })
    await wrapper.find('.tool-toggle').trigger('click')
    expect(wrapper.text()).toContain('/a.ts')
  })

  it('点击 info 按钮会弹出参数弹窗，点击外部可关闭', async () => {
    const wrapper = mount(PluginDevPartTool, {
      props: {
        tool: 'search',
        display: {
          kind: 'search',
          renderMode: 'collapsible',
          toolName: 'search',
          argsText: 'keyword',
          argsPreview: 'keyword',
          hasInput: true,
          fullInputText: '{\n  "query": "keyword"\n}',
          title: 'search keyword',
          summary: 'search keyword',
          detailsText: 'matched line 1',
          command: '',
          outputTail: '',
          diffStat: '',
          patchPreview: ''
        }
      },
      attachTo: document.body
    })

    expect(document.body.querySelector('.tool-input-popover')).toBeNull()
    await wrapper.find('.tool-info-btn').trigger('click')
    await wrapper.vm.$nextTick()
    const popover = document.body.querySelector('.tool-input-popover')
    const pre = document.body.querySelector('.tool-input-pre')
    expect(popover).not.toBeNull()
    expect(popover?.textContent || '').toContain('Tool: search')
    expect(pre?.textContent || '').toContain('"query": "keyword"')

    document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await wrapper.vm.$nextTick()
    expect(document.body.querySelector('.tool-input-popover')).toBeNull()
    wrapper.unmount()
  })

  it('失败态详情区仅展示错误信息，不展示输出内容', async () => {
    const wrapper = mount(PluginDevPartTool, {
      props: {
        tool: 'bash',
        status: 'error',
        display: {
          kind: 'bash',
          renderMode: 'collapsible',
          toolName: 'bash',
          argsText: 'echo test',
          argsPreview: 'echo test',
          hasError: true,
          fullErrorText: 'Permission denied',
          fullOutputText: 'should not be shown',
          hasDetails: true,
          title: 'bash echo test',
          summary: 'bash echo test',
          detailsText: 'Permission denied',
          command: 'echo test',
          outputTail: 'should not be shown',
          diffStat: '',
          patchPreview: ''
        }
      }
    })

    await wrapper.find('.tool-toggle').trigger('click')
    expect(wrapper.text()).toContain('Permission denied')
    expect(wrapper.text()).not.toContain('should not be shown')
  })
})
