import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  createWorkbenchProject,
  deleteWorkbenchProject,
  getWorkbenchProject,
  listWorkbenchProjects,
  onWorkbenchProjectsUpdated,
  updateWorkbenchProject,
  type WorkbenchProject
} from '@/stores/workbenchProjectsApi'
import { logger } from '@/utils/logger'

export const useWorkbenchProjectsStore = defineStore('workbenchProjects', () => {
  const projects = ref<WorkbenchProject[]>([])
  const projectsLoaded = ref(false)
  const isLoadingProjects = ref(false)
  const isCreatingProject = ref(false)
  const projectById = ref<Record<string, WorkbenchProject>>({})
  let stopExternalSync: (() => void) | null = null
  let loadPromise: Promise<WorkbenchProject[]> | null = null

  const orderedProjects = computed(() => {
    return [...projects.value].sort((a, b) => {
      const aTime = new Date(a.updated_at || a.created_at || 0).getTime()
      const bTime = new Date(b.updated_at || b.created_at || 0).getTime()
      return bTime - aTime
    })
  })

  function syncProjectMap(rows: WorkbenchProject[]) {
    const nextMap: Record<string, WorkbenchProject> = {}
    for (const row of rows) {
      nextMap[row.id] = row
    }
    projectById.value = nextMap
  }

  async function loadProjects(force = false): Promise<WorkbenchProject[]> {
    if (loadPromise && !force) {
      return loadPromise
    }
    isLoadingProjects.value = true
    loadPromise = listWorkbenchProjects()
      .then((rows) => {
        projects.value = rows
        projectsLoaded.value = true
        syncProjectMap(rows)
        return rows
      })
      .catch((error) => {
        logger.error('workbench_projects_load_failed', error)
        throw error
      })
      .finally(() => {
        isLoadingProjects.value = false
        loadPromise = null
      })
    return loadPromise
  }

  async function refreshProject(projectId: string): Promise<WorkbenchProject | null> {
    const normalizedId = String(projectId || '').trim()
    if (!normalizedId) return null
    const project = await getWorkbenchProject(normalizedId)
    if (!project) {
      delete projectById.value[normalizedId]
      projects.value = projects.value.filter((item) => item.id !== normalizedId)
      return null
    }
    projectById.value = {
      ...projectById.value,
      [normalizedId]: project
    }
    const index = projects.value.findIndex((item) => item.id === normalizedId)
    if (index >= 0) {
      projects.value.splice(index, 1, project)
    } else {
      projects.value = [project, ...projects.value]
    }
    return project
  }

  async function ensureProject(projectId: string): Promise<WorkbenchProject | null> {
    const normalizedId = String(projectId || '').trim()
    if (!normalizedId) return null
    if (projectById.value[normalizedId]) {
      return projectById.value[normalizedId]
    }
    return refreshProject(normalizedId)
  }

  async function createProject(payload: { name?: string; projectType?: string } = {}): Promise<WorkbenchProject> {
    isCreatingProject.value = true
    try {
      const project = await createWorkbenchProject(payload)
      projectById.value = {
        ...projectById.value,
        [project.id]: project
      }
      projects.value = [project, ...projects.value.filter((item) => item.id !== project.id)]
      projectsLoaded.value = true
      return project
    } finally {
      isCreatingProject.value = false
    }
  }

  async function renameProject(projectId: string, name: string): Promise<WorkbenchProject> {
    const project = await updateWorkbenchProject(projectId, { name })
    await refreshProject(project.id)
    return project
  }

  async function updateProject(projectId: string, payload: { name?: string; projectType?: string }): Promise<WorkbenchProject> {
    const project = await updateWorkbenchProject(projectId, payload)
    await refreshProject(project.id)
    return project
  }

  async function removeProject(projectId: string): Promise<void> {
    await deleteWorkbenchProject(projectId)
    delete projectById.value[projectId]
    projects.value = projects.value.filter((item) => item.id !== projectId)
  }

  function ensureSyncListener() {
    if (stopExternalSync) return
    stopExternalSync = onWorkbenchProjectsUpdated(() => {
      loadProjects(true).catch((error) => {
        logger.error('workbench_projects_external_refresh_failed', error)
      })
    })
  }

  return {
    projects,
    orderedProjects,
    projectById,
    projectsLoaded,
    isLoadingProjects,
    isCreatingProject,
    loadProjects,
    ensureProject,
    refreshProject,
    createProject,
    renameProject,
    updateProject,
    removeProject,
    ensureSyncListener
  }
})
