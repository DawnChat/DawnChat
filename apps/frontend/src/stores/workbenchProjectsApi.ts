import { buildBackendUrl } from '@/utils/backendUrl'

export interface WorkbenchProject {
  id: string
  name: string
  project_type: string
  workspace_path: string
  created_at: string
  updated_at: string
}

const WORKBENCH_PROJECTS_UPDATED_EVENT = 'workbench-projects-updated'

function emitProjectsUpdated() {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(WORKBENCH_PROJECTS_UPDATED_EVENT))
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`${response.status} ${detail}`.trim())
  }
  const payload = await response.json().catch(() => ({}))
  return (payload?.data || payload) as T
}

export function onWorkbenchProjectsUpdated(handler: () => void): () => void {
  if (typeof window === 'undefined') {
    return () => {}
  }
  window.addEventListener(WORKBENCH_PROJECTS_UPDATED_EVENT, handler)
  return () => {
    window.removeEventListener(WORKBENCH_PROJECTS_UPDATED_EVENT, handler)
  }
}

export async function listWorkbenchProjects(): Promise<WorkbenchProject[]> {
  const response = await fetch(buildBackendUrl('/api/workbench/projects'))
  return parseJsonResponse<WorkbenchProject[]>(response)
}

export async function getWorkbenchProject(projectId: string): Promise<WorkbenchProject | null> {
  const response = await fetch(buildBackendUrl(`/api/workbench/projects/${encodeURIComponent(projectId)}`))
  if (response.status === 404) {
    return null
  }
  return parseJsonResponse<WorkbenchProject>(response)
}

export async function createWorkbenchProject(payload: {
  name?: string
  projectType?: string
} = {}): Promise<WorkbenchProject> {
  const response = await fetch(buildBackendUrl('/api/workbench/projects'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: payload.name,
      project_type: payload.projectType
    })
  })
  const project = await parseJsonResponse<WorkbenchProject>(response)
  emitProjectsUpdated()
  return project
}

export async function updateWorkbenchProject(
  projectId: string,
  payload: {
    name?: string
    projectType?: string
  }
): Promise<WorkbenchProject> {
  const response = await fetch(buildBackendUrl(`/api/workbench/projects/${encodeURIComponent(projectId)}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...(payload.name === undefined ? {} : { name: payload.name }),
      ...(payload.projectType === undefined ? {} : { project_type: payload.projectType })
    })
  })
  const project = await parseJsonResponse<WorkbenchProject>(response)
  emitProjectsUpdated()
  return project
}

export async function deleteWorkbenchProject(projectId: string): Promise<void> {
  const response = await fetch(buildBackendUrl(`/api/workbench/projects/${encodeURIComponent(projectId)}`), {
    method: 'DELETE'
  })
  await parseJsonResponse<boolean>(response)
  emitProjectsUpdated()
}
