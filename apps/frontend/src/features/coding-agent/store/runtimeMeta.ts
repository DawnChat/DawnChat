import type { Ref } from 'vue'
import { buildBackendUrl } from '@/utils/backendUrl'
import { logger } from '@/utils/logger'
import type { EngineId } from '@/services/coding-agent/adapterRegistry'
import { engineUsesRuntimeMeta, getControlPlanePrefix } from '@/services/coding-agent/engineCapabilities'
import { getWorkbenchProject } from '@/stores/workbenchProjectsApi'
import type { WorkspaceResolveOptions, WorkspaceTarget } from '@/features/coding-agent/store/types'

interface ModelOption {
  id: string
  label: string
  providerID: string
  modelID: string
}

interface AgentOption {
  id: string
  label: string
  description: string
  mode: string
  hidden: boolean
}

interface OpenCodeRulesStatus {
  enabled: boolean
  current_version?: string
  current_dir?: string
  updated_at?: string
  reason?: string
}

function normalizePluginWorkspaceTarget(payload: any, pluginId: string): WorkspaceTarget {
  const appType = String(payload?.app_type || payload?.appType || 'desktop')
  const workspacePath = String(payload?.workspace_path || payload?.workspacePath || '')
  const isWebLike = appType === 'web' || appType === 'mobile'
  const preferredEntry = String(
    payload?.preferred_entry ||
      payload?.preferredEntry ||
      (isWebLike ? 'web-src/src/App.vue' : 'src/main.py')
  )
  const preferredDirectoriesRaw = Array.isArray(payload?.preferred_directories)
    ? payload.preferred_directories
    : Array.isArray(payload?.preferredDirectories)
      ? payload.preferredDirectories
      : []
  const hintsRaw = Array.isArray(payload?.hints) ? payload.hints : []
  return {
    id: `plugin:${pluginId}`,
    kind: 'plugin-dev',
    displayName: pluginId,
    appType,
    workspacePath,
    preferredEntry,
    preferredDirectories: preferredDirectoriesRaw.map((item: unknown) => String(item || '')).filter(Boolean),
    hints: hintsRaw.map((item: unknown) => String(item || '')).filter(Boolean),
    defaultAgent: 'build',
    sessionStrategy: 'multi',
    pluginId
  }
}

function normalizeWorkbenchWorkspaceTarget(payload: any, projectId: string): WorkspaceTarget {
  const workspacePath = String(payload?.workspace_path || payload?.workspacePath || '')
  const projectType = String(payload?.project_type || payload?.app_type || payload?.appType || 'chat')
  const displayName = String(payload?.name || payload?.display_name || payload?.displayName || projectId).trim() || projectId
  const preferredDirectoriesRaw = Array.isArray(payload?.preferred_directories)
    ? payload.preferred_directories
    : Array.isArray(payload?.preferredDirectories)
      ? payload.preferredDirectories
      : []
  const hintsRaw = Array.isArray(payload?.hints) ? payload.hints : []
  return {
    id: `workbench:${projectId}`,
    kind: 'workbench-general',
    displayName,
    appType: projectType,
    workspacePath,
    preferredEntry: String(payload?.preferred_entry || payload?.preferredEntry || ''),
    preferredDirectories: preferredDirectoriesRaw.map((item: unknown) => String(item || '')).filter(Boolean),
    hints: hintsRaw.map((item: unknown) => String(item || '')).filter(Boolean),
    defaultAgent: String(payload?.default_agent || payload?.defaultAgent || 'general'),
    sessionStrategy: 'single',
    projectId
  }
}

export function parseProviderModels(data: any): ModelOption[] {
  const providersRaw = Array.isArray(data?.providers) ? data.providers : []
  const providers = providersRaw.filter((provider: any) => {
    const providerID = String(provider?.id || provider?.providerID || '')
    if (providerID === 'dawnchat-local') return true
    if (provider?.available === false) return false
    if (provider?.configured === false) return false
    return true
  })
  const sourceProviders = providers.length > 0 ? providers : providersRaw
  const result: ModelOption[] = []
  for (const provider of sourceProviders) {
    const providerID = String(provider?.id || provider?.providerID || '')
    const models = provider?.models || {}
    if (!providerID) continue

    if (Array.isArray(models)) {
      for (const item of models) {
        if (typeof item === 'string') {
          const modelID = String(item || '')
          if (!modelID) continue
          result.push({
            id: `${providerID}/${modelID}`,
            label: modelID,
            providerID,
            modelID
          })
          continue
        }
        const modelID = String(item?.id || item?.modelID || '')
        if (!modelID) continue
        result.push({
          id: `${providerID}/${modelID}`,
          label: String(item?.name || modelID),
          providerID,
          modelID
        })
      }
    } else if (typeof models === 'object') {
      for (const [modelID, modelConfig] of Object.entries(models)) {
        const name = (modelConfig as any)?.name || modelID
        result.push({
          id: `${providerID}/${modelID}`,
          label: String(name),
          providerID,
          modelID: String(modelID)
        })
      }
    }
  }
  return result
}

