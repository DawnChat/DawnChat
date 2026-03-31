import type { Ref } from 'vue'
import { buildBackendUrl } from '@/utils/backendUrl'
import { logger } from '@/utils/logger'
import { ENGINE_AGENTV3, ENGINE_OPENCODE, type EngineId } from '@/services/coding-agent/adapterRegistry'
import { getControlPlanePrefix } from '@/services/coding-agent/engineCapabilities'
import type { EngineAdapter } from '@/services/coding-agent/engineAdapter'
import type { ModelOption } from '@/features/coding-agent/store/types'

export function createEngineConfigBridge(input: {
  selectedEngine: Ref<EngineId>
  selectedAgent: Ref<string>
  selectedModelId: Ref<string>
  availableModels: Ref<ModelOption[]>
  activeSessionId: Ref<string>
  getActiveAdapter: () => EngineAdapter
  persistSelectedAgent: (id: string) => void
  persistSelectedModel: (id: string) => void
}) {
  const {
    selectedEngine,
    selectedAgent,
    selectedModelId,
    availableModels,
    activeSessionId,
    getActiveAdapter,
    persistSelectedAgent,
    persistSelectedModel
  } = input

  async function patchControlPlaneConfig(engineId: EngineId, payload: Record<string, unknown>): Promise<boolean> {
    const resp = await fetch(buildBackendUrl(`${getControlPlanePrefix(engineId)}/config`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!resp.ok) {
      const detail = await resp.text().catch(() => '')
      const softDefaultAgentFailure =
        engineId === ENGINE_OPENCODE &&
        resp.status === 400 &&
        typeof payload.default_agent === 'string' &&
        String(payload.default_agent || '').trim().length > 0
      if (softDefaultAgentFailure) {
        logger.info('[codingAgentStore] skip unsupported opencode default_agent patch', {
          defaultAgent: String(payload.default_agent || ''),
          status: resp.status,
          detail
        })
        return false
      }
      throw new Error(`patch config failed: ${resp.status} ${detail}`)
    }
    return true
  }

  async function patchOpenCodeConfig(payload: Record<string, unknown>): Promise<boolean> {
    return patchControlPlaneConfig(ENGINE_OPENCODE, payload)
  }

  async function patchAgentV3SessionConfig(payload: {
    agent?: string
    model?: {
      providerID: string
      modelID: string
    }
  }) {
    if (selectedEngine.value !== ENGINE_AGENTV3) return
    const sessionID = activeSessionId.value
    if (!sessionID) return
    const adapter = getActiveAdapter()
    if (!adapter.updateSessionConfig) return
    await adapter.updateSessionConfig(sessionID, payload)
  }

  function selectAgent(agent: string) {
    selectedAgent.value = agent
    persistSelectedAgent(agent)
    if (selectedEngine.value === ENGINE_OPENCODE) {
      patchOpenCodeConfig({ default_agent: agent }).catch((err) => {
        logger.warn('[codingAgentStore] patch agent failed', err)
      })
      return
    }
    if (selectedEngine.value === ENGINE_AGENTV3) {
      patchAgentV3SessionConfig({ agent }).catch((err) => {
        logger.warn('[codingAgentStore] patch agentv3 session config failed', err)
      })
    }
  }

  function selectModel(id: string) {
    selectedModelId.value = id
    persistSelectedModel(id)
    const model = availableModels.value.find((item) => item.id === id)
    if (!model) return
    if (selectedEngine.value === ENGINE_OPENCODE) {
      patchOpenCodeConfig({ model: `${model.providerID}/${model.modelID}` }).catch((err) => {
        logger.warn('[codingAgentStore] patch model failed', err)
      })
      return
    }
    if (selectedEngine.value === ENGINE_AGENTV3) {
      patchAgentV3SessionConfig({
        model: {
          providerID: model.providerID,
          modelID: model.modelID
        }
      }).catch((err) => {
        logger.warn('[codingAgentStore] patch agentv3 model failed', err)
      })
    }
  }

  return {
    patchOpenCodeConfig,
    patchAgentV3SessionConfig,
    selectAgent,
    selectModel
  }
}
