import { describe, expect, it, vi } from 'vitest'

vi.mock('../openCodeAdapter', () => ({
  openCodeAdapter: {} as any,
  fetchOpenCodeHealthSnapshot: vi.fn(async () => ({
    baseUrl: 'http://127.0.0.1:4096',
    backendStatus: 'running',
    healthy: true
  }))
}))

vi.mock('../agentV3Adapter', () => ({
  agentV3Adapter: {} as any,
  fetchAgentV3HealthSnapshot: vi.fn(async () => ({
    healthy: true,
    payload: {}
  }))
}))

import {
  checkEngineHealth,
  engineSupportsWorkspacePayload,
  engineUsesRuntimeMeta,
  getControlPlanePrefix,
  getEngineOptions
} from '@/services/coding-agent/engineCapabilities'

describe('engineCapabilities', () => {
  it('返回引擎列表', () => {
    const options = getEngineOptions()
    expect(options.map((item) => item.id)).toEqual(['opencode', 'agentv3'])
  })

  it('控制面前缀按引擎正确返回', () => {
    expect(getControlPlanePrefix('opencode')).toBe('/api/opencode')
    expect(() => getControlPlanePrefix('agentv3')).toThrowError('不支持控制面前缀')
  })

  it('声明 runtime meta 与 workspace payload 能力', () => {
    expect(engineUsesRuntimeMeta('opencode')).toBe(true)
    expect(engineUsesRuntimeMeta('agentv3')).toBe(false)
    expect(engineSupportsWorkspacePayload('agentv3')).toBe(true)
    expect(engineSupportsWorkspacePayload('opencode')).toBe(false)
  })

  it('统一健康检查输出', async () => {
    const openCode = await checkEngineHealth('opencode')
    const agentV3 = await checkEngineHealth('agentv3')
    expect(openCode.healthy).toBe(true)
    expect(agentV3.detail).toContain('AgentV3')
  })
})
