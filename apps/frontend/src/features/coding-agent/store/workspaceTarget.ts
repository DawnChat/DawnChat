import type { WorkbenchProject } from '@/stores/workbenchProjectsApi'
import type { WorkspaceResolveOptions, WorkspaceTarget } from '@/features/coding-agent/store/types'

function normalizeWorkspaceId(value: string): string {
  return String(value || '').trim()
}

export function createPluginDevWorkspaceTarget(pluginId: string): WorkspaceTarget {
  const normalizedPluginId = normalizeWorkspaceId(pluginId)
  return {
    id: `plugin:${normalizedPluginId}`,
    kind: 'plugin-dev',
    displayName: normalizedPluginId,
    appType: 'desktop',
    workspacePath: '',
    preferredEntry: '',
    preferredDirectories: [],
    hints: [],
    defaultAgent: 'build',
    sessionStrategy: 'multi',
    pluginId: normalizedPluginId
  }
}

export function createWorkbenchWorkspaceTarget(
  project: Pick<WorkbenchProject, 'id' | 'name' | 'project_type'> & Partial<Pick<WorkbenchProject, 'workspace_path'>>
): WorkspaceTarget {
  const projectId = normalizeWorkspaceId(project.id)
  const displayName = String(project.name || '').trim() || 'Untitled Workspace'
  const projectType = String(project.project_type || 'chat').trim() || 'chat'
  const workspacePath = String(project.workspace_path || '').trim()
  return {
    id: `workbench:${projectId}`,
    kind: 'workbench-general',
    displayName,
    appType: projectType,
    workspacePath,
    preferredEntry: '',
    preferredDirectories: [],
    hints: [
      '当前场景是 DawnChat Workbench 通用聊天模式。',
      '优先基于用户当前上下文给出通用协助，不要假设存在插件开发预览或源码圈选能力。'
    ],
    defaultAgent: 'general',
    sessionStrategy: 'single',
    projectId
  }
}

export function resolveWorkspaceTarget(options?: WorkspaceResolveOptions): WorkspaceTarget | null {
  if (options?.workspaceTarget) {
    return options.workspaceTarget
  }
  const pluginId = String(options?.pluginId || '').trim()
  if (!pluginId) {
    return null
  }
  return createPluginDevWorkspaceTarget(pluginId)
}
