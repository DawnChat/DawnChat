import { describe, expect, it, vi } from 'vitest'

const { mockedOpenCodeAdapter, mockedAgentV3Adapter } = vi.hoisted(() => ({
  mockedOpenCodeAdapter: { name: 'opencode' } as any,
  mockedAgentV3Adapter: { name: 'agentv3' } as any
}))

vi.mock('../openCodeAdapter', () => ({
  openCodeAdapter: mockedOpenCodeAdapter
}))

vi.mock('../agentV3Adapter', () => ({
  agentV3Adapter: mockedAgentV3Adapter
}))

import {
  ENGINE_AGENTV3,
  ENGINE_OPENCODE,
  getEngineAdapter,
  isEngineId
} from '@/services/coding-agent/adapterRegistry'

describe('adapterRegistry', () => {
  it('按引擎返回对应 adapter', () => {
    expect(getEngineAdapter(ENGINE_OPENCODE)).toBe(mockedOpenCodeAdapter)
    expect(getEngineAdapter(ENGINE_AGENTV3)).toBe(mockedAgentV3Adapter)
  })

  it('未知引擎会抛错而不是回退到 opencode', () => {
    expect(() => getEngineAdapter('unknown')).toThrowError('未知 coding 引擎')
  })

  it('isEngineId 正确识别合法引擎', () => {
    expect(isEngineId('opencode')).toBe(true)
    expect(isEngineId('agentv3')).toBe(true)
    expect(isEngineId('foo')).toBe(false)
  })
})
