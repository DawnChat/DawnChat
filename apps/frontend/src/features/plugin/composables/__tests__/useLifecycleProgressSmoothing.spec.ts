import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { defineComponent, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useLifecycleProgressSmoothing } from '@/features/plugin/composables/useLifecycleProgressSmoothing'
import type { LifecycleTask } from '@/stores/plugin/types'

interface HarnessState {
  visible: Ref<boolean>
  taskId: Ref<string>
  rawProgress: Ref<number>
  taskStatus: Ref<LifecycleTask['status']>
  progressPercent: Ref<number>
}

const createHarness = (initial: {
  visible?: boolean
  taskId?: string
  rawProgress?: number
  taskStatus?: LifecycleTask['status']
}) => {
  let state: HarnessState | null = null
  const TestHarness = defineComponent({
    setup() {
      const visible = ref(initial.visible ?? true)
      const taskId = ref(initial.taskId ?? 'task_1')
      const rawProgress = ref(initial.rawProgress ?? 0)
      const taskStatus = ref<LifecycleTask['status']>(initial.taskStatus ?? 'running')
      const { progressPercent } = useLifecycleProgressSmoothing({
        visible,
        taskId,
        rawProgress,
        taskStatus,
      })
      state = { visible, taskId, rawProgress, taskStatus, progressPercent }
      return () => null
    },
  })
  const wrapper = mount(TestHarness)
  return {
    wrapper,
    state: state as HarnessState,
  }
}

describe('useLifecycleProgressSmoothing', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      return setTimeout(() => callback(Date.now()), 16) as unknown as number
    })
    vi.stubGlobal('cancelAnimationFrame', (id: number) => {
      clearTimeout(id as unknown as ReturnType<typeof setTimeout>)
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('在后端进度长时间不变时平滑推进，并在100%时快速补满', async () => {
    const { wrapper, state } = createHarness({
      rawProgress: 70,
      taskStatus: 'running',
    })

    await vi.advanceTimersByTimeAsync(5000)
    expect(state.progressPercent.value).toBeGreaterThan(71)
    expect(state.progressPercent.value).toBeLessThanOrEqual(95)

    state.rawProgress.value = 100
    state.taskStatus.value = 'completed'
    await vi.advanceTimersByTimeAsync(220)
    expect(state.progressPercent.value).toBe(100)

    wrapper.unmount()
  })
})