export function createRuntimeMetaLoader(input: {
  selectedEngine: Ref<EngineId>
  availableModels: Ref<ModelOption[]>
  availableAgentOptions: Ref<AgentOption[]>
  selectedModelId: Ref<string>
  selectedAgent: Ref<string>
  globalError: Ref<string | null>
  rulesStatus: Ref<OpenCodeRulesStatus | null>
  workspaceProfile: Ref<WorkspaceTarget | null>
  persistSelectedAgent: (id: string) => void
  selectModel: (id: string) => void
}) {
  const {
    selectedEngine,
    availableModels,
    availableAgentOptions,
    selectedModelId,
    selectedAgent,
    globalError,
    rulesStatus,
    workspaceProfile,
    persistSelectedAgent,
    selectModel
  } = input

  function setAvailableAgents(rows: unknown[]) {
    const normalized = (Array.isArray(rows) ? rows : [])
      .map((item: any) => {
        const id = String(item?.id || item?.name || '').trim()
        if (!id) return null
        const mode = String(item?.mode || 'primary').trim().toLowerCase()
        const hidden = Boolean(item?.hidden)
        return {
          id,
          label: String(item?.label || item?.name || id),
          description: String(item?.description || ''),
          mode,
          hidden
        } satisfies AgentOption
      })
      .filter((item): item is AgentOption => Boolean(item))
      .filter((item) => item.mode !== 'subagent' && item.hidden !== true)

    const fallback: AgentOption[] = [
      { id: 'build', label: 'build', description: '', mode: 'primary', hidden: false },
      { id: 'plan', label: 'plan', description: '', mode: 'primary', hidden: false }
    ]
    availableAgentOptions.value = normalized.length > 0 ? normalized : fallback
    if (!availableAgentOptions.value.some((item) => item.id === selectedAgent.value)) {
      selectedAgent.value = availableAgentOptions.value[0]?.id || 'build'
      persistSelectedAgent(selectedAgent.value)
    }
  }

  async function loadWorkspaceProfile(target: WorkspaceTarget) {
    if (target.kind === 'workbench-general') {
      const projectId = String(target.projectId || '').trim()
      if (!projectId) {
        workspaceProfile.value = target
        return
      }
      const project = await getWorkbenchProject(projectId)
      workspaceProfile.value = project
        ? normalizeWorkbenchWorkspaceTarget(project, projectId)
        : target
      return
    }
    if (target.kind !== 'plugin-dev' || !target.pluginId) {
      workspaceProfile.value = target
      return
    }
    const pluginId = target.pluginId
    const response = await fetch(buildBackendUrl(`/api/plugins/${encodeURIComponent(pluginId)}`))
    if (!response.ok) {
      throw new Error(`插件工作区画像读取失败: ${response.status}`)
    }
    const payload = await response.json()
    const plugin = payload?.plugin || {}
    const appType = String(plugin?.app_type || 'desktop')
    const pluginPath = String(plugin?.plugin_path || '')
    const isWebLike = appType === 'web' || appType === 'mobile'
    workspaceProfile.value = normalizePluginWorkspaceTarget(
      {
        app_type: appType,
        workspace_path: pluginPath,
        preferred_entry: isWebLike ? 'web-src/src/App.vue' : 'src/main.py',
        preferred_directories:
          isWebLike
            ? ['web-src/src', 'web-src/src/components', 'web-src/src/views', 'web-src/src/composables', 'web-src/src/stores']
            : ['src', 'web-src/src'],
        hints:
          appType === 'web'
            ? [
                '这是纯前端 web 插件，请优先修改 web-src 下的 Vue 代码。',
                '不要假设项目中存在 Python 后端或桌面端入口。'
              ]
            : appType === 'mobile'
              ? [
                  '这是 mobile 插件，请优先修改 web-src 下的前端代码。',
                  '桌面端预览主要用于验证 UI，原生能力需要在移动端宿主里验证。'
                ]
            : ['这是桌面插件，可能同时包含 Python 后端与 Vue 前端。']
      },
      pluginId
    )
  }

  async function loadRuntimeMeta(options?: WorkspaceResolveOptions) {
    const target = options?.workspaceTarget || null
    if (!target) {
      throw new Error('Coding 引擎启动必须绑定 workspace target')
    }
    const engineId = selectedEngine.value
    if (!engineUsesRuntimeMeta(engineId)) {
      throw new Error(`当前引擎 ${engineId} 不支持控制面元数据加载`)
    }
    const engineLabel = 'OpenCode'
    const controlPrefix = getControlPlanePrefix(engineId)
    const startResp = await fetch(buildBackendUrl(`${controlPrefix}/start_with_workspace`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workspace_kind: target.kind,
        ...(target.pluginId ? { plugin_id: target.pluginId } : {}),
        ...(target.projectId ? { project_id: target.projectId } : {}),
        force_restart: Boolean(options?.forceRestart)
      })
    })
    if (!startResp.ok) {
      const payload = await startResp.json().catch(() => ({}))
      const detail = payload?.detail
      const message = String(detail?.message || payload?.message || '').trim()
      const reason = String(detail?.reason || '').trim()
      const failureReason = String(detail?.last_start_failure?.reason || detail?.health?.last_start_failure?.reason || '').trim()
      const hint = String(
        detail?.last_start_failure?.hint
        || detail?.health?.last_start_failure?.hint
        || ''
      ).trim()
      const segments = [
        message || `${engineLabel} 启动失败`,
        reason || failureReason ? `reason=${reason || failureReason}` : '',
        hint ? `hint=${hint.split('\n').slice(-1)[0]}` : '',
      ].filter(Boolean)
      throw new Error(`${engineLabel} 启动失败: ${startResp.status} ${segments.join(' | ')}`)
    }
    const startPayload = await startResp.json().catch(() => ({}))
    const startData = startPayload?.data || {}
    if (startData.workspace_profile) {
      workspaceProfile.value =
        target.kind === 'plugin-dev' && target.pluginId
          ? normalizePluginWorkspaceTarget(startData.workspace_profile, target.pluginId)
          : normalizeWorkbenchWorkspaceTarget(
              startData.workspace_profile,
              String(target.projectId || startData.workspace_profile?.project_id || '')
            )
    }

    const [providersResp, agentsResp, rulesResp] = await Promise.allSettled([
      fetch(buildBackendUrl(`${controlPrefix}/config/providers`)),
      fetch(buildBackendUrl(`${controlPrefix}/agents`)),
      fetch(buildBackendUrl(`${controlPrefix}/rules`))
    ])
    const errors: string[] = []

    if (providersResp.status === 'fulfilled') {
      if (providersResp.value.ok) {
        const providersJson = await providersResp.value.json()
        availableModels.value = parseProviderModels(providersJson?.data || {})
        if (!selectedModelId.value && availableModels.value.length > 0) {
          selectModel(availableModels.value[0].id)
        } else if (
          selectedModelId.value &&
          !availableModels.value.some((item) => item.id === selectedModelId.value) &&
          availableModels.value.length > 0
        ) {
          selectModel(availableModels.value[0].id)
        }
      } else {
        errors.push(`providers: ${providersResp.value.status}`)
      }
    } else {
      errors.push(`providers: ${String(providersResp.reason)}`)
    }

    if (agentsResp.status === 'fulfilled') {
      if (agentsResp.value.ok) {
        const agentsJson = await agentsResp.value.json()
        const data = agentsJson?.data
        const rows = Array.isArray(data) ? data : Array.isArray(data?.agents) ? data.agents : []
        setAvailableAgents(rows)
      } else {
        errors.push(`agents: ${agentsResp.value.status}`)
      }
    } else {
      errors.push(`agents: ${String(agentsResp.reason)}`)
    }

    if (rulesResp.status === 'fulfilled') {
      if (rulesResp.value.ok) {
        const rulesJson = await rulesResp.value.json()
        const data = rulesJson?.data || {}
        rulesStatus.value = {
          enabled: Boolean(data?.enabled),
          current_version: String(data?.current_version || ''),
          current_dir: String(data?.current_dir || ''),
          updated_at: String(data?.updated_at || ''),
          reason: String(data?.reason || '')
        }
      } else {
        errors.push(`rules: ${rulesResp.value.status}`)
      }
    } else {
      errors.push(`rules: ${String(rulesResp.reason)}`)
    }

    if (errors.length > 0) {
      const errorText = `${engineLabel} 元数据加载不完整 (${errors.join(', ')})`
      logger.warn('[codingAgentStore] loadRuntimeMeta partial failure', { engineId, errors })
      globalError.value = errorText
    }
  }

  return {
    setAvailableAgents,
    loadRuntimeMeta,
    loadWorkspaceProfile
  }
}
