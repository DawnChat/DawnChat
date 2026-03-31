import {
  ENGINE_AGENTV3,
  ENGINE_OPENCODE,
  type EngineId
} from '@/services/coding-agent/adapterRegistry'
import { fetchAgentV3HealthSnapshot } from '@/services/coding-agent/agentV3Adapter'
import { fetchOpenCodeHealthSnapshot } from '@/services/coding-agent/openCodeAdapter'

export interface EngineOption {
  id: EngineId
  label: string
}

const ENGINE_OPTIONS: EngineOption[] = [
  { id: ENGINE_OPENCODE, label: 'OpenCode' },
  { id: ENGINE_AGENTV3, label: 'AgentV3' }
]

export function getEngineOptions(): EngineOption[] {
  return ENGINE_OPTIONS.slice()
}

export function getControlPlanePrefix(engineId: EngineId): string {
  if (engineId === ENGINE_OPENCODE) {
    return '/api/opencode'
  }
  throw new Error(`引擎 ${engineId} 不支持控制面前缀`)
}

export function engineUsesRuntimeMeta(engineId: EngineId): boolean {
  return engineId === ENGINE_OPENCODE
}

export function engineSupportsWorkspacePayload(engineId: EngineId): boolean {
  return engineId === ENGINE_AGENTV3
}

export function engineUsesWorkspaceSystemPrompt(engineId: EngineId): boolean {
  return engineId === ENGINE_OPENCODE || engineId === ENGINE_AGENTV3
}

export async function checkEngineHealth(engineId: EngineId): Promise<{ healthy: boolean; detail: string }> {
  if (engineId === ENGINE_OPENCODE) {
    const snapshot = await fetchOpenCodeHealthSnapshot()
    const healthy = snapshot.healthy && ['running', 'starting'].includes(snapshot.backendStatus)
    return {
      healthy,
      detail: healthy ? 'OpenCode 已连接' : `OpenCode 状态异常: ${snapshot.backendStatus || 'unknown'}`
    }
  }

  if (engineId === ENGINE_AGENTV3) {
    await fetchAgentV3HealthSnapshot()
    return {
      healthy: true,
      detail: 'AgentV3 已连接'
    }
  }
  throw new Error(`未知引擎: ${engineId}`)
}
