export type PluginState = 'stopped' | 'starting' | 'running' | 'stopping' | 'error'
export type PluginPreviewState = 'stopped' | 'starting' | 'running' | 'reloading' | 'error'
export type PluginPreviewFrontendMode = 'dev' | 'dist'
export type PluginPreviewInstallStatus = 'idle' | 'running' | 'success' | 'failed'
export type PluginWorkbenchLayout = 'default' | 'agent_preview'
export type PluginWorkbenchSurfaceMode = 'dev_split' | 'assistant_compact'
export type PluginRunMode = 'normal' | 'preview'

export interface PluginRuntime {
  port: number | null
  gradio_url: string | null
  started_at: string | null
}

export interface PluginPreviewRuntime {
  state: PluginPreviewState
  url: string | null
  backend_port: number | null
  frontend_port: number | null
  log_session_id?: string | null
  error_message: string | null
  frontend_mode?: PluginPreviewFrontendMode
  deps_ready?: boolean
  frontend_reachable?: boolean | null
  frontend_last_probe_at?: string | null
  install_status?: PluginPreviewInstallStatus
  install_error_message?: string | null
  workbench_layout?: PluginWorkbenchLayout
  has_iwp_requirements?: boolean
}

export interface PluginCapabilities {
  gradio: boolean
  cards: boolean
  chat: boolean
  tools: boolean
}

export interface PluginManifest {
  requires?: {
    ai?: boolean | { level?: string }
    local_ai?: boolean | { level?: string }
    cloud_ai?: boolean | { level?: string }
    tts?: boolean | { level?: string }
    asr?: boolean | { level?: string }
    ffmpeg?: boolean | { level?: string }
  }
}

export interface Plugin {
  id: string
  name: string
  version: string
  app_type?: 'desktop' | 'web' | 'mobile'
  description: string
  author: string
  icon: string
  tags: string[]
  state: PluginState
  is_official: boolean
  capabilities: PluginCapabilities
  runtime: PluginRuntime | null
  preview?: PluginPreviewRuntime
  error_message: string | null
  manifest?: PluginManifest
  plugin_path?: string | null
  source_type?: string
  owner_user_id?: string
  owner_email?: string
  template_id?: string
  created_at?: string
}
