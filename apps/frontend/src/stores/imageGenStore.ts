/**
 * Image Generation Store
 * 
 * Manages state for image generation models and ComfyUI service.
 * Download progress is obtained from backend via loadModels().
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { 
  ImageGenModel, 
  ImageGenWorkflow, 
  ImageGenServiceStatus,
  ImageGenTaskType,
  DownloadStatus
} from '@/types/environment'
import { logger } from '@/utils/logger'
import { buildBackendUrl } from '@/utils/backendUrl'

const getApiBase = () => buildBackendUrl('/api/image-gen')

/**
 * Download progress for a model (for environmentStore integration)
 */
interface ModelDownloadProgress {
  modelId: string
  status: DownloadStatus
  progress: number
  downloadedBytes: number
  totalBytes: number
  speed?: string
  message?: string
  errorMessage?: string
}

export const useImageGenStore = defineStore('imageGen', () => {
  // ============ State ============
  
  /** All available models */
  const models = ref<ImageGenModel[]>([])
  
  /** All workflow templates */
  const workflows = ref<ImageGenWorkflow[]>([])
  
  /** Service status */
  const serviceStatus = ref<ImageGenServiceStatus>({
    installed: false,
    running: false,
    ready: false,
    hasModels: false,
    canStart: false,
    installedCount: 0,
    totalModels: 0
  })
  
  /** Download progress by model ID (synced from models list) */
  const downloadProgress = ref<Map<string, ModelDownloadProgress>>(new Map())
  
  /** Loading states */
  const loading = ref({
    models: false,
    workflows: false,
    status: false,
    starting: false,
    stopping: false
  })
  
  /** Current active task type filter */
  const activeTaskType = ref<ImageGenTaskType | 'all'>('all')
  
  // ============ Computed ============
  
  /** Installed models */
  const installedModels = computed(() => 
    models.value.filter((m: ImageGenModel) => m.installed)
  )
  
  /** Models filtered by active task type */
  const filteredModels = computed(() => {
    if (activeTaskType.value === 'all') {
      return models.value
    }
    return models.value.filter((m: ImageGenModel) => 
      m.types.includes(activeTaskType.value as ImageGenTaskType)
    )
  })
  
  /** Workflows filtered by active task type */
  const filteredWorkflows = computed(() => {
    if (activeTaskType.value === 'all') {
      return workflows.value
    }
    return workflows.value.filter((w: ImageGenWorkflow) => 
      w.taskType === activeTaskType.value
    )
  })
  
  /** Available workflows (have all required models) */
  const availableWorkflows = computed(() => 
    workflows.value.filter((w: ImageGenWorkflow) => w.available)
  )
  
  /** Active downloads (for environmentStore) */
  const activeDownloads = computed(() => 
    (Array.from(downloadProgress.value.values()) as ModelDownloadProgress[])
      .filter(p => ['pending', 'downloading'].includes(p.status))
  )
  
  /** Has at least one model installed */
  const hasModelsInstalled = computed(() => 
    installedModels.value.length > 0
  )
  
  /** Has any active downloads */
  const hasActiveDownloads = computed(() => 
    activeDownloads.value.length > 0
  )
  
  // ============ Actions ============
  
  /**
   * Load all models from API and sync download progress
   */
  async function loadModels() {
    loading.value.models = true
    try {
      models.value = []
      downloadProgress.value.clear()
    } finally {
      loading.value.models = false
    }
  }
  
  /**
   * Load workflow templates from API
   */
  async function loadWorkflows() {
    loading.value.workflows = true
    
    try {
      const response = await fetch(`${getApiBase()}/workflows`)
      if (!response.ok) {
        throw new Error(`Failed to load workflows: ${response.status}`)
      }
      
      const data = await response.json()
      
      workflows.value = data.workflows.map((w: any) => ({
        id: w.id,
        name: w.name,
        description: w.description,
        taskType: w.task_type,
        requiredModels: w.required_models,
        previewImage: w.preview_image,
        inputSchema: w.input_schema,
        available: w.available,
        missingModels: w.missing_models || []
      }))
      
      logger.info('🔧 Loaded image gen workflows', { count: workflows.value.length })
      
    } catch (error) {
      logger.error('Failed to load workflows', { error })
    } finally {
      loading.value.workflows = false
    }
  }
  
  /**
   * Load service status from API
   */
  async function loadStatus() {
    loading.value.status = true
    
    try {
      const response = await fetch(`${getApiBase()}/status`)
      if (!response.ok) {
        throw new Error(`Failed to load status: ${response.status}`)
      }
      
      const data = await response.json()
      
      serviceStatus.value = {
        installed: data.installed,
        running: data.running,
        ready: data.ready,
        hasModels: data.has_models,
        canStart: data.can_start,
        startBlockedReason: data.start_blocked_reason,
        installedCount: data.installed_count || 0,
        totalModels: data.total_models || 0
      }
      
      logger.info('🔍 Loaded image gen status', serviceStatus.value)
      
    } catch (error) {
      logger.error('Failed to load status', { error })
      throw error
    } finally {
      loading.value.status = false
    }
  }
  
  /**
   * Download a model
   * @param modelId - Model ID to download
   * @param useMirror - Whether to use mirror acceleration (default true)
   */
  async function downloadModel(modelId: string, useMirror = true) {
    logger.warn('ComfyUI 模型下载已迁移到插件 UI', { modelId, useMirror })
    throw new Error('ComfyUI 模型管理已迁移到插件页面')
  }
  
  /**
   * Pause a download (called by environmentStore)
   */
  async function pauseDownload(modelId: string) {
    logger.warn('ComfyUI 模型下载暂停已迁移到插件 UI', { modelId })
  }
  
  /**
   * Cancel a download (called by environmentStore)
   */
  async function cancelDownload(modelId: string) {
    downloadProgress.value.delete(modelId)
    logger.warn('ComfyUI 模型下载取消已迁移到插件 UI', { modelId })
  }
  
  /**
   * Resume a paused/failed download (called by environmentStore)
   */
  async function resumeDownload(modelId: string, useMirror = true) {
    logger.warn('ComfyUI 模型下载恢复已迁移到插件 UI', { modelId, useMirror })
  }
  
  /**
   * Delete a model
   */
  async function deleteModel(modelId: string) {
    logger.warn('ComfyUI 模型删除已迁移到插件 UI', { modelId })
  }
  
  /**
   * Start the ComfyUI service
   */
  async function startService() {
    loading.value.starting = true
    
    try {
      const response = await fetch(`${getApiBase()}/start`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to start service')
      }
      
      const data = await response.json()
      
      serviceStatus.value.running = true
      serviceStatus.value.ready = true
      
      logger.info('🚀 ComfyUI service started', { baseUrl: data.base_url })
      
      await loadStatus()
      
    } catch (error) {
      logger.error('Failed to start service', { error })
      throw error
    } finally {
      loading.value.starting = false
    }
  }
  
  /**
   * Stop the ComfyUI service
   */
  async function stopService() {
    loading.value.stopping = true
    
    try {
      const response = await fetch(`${getApiBase()}/stop`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        throw new Error('Failed to stop service')
      }
      
      serviceStatus.value.running = false
      serviceStatus.value.ready = false
      
      logger.info('🛑 ComfyUI service stopped')
      
      await loadStatus()
      
    } catch (error) {
      logger.error('Failed to stop service', { error })
      throw error
    } finally {
      loading.value.stopping = false
    }
  }
  
  /**
   * Set the active task type filter
   */
  function setActiveTaskType(taskType: ImageGenTaskType | 'all') {
    activeTaskType.value = taskType
  }
  
  /**
   * Initialize the store
   */
  async function initialize() {
    await Promise.all([
      loadModels(),
      loadWorkflows(),
      loadStatus()
    ])
  }
  
  /**
   * Refresh all data
   */
  async function refresh() {
    await initialize()
  }
  
  // ============ Return ============
  
  return {
    // State
    models,
    workflows,
    serviceStatus,
    downloadProgress,
    loading,
    activeTaskType,
    
    // Computed
    installedModels,
    filteredModels,
    filteredWorkflows,
    availableWorkflows,
    activeDownloads,
    hasModelsInstalled,
    hasActiveDownloads,
    
    // Actions
    loadModels,
    loadWorkflows,
    loadStatus,
    downloadModel,
    pauseDownload,
    cancelDownload,
    resumeDownload,
    deleteModel,
    startService,
    stopService,
    setActiveTaskType,
    initialize,
    refresh
  }
})
