import type { EngineAdapter } from './engineAdapter'
import { agentV3Adapter } from './agentV3Adapter'
import { openCodeAdapter } from './openCodeAdapter'

export const ENGINE_OPENCODE = 'opencode'
export const ENGINE_AGENTV3 = 'agentv3'
export type EngineId = typeof ENGINE_OPENCODE | typeof ENGINE_AGENTV3

const ADAPTER_BY_ENGINE: Record<EngineId, EngineAdapter> = {
  [ENGINE_OPENCODE]: openCodeAdapter,
  [ENGINE_AGENTV3]: agentV3Adapter
}

export function isEngineId(engineId: string): engineId is EngineId {
  return engineId === ENGINE_OPENCODE || engineId === ENGINE_AGENTV3
}

export function getEngineAdapter(engineId: string): EngineAdapter {
  if (!isEngineId(engineId)) {
    throw new Error(`未知 coding 引擎: ${engineId}`)
  }
  return ADAPTER_BY_ENGINE[engineId]
}
