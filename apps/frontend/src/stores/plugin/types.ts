import type { Plugin } from '@/features/plugin/types'
import type { MobilePublishResult, MobilePublishStatusResult, MobilePublishTask } from '@/services/plugins/mobilePublishApi'
import type { WebPublishResult, WebPublishStatusResult, WebPublishTask } from '@/services/plugins/webPublishApi'

export interface PluginInstallProgress {
  plugin_id: string
  version?: string
  status: string
  message: string
  progress: number
  error?: string | null
}

export interface MarketPlugin extends Plugin {
  installed: boolean
  installed_version?: string | null
  action: 'install' | 'installed' | 'open' | 'update'
}

export interface TemplateCacheInfo {
  template_id: string
  template_name?: string
  version: string
  source_dir: string
  cached: boolean
}

export interface CreatePluginPayload {
  template_id: string
  app_type: 'desktop' | 'web' | 'mobile'
  name: string
  plugin_id: string
  description: string
  owner_email: string
  owner_user_id: string
  is_main_assistant?: boolean
}

export interface WebPublishState {
  loading: boolean
  error: string | null
  last_result: WebPublishResult | null
  last_status: WebPublishStatusResult | null
  active_task: WebPublishTask | null
}

export interface MobilePublishState {
  loading: boolean
  error: string | null
  last_result: MobilePublishResult | null
  last_status: MobilePublishStatusResult | null
  active_task: MobilePublishTask | null
}

export type LifecycleOperationType =
  | 'create_dev_session'
  | 'start_dev_session'
  | 'restart_dev_session'
  | 'start_runtime'

export type LifecycleNavigationIntent = 'workbench' | 'runtime' | 'none'
export type LifecycleUiMode = 'modal' | 'inline'
export type BuildHubFilter = 'all' | 'recent' | 'installed' | 'market'

export interface BuildHubRecentSession {
  pluginId: string
  visitedAt: number
}

export interface RunLifecycleOperationOptions {
  operationType: LifecycleOperationType
  payload: Record<string, unknown>
  navigationIntent?: LifecycleNavigationIntent
  from?: string
  uiMode?: LifecycleUiMode
  completionMessage?: string
}

export interface LifecycleTaskProgress {
  stage: string
  stage_label: string
  progress: number
  message: string
  eta_seconds?: number | null
  retryable?: boolean
  details?: string[]
}

export interface LifecycleTask {
  task_id: string
  operation_type: LifecycleOperationType
  plugin_id: string
  app_type: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  updated_at: string
  elapsed_seconds: number
  progress: LifecycleTaskProgress
  result?: Record<string, unknown> | null
  error?: { message?: string; code?: string } | null
}
