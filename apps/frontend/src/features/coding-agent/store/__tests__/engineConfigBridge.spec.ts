import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { createEngineConfigBridge } from '@/features/coding-agent/store/engineConfigBridge'
import type { ModelOption } from '@/features/coding-agent/store/types'

describe('engineConfigBridge', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('opencode 选择 agent 会 patch /api/opencode/config', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => ''
    }))
    vi.stubGlobal('fetch', fetchMock as any)

    const selectedEngine = ref<'opencode' | 'agentv3'>('opencode')
    const selectedAgent = ref('build')
    const selectedModelId = ref('')
    const availableModels = ref<ModelOption[]>([])
    const activeSessionId = ref('s1')
    const adapter = {}
    const bridge = createEngineConfigBridge({
      selectedEngine: selectedEngine as any,
      selectedAgent,
      selectedModelId,
      availableModels,
      activeSessionId,
      getActiveAdapter: () => adapter as any,
      persistSelectedAgent: () => {},
      persistSelectedModel: () => {}
    })

    bridge.selectAgent('plan')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(selectedAgent.value).toBe('plan')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0]?.[0] || '')).toContain('/api/opencode/config')
  })

  it('agentv3 选择 model 会调用 updateSessionConfig', async () => {
    const selectedEngine = ref<'opencode' | 'agentv3'>('agentv3')
    const selectedAgent = ref('build')
    const selectedModelId = ref('')
    const availableModels = ref<ModelOption[]>([
      {
        id: 'p/m',
        label: 'm',
        providerID: 'p',
        modelID: 'm'
      }
    ])
    const activeSessionId = ref('s2')
    const updateSessionConfig = vi.fn(async () => null)
    const bridge = createEngineConfigBridge({
      selectedEngine: selectedEngine as any,
      selectedAgent,
      selectedModelId,
      availableModels,
      activeSessionId,
      getActiveAdapter: () =>
        ({
          updateSessionConfig
        }) as any,
      persistSelectedAgent: () => {},
      persistSelectedModel: () => {}
    })

    bridge.selectModel('p/m')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(selectedModelId.value).toBe('p/m')
    expect(updateSessionConfig).toHaveBeenCalledWith('s2', {
      model: {
        providerID: 'p',
        modelID: 'm'
      }
    })
  })

  it('opencode default_agent patch 返回 400 时会软跳过，不抛出异常', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 400,
      text: async () => 'default_agent 不可用'
    }))
    vi.stubGlobal('fetch', fetchMock as any)

    const selectedEngine = ref<'opencode' | 'agentv3'>('opencode')
    const selectedAgent = ref('build')
    const selectedModelId = ref('')
    const availableModels = ref<ModelOption[]>([])
    const activeSessionId = ref('s1')
    const bridge = createEngineConfigBridge({
      selectedEngine: selectedEngine as any,
      selectedAgent,
      selectedModelId,
      availableModels,
      activeSessionId,
      getActiveAdapter: () => ({}) as any,
      persistSelectedAgent: () => {},
      persistSelectedModel: () => {}
    })

    bridge.selectAgent('general')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(selectedAgent.value).toBe('general')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

})
