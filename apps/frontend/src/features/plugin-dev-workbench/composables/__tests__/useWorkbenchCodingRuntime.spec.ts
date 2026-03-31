import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'

const ensureReadyWithWorkspace = vi.fn()
const dispose = vi.fn()

vi.mock('@/features/coding-agent/store/codingAgentStore', () => ({
  useCodingAgentStore: () => ({
    ensureReadyWithWorkspace,
    dispose,
  }),
}))

import { useWorkbenchCodingRuntime } from '@/features/plugin-dev-workbench/composables/useWorkbenchCodingRuntime'

describe('useWorkbenchCodingRuntime', () => {
  beforeEach(() => {
    ensureReadyWithWorkspace.mockReset()
    dispose.mockReset()
    ensureReadyWithWorkspace.mockResolvedValue(undefined)
  })

  it('挂载时对当前插件触发一次 runtime ensure', async () => {
    const pluginId = ref('plugin.a')
    const Harness = defineComponent({
      setup() {
        return useWorkbenchCodingRuntime({ pluginId: computed(() => pluginId.value) })
      },
      template: '<div />',
    })
    mount(Harness)
    await Promise.resolve()
    expect(ensureReadyWithWorkspace).toHaveBeenCalledTimes(1)
    expect(ensureReadyWithWorkspace).toHaveBeenCalledWith({ pluginId: 'plugin.a' })
  })

  it('插件切换时触发新的 runtime ensure', async () => {
    const pluginId = ref('plugin.a')
    const Harness = defineComponent({
      setup() {
        return useWorkbenchCodingRuntime({ pluginId: computed(() => pluginId.value) })
      },
      template: '<div />',
    })
    mount(Harness)
    await Promise.resolve()
    pluginId.value = 'plugin.b'
    await Promise.resolve()
    expect(ensureReadyWithWorkspace).toHaveBeenLastCalledWith({ pluginId: 'plugin.b' })
  })

  it('workbench 卸载时释放 runtime', () => {
    const pluginId = ref('plugin.a')
    const Harness = defineComponent({
      setup() {
        return useWorkbenchCodingRuntime({ pluginId: computed(() => pluginId.value) })
      },
      template: '<div />',
    })
    const wrapper = mount(Harness)
    wrapper.unmount()
    expect(dispose).toHaveBeenCalledTimes(1)
  })
})
