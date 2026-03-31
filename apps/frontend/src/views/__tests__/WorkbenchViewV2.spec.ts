import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

function createStoreState() {
  return {
    isLoadingProjects: ref(false),
    ensureSyncListener: vi.fn(),
    ensureProject: vi.fn(async (_projectId: string) => null)
  }
}

let storeState = createStoreState()

vi.mock('pinia', async () => {
  const actual = await vi.importActual<typeof import('pinia')>('pinia')
  return {
    ...actual,
    storeToRefs: (store: Record<string, unknown>) => store
  }
})

vi.mock('../../composables/useI18n', () => ({
  useI18n: () => ({
    t: ref({
      workbench: {
        emptyState: {
          startNew: '开始新的工作区对话',
          createDesc: '从左侧选择一个项目开始对话。'
        },
        loadingTimeline: '正在加载工作区...',
        localProject: '本地项目'
      }
    })
  })
}))

vi.mock('../../utils/logger', () => ({
  logger: {
    error: vi.fn(),
    info: vi.fn(),
    warn: vi.fn()
  }
}))

vi.mock('../../stores/workbenchProjectsStore', () => ({
  useWorkbenchProjectsStore: () => storeState
}))

vi.mock('@/features/coding-agent', async () => {
  const actual = await vi.importActual<typeof import('@/features/coding-agent')>('@/features/coding-agent')
  return {
    ...actual,
    WorkbenchChatPanel: {
      name: 'WorkbenchChatPanel',
      props: ['workspaceTarget', 'modelValue'],
      template: '<div class="workbench-chat-panel-stub">{{ workspaceTarget?.displayName }}</div>'
    }
  }
})

import WorkbenchViewV2 from '@/features/workbench/views/WorkbenchView.vue'

describe('WorkbenchViewV2', () => {
  beforeEach(() => {
    storeState = createStoreState()
    storeState.ensureSyncListener.mockClear()
    storeState.ensureProject.mockReset()
    storeState.isLoadingProjects.value = false
  })

  it('会把独立的 workbench project 映射为 workspace target 并渲染聊天面板', async () => {
    storeState.ensureProject.mockResolvedValue({
      id: 'proj_1',
      name: 'Workbench Alpha',
      project_type: 'chat',
      workspace_path: '/tmp/workbench/proj_1',
      created_at: '2026-01-01T00:00:00.000Z',
      updated_at: '2026-01-02T00:00:00.000Z'
    })

    const wrapper = mount(WorkbenchViewV2, {
      props: {
        selectedRoomId: 'proj_1'
      }
    })

    await flushPromises()

    expect(storeState.ensureSyncListener).toHaveBeenCalled()
    expect(storeState.ensureProject).toHaveBeenCalledWith('proj_1')
    expect(wrapper.text()).toContain('Workbench Alpha')
    expect(wrapper.text()).toContain('本地项目')
    const panel = wrapper.findComponent({ name: 'WorkbenchChatPanel' })
    expect(panel.exists()).toBe(true)
    expect(panel.props('workspaceTarget')).toEqual(
      expect.objectContaining({
        kind: 'workbench-general',
        projectId: 'proj_1',
        workspacePath: '/tmp/workbench/proj_1',
        defaultAgent: 'general'
      })
    )
  })

  it('没有 project 时展示空态', async () => {
    storeState.ensureProject.mockResolvedValue(null)
    const wrapper = mount(WorkbenchViewV2, {
      props: {
        selectedRoomId: 'missing'
      }
    })

    await flushPromises()

    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.text()).toContain('开始新的工作区对话')
  })
})
