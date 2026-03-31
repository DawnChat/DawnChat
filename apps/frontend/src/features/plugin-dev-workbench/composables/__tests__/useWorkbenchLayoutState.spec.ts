import { beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useWorkbenchLayoutState } from '@/features/plugin-dev-workbench/composables/useWorkbenchLayoutState'
import { getWorkbenchLayoutProfile } from '@/features/plugin-dev-workbench/services/workbenchLayoutProfile'

describe('useWorkbenchLayoutState', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('挂载时恢复并收敛本地布局状态', () => {
    localStorage.setItem(
      'plugin-dev-workbench.layout.v1',
      JSON.stringify({ previewWidthPx: 1200, agentLogHeightPx: 80 })
    )

    const Harness = defineComponent({
      setup() {
        return useWorkbenchLayoutState()
      },
      template: '<div />',
    })

    const wrapper = mount(Harness)
    expect((wrapper.vm as any).previewWidthPx).toBe(900)
    expect((wrapper.vm as any).agentLogHeightPx).toBe(120)
  })

  it('拖拽后更新尺寸并持久化', () => {
    const Harness = defineComponent({
      setup() {
        return useWorkbenchLayoutState()
      },
      template: '<div />',
    })

    const wrapper = mount(Harness)
    ;(wrapper.vm as any).startResizeAgentLog(new MouseEvent('pointerdown', { clientY: 220 }) as PointerEvent)
    window.dispatchEvent(new MouseEvent('pointermove', { clientY: 170 }))
    expect((wrapper.vm as any).agentLogHeightPx).toBe(238)

    ;(wrapper.vm as any).startResizePreview(new MouseEvent('pointerdown', { clientX: 300 }) as PointerEvent)
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 1000 }))
    expect((wrapper.vm as any).previewWidthPx).toBeGreaterThanOrEqual(360)

    window.dispatchEvent(new MouseEvent('pointerup'))
    const saved = JSON.parse(String(localStorage.getItem('plugin-dev-workbench.layout.v1')))
    expect(saved.previewWidthPx).toBeTypeOf('number')
    expect(saved.agentLogHeightPx).toBeTypeOf('number')
  })

  it('强制 Agent-only 布局时忽略本地缓存且不写入持久化', () => {
    localStorage.setItem(
      'plugin-dev-workbench.layout.v1',
      JSON.stringify({ previewWidthPx: 900, agentLogHeightPx: 300 })
    )
    const profile = ref(getWorkbenchLayoutProfile('agent_preview'))
    const Harness = defineComponent({
      setup() {
        return useWorkbenchLayoutState({ profile })
      },
      template: '<div />',
    })

    const wrapper = mount(Harness)
    expect((wrapper.vm as any).previewWidthPx).toBe(460)

    ;(wrapper.vm as any).startResizePreview(new MouseEvent('pointerdown', { clientX: 320 }) as PointerEvent)
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 200 }))
    window.dispatchEvent(new MouseEvent('pointerup'))
    const saved = JSON.parse(String(localStorage.getItem('plugin-dev-workbench.layout.v1')))
    expect(saved.previewWidthPx).toBe(900)
  })

  it('强制 Agent-only 布局时左侧 Agent 宽度最多到均分', () => {
    const profile = ref(getWorkbenchLayoutProfile('agent_preview'))
    const Harness = defineComponent({
      setup() {
        return useWorkbenchLayoutState({ profile })
      },
      template: '<div />',
    })

    const wrapper = mount(Harness)
    ;(wrapper.vm as any).startResizePreview(new MouseEvent('pointerdown', { clientX: 300 }) as PointerEvent)
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 2000 }))
    const maxByHalf = Math.floor((window.innerWidth - 8) / 2)
    expect((wrapper.vm as any).previewWidthPx).toBe(maxByHalf)
  })
})
