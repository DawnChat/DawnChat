import type { PluginWorkbenchLayout } from '@/features/plugin/types'

export type PreviewResizeMode = 'preview_width' | 'agent_width_capped'

export interface WorkbenchLayoutProfile {
  layout: PluginWorkbenchLayout
  isAgentPreview: boolean
  showFileTree: boolean
  showModeSwitch: boolean
  allowRequirementsMode: boolean
  loadIwpFilesOnMount: boolean
  lockLayoutPersistence: boolean
  previewResizeMode: PreviewResizeMode
}

const PROFILE_BY_LAYOUT: Record<PluginWorkbenchLayout, WorkbenchLayoutProfile> = {
  default: {
    layout: 'default',
    isAgentPreview: false,
    showFileTree: true,
    showModeSwitch: true,
    allowRequirementsMode: true,
    loadIwpFilesOnMount: true,
    lockLayoutPersistence: false,
    previewResizeMode: 'preview_width',
  },
  agent_preview: {
    layout: 'agent_preview',
    isAgentPreview: true,
    showFileTree: false,
    showModeSwitch: false,
    allowRequirementsMode: false,
    loadIwpFilesOnMount: false,
    lockLayoutPersistence: true,
    previewResizeMode: 'agent_width_capped',
  },
}

export const getWorkbenchLayoutProfile = (layout: PluginWorkbenchLayout): WorkbenchLayoutProfile => {
  return PROFILE_BY_LAYOUT[layout]
}

