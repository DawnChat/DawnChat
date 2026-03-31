/**
 * Models Store - 集中管理所有模型相关状态
 * 
 * 功能：
 * 1. 已安装模型管理
 * 2. HuggingFace 模型市场
 * 3. 模型下载任务管理
 * 4. 搜索和筛选
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { logger } from '@/utils/logger'
import { useI18n } from '@/composables/useI18n'
import { buildBackendUrl } from '@/utils/backendUrl'

// ============ 类型定义 ============

/**
 * 模型格式类型
 */
export type ModelFormat = 'gguf' | 'mlx'

export const REPO_DOWNLOAD_FILENAME = '__repo__'

/**
 * HuggingFace 模型信息（来自 lmstudio-community）
 */
export interface HuggingFaceModel {
  id: string                    // e.g. "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
  modelId: string               // 模型 ID
  author: string                // e.g. "lmstudio-community"
  sha: string                   // 版本 hash
  lastModified: string          // ISO 日期
  private: boolean
  disabled: boolean
  gated: boolean
  downloads: number
  likes: number
  tags: string[]
  pipeline_tag?: string
  library_name?: string
  format?: ModelFormat
  // 本地扩展字段
  siblings?: HuggingFaceFileSibling[]
}

/**
 * HuggingFace 文件信息
 */
export interface HuggingFaceFileSibling {
  rfilename: string             // 文件名
  size?: number                 // 文件大小（字节）
  lfs?: {
    sha256: string
    size: number
    pointer_size: number
  }
}

/**
 * 已安装的本地模型
 */
export interface InstalledModel {
  id: string                    // 唯一标识
  filename: string              // 文件名
  path: string                  // 文件路径
  size: number                  // 文件大小（字节）
  sizeDisplay: string           // 格式化大小
  modifiedAt: string            // 修改时间
  format: ModelFormat           // 模型格式 (gguf/mlx)
  // HuggingFace 来源信息
  huggingfaceId?: string        // HuggingFace 模型 ID
  author?: string               // 作者
}

/**
 * 下载任务
 */
export interface DownloadTask {
  modelId: string               // 模型 ID（HuggingFace ID）
  filename: string              // 文件名
  status: 'pending' | 'downloading' | 'paused' | 'completed' | 'failed' | 'cancelled'
  progress: number              // 0-100
  downloadedBytes: number
  totalBytes: number
  speed: string                 // e.g. "1.5 MB/s"
  eta: string                   // 剩余时间
  startedAt: string
  updatedAt: string
  error?: string
  // 用于取消下载
  abortController?: AbortController
  // 是否为恢复的下载
  isResuming?: boolean
  // Repo 下载时的文件进度（仅多文件下载时有效）
  completedFiles?: number
  totalFiles?: number
  currentFile?: string
}

/**
 * 可恢复的下载任务（来自后端）
 */
export interface PendingDownload {
  model_id: string
  filename: string
  total_bytes: number
  downloaded_bytes: number
  progress: number
  status: string
  use_mirror: boolean
  started_at: string
  updated_at: string
  error_message?: string
}

/**
 * 模型来源类型
 */
export type ModelSource = string

// ============ Store 定义 ============

export const useModelHubStore = defineStore('modelHub', () => {
  const { t } = useI18n()
  // ============ 状态 ============
  
  // 已安装模型
  const installedModels = ref<InstalledModel[]>([])
  const installedLoading = ref(false)
  
  // 模型市场
  const marketModels = ref<HuggingFaceModel[]>([])
  const marketLoading = ref(false)
  const marketError = ref<string | null>(null)
  const marketPage = ref(0)
  const marketHasMore = ref(true)
  const marketSearchQuery = ref('')
  
  // 下载任务
  const downloadTasks = ref<Map<string, DownloadTask>>(new Map())
  
  // 可恢复的下载任务
  const pendingDownloads = ref<PendingDownload[]>([])
  
  // 当前数据源
  const currentSource = ref<ModelSource>('lmstudio-community,mlx-community,onnx-community,Qwen')
  
  // 镜像设置
  const useMirror = ref(true)  // 默认使用镜像
  
  // 格式过滤
  const formatFilter = ref<{ gguf: boolean; mlx: boolean }>({
    gguf: true,
    mlx: false
  })
  
  // 检测是否为 macOS
  const isMacOS = navigator.platform.toLowerCase().includes('mac')
  
  // API 基础 URL
  const API_BASE = () => buildBackendUrl('/api')
  
  // 轮询定时器管理
  const pollingIntervals = ref<Map<string, ReturnType<typeof setInterval>>>(new Map())
  
  // ============ 计算属性 ============
  
  const downloadTasksList = computed(() => Array.from(downloadTasks.value.values()))
  
  const activeDownloads = computed(() => 
    downloadTasksList.value.filter(t => ['pending', 'downloading'].includes(t.status))
  )
  
  const pausedDownloads = computed(() => 
    downloadTasksList.value.filter(t => t.status === 'paused')
  )
  
  const isModelInstalled = computed(() => (modelId: string, filename: string) => {
    return installedModels.value.some(m => 
      m.huggingfaceId === modelId || m.filename === filename
    )
  })
  
  const isModelDownloading = computed(() => (modelId: string) => {
    const task = downloadTasks.value.get(modelId)
    return task && ['pending', 'downloading'].includes(task.status)
  })
  
  const isModelPaused = computed(() => (modelId: string, filename: string) => {
    const taskId = `${modelId}/${filename}`
    const task = downloadTasks.value.get(taskId)
    if (task && task.status === 'paused') return true
    // 也检查 pendingDownloads
    return pendingDownloads.value.some(p => 
      p.model_id === modelId && p.filename === filename
    )
  })
  
  // ============ 已安装模型管理 ============
  
  async function loadInstalledModels() {
    installedLoading.value = true
    try {
      logger.info('📦 加载已安装模型列表...')
      
      const res = await fetch(`${API_BASE()}/local-ai/models`)
      const data = await res.json()
      
      if (data.status === 'success') {
        installedModels.value = data.models.map((m: any) => ({
          id: m.id,
          filename: m.filename,
          path: m.path,
          size: m.size,
          sizeDisplay: m.size_display,
          modifiedAt: m.modified_at,
          format: detectModelFormat(m.filename),
          huggingfaceId: m.huggingface_id,
          author: m.author
        }))
        logger.info(`✅ 加载了 ${installedModels.value.length} 个已安装模型`)
      }
    } catch (error) {
      logger.error('❌ 加载已安装模型失败:', error)
    } finally {
      installedLoading.value = false
    }
  }
  
  async function deleteInstalledModel(modelId: string): Promise<boolean> {
    try {
      logger.info(`🗑️ 删除模型: ${modelId}`)
      
      const res = await fetch(`${API_BASE()}/local-ai/models/${encodeURIComponent(modelId)}`, {
        method: 'DELETE'
      })
      
      const data = await res.json()
      
      if (data.status === 'success') {
        // 从列表移除
        installedModels.value = installedModels.value.filter(m => m.id !== modelId)
        logger.info(`✅ 模型删除成功: ${modelId}`)
        return true
      } else {
        logger.error(`❌ 删除失败: ${data.message}`)
        return false
      }
    } catch (error) {
      logger.error('❌ 删除模型异常:', error)
      return false
    }
  }
  
  // ============ HuggingFace 模型市场 ============
  
  async function loadMarketModels(reset = false) {
    if (marketLoading.value) return
    if (!reset && !marketHasMore.value) return
    
    if (reset) {
      marketPage.value = 0
      marketModels.value = []
      marketHasMore.value = true
    }
    
    marketLoading.value = true
    marketError.value = null
    
    try {
      logger.info(`🏪 加载模型市场 (页码: ${marketPage.value}, 搜索: ${marketSearchQuery.value})`)
      
      const selectedFormats = Object.entries(formatFilter.value)
        .filter(([, enabled]) => enabled)
        .map(([format]) => format)

      const params = new URLSearchParams({
        page: String(marketPage.value),
        search: marketSearchQuery.value,
        source: currentSource.value,
        use_mirror: String(useMirror.value)
      })

      if (selectedFormats.length > 0) {
        params.set('formats', selectedFormats.join(','))
      }
      
      const res = await fetch(`${API_BASE()}/huggingface/models?${params}`)
      const data = await res.json()
      
      if (data.status === 'success') {
        const newModels = data.models as HuggingFaceModel[]
        
        if (reset) {
          marketModels.value = newModels
        } else {
          marketModels.value = [...marketModels.value, ...newModels]
        }
        
        marketHasMore.value = newModels.length >= 20 // 假设每页 20 条
        marketPage.value++
        
        logger.info(`✅ 加载了 ${newModels.length} 个市场模型`)
      } else {
        marketError.value = data.message || t.value.models.loadFailed
      }
    } catch (error) {
      logger.error('❌ 加载模型市场失败:', error)
      marketError.value = t.value.models.networkError
    } finally {
      marketLoading.value = false
    }
  }
  
  async function searchMarketModels(query: string) {
    marketSearchQuery.value = query
    await loadMarketModels(true)
  }
  
  async function loadMoreMarketModels() {
    await loadMarketModels(false)
  }
  
  // ============ 获取模型详情（包含文件列表） ============
  
  async function getModelFiles(modelId: string): Promise<HuggingFaceFileSibling[]> {
    try {
      logger.info(`📂 获取模型文件列表: ${modelId}`)
      
      const res = await fetch(`${API_BASE()}/huggingface/models/${encodeURIComponent(modelId)}/files`)
      const data = await res.json()
      
      if (data.status === 'success') {
        return data.files || []
      }
      return []
    } catch (error) {
      logger.error('❌ 获取模型文件失败:', error)
      return []
    }
  }
  
  async function getModelInfo(modelId: string): Promise<HuggingFaceModel | null> {
    try {
      logger.info(`ℹ️ 获取模型详情: ${modelId}`)
      
      const res = await fetch(`${API_BASE()}/huggingface/models/${encodeURIComponent(modelId)}/info`)
      const data = await res.json()
      
      if (data.status === 'success') {
        return data.model
      }
      return null
    } catch (error) {
      logger.error('❌ 获取模型详情失败:', error)
      return null
    }
  }
  
  // ============ 下载管理 ============
  
  /**
   * 加载可恢复的下载任务
   */
  async function loadPendingDownloads() {
    try {
      logger.info('📋 加载可恢复的下载任务...')
      
      const res = await fetch(`${API_BASE()}/huggingface/download/pending`)
      const data = await res.json()
      
      if (data.status === 'success') {
        pendingDownloads.value = data.tasks || []
        
        // 将 pending downloads 转换为暂停状态的任务（方便 UI 显示）
        for (const pending of pendingDownloads.value) {
          const taskId = `${pending.model_id}/${pending.filename}`
          if (!downloadTasks.value.has(taskId)) {
            const task: DownloadTask = {
              modelId: pending.model_id,
              filename: pending.filename,
              status: 'paused',
              progress: pending.progress,
              downloadedBytes: pending.downloaded_bytes,
              totalBytes: pending.total_bytes,
              speed: '',
              eta: '',
              startedAt: pending.started_at,
              updatedAt: pending.updated_at,
              error: pending.error_message
            }
            downloadTasks.value.set(taskId, task)
          }
        }
        
        if (pendingDownloads.value.length > 0) {
          logger.info(`✅ 发现 ${pendingDownloads.value.length} 个可恢复的下载任务`)
        }
      }
    } catch (error) {
      logger.error('❌ 加载可恢复任务失败:', error)
    }
  }
  
  /**
   * 下载模型文件
   * 
   * 支持并行下载多个模型，每个下载任务完全独立运行。
   * 使用 AbortController 支持取消功能。
   * 
   * @param modelId HuggingFace 模型 ID
   * @param filename 要下载的文件名
   * @param resume 是否为恢复下载（断点续传）
   * @param parameters 模型参数量 (e.g. "7B")
   * @param capabilities 模型能力列表 (e.g. ["text-generation"])
   */
  function downloadModel(
    modelId: string, 
    filename: string, 
    resume: boolean = false,
    parameters?: string,
    capabilities?: string[]
  ) {
    const taskId = `${modelId}/${filename}`
    
    // 检查是否已在下载
    if (downloadTasks.value.has(taskId)) {
      const existing = downloadTasks.value.get(taskId)!
      if (['pending', 'downloading'].includes(existing.status)) {
        logger.warn(`⚠️ 模型已在下载队列: ${taskId}`)
        return
      }
    }
    
    // 从 pendingDownloads 移除（如果是恢复下载）
    if (resume) {
      pendingDownloads.value = pendingDownloads.value.filter(
        p => !(p.model_id === modelId && p.filename === filename)
      )
    }
    
    // 创建 AbortController 用于取消
    const abortController = new AbortController()
    
    // 获取已有进度（如果是恢复下载）
    const existingTask = downloadTasks.value.get(taskId)
    
    // 创建下载任务
    const task: DownloadTask = {
      modelId,
      filename,
      status: 'pending',
      progress: resume && existingTask ? existingTask.progress : 0,
      downloadedBytes: resume && existingTask ? existingTask.downloadedBytes : 0,
      totalBytes: resume && existingTask ? existingTask.totalBytes : 0,
      speed: '',
      eta: '',
      startedAt: resume && existingTask ? existingTask.startedAt : new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      abortController,
      isResuming: resume
    }
    
    downloadTasks.value.set(taskId, task)
    logger.info(`⬇️ ${resume ? '恢复' : '创建'}下载任务: ${taskId}`)
    
    // 启动下载（不阻塞，在后台运行）
    startDownload(taskId, modelId, filename, abortController, resume, parameters, capabilities)
  }

  function downloadRepository(
    modelId: string,
    parameters?: string,
    capabilities?: string[]
  ) {
    downloadModel(modelId, REPO_DOWNLOAD_FILENAME, false, parameters, capabilities)
  }
  
  /**
   * 执行下载的内部函数（异步，不阻塞调用方）
   * 
   * 使用后台任务 + 轮询模式，而非 SSE 流
   */
  async function startDownload(
    taskId: string,
    modelId: string,
    filename: string,
    abortController: AbortController,
    resume: boolean = false,
    parameters?: string,
    capabilities?: string[]
  ) {
    const task = downloadTasks.value.get(taskId)
    if (!task) return
    
    try {
      logger.info(`⬇️ ${resume ? '恢复' : '开始'}下载: ${taskId}`)
      
      // 发送下载请求（后端会启动后台任务）
      const response = await fetch(`${API_BASE()}/huggingface/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          model_id: modelId, 
          filename,
          use_mirror: useMirror.value,
          resume: resume,
          parameters,
          capabilities
        }),
        signal: abortController.signal
      })
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`)
      }
      
      const data = await response.json()
      
      if (data.status === 'started') {
        // 更新状态为下载中
        updateTaskStatus(taskId, { status: 'downloading' })
        
        // 启动轮询进度
        startProgressPolling(taskId, modelId, filename)
        
        logger.info(`✅ 下载任务已启动: ${taskId}`)
      } else {
        throw new Error(data.message || t.value.models.startDownloadFailed)
      }
      
    } catch (error: unknown) {
      // 检查是否是取消导致的错误
      if (error instanceof Error && error.name === 'AbortError') {
        logger.info(`⛔ 下载已取消: ${taskId}`)
        updateTaskStatus(taskId, { status: 'cancelled' })
      } else {
        logger.error(`❌ 下载异常 [${taskId}]:`, error)
        updateTaskStatus(taskId, { 
          status: 'failed', 
          error: error instanceof Error ? error.message : String(error) 
        })
      }
    }
  }
  
  /**
   * 启动进度轮询
   */
  function startProgressPolling(taskId: string, modelId: string, filename: string) {
    // 如果已有轮询，先停止
    stopProgressPolling(taskId)
    
    const pollProgress = async () => {
      try {
        const encodedModelId = encodeURIComponent(modelId)
        const encodedFilename = encodeURIComponent(filename)
        const res = await fetch(
          `${API_BASE()}/huggingface/download/progress/${encodedModelId}?filename=${encodedFilename}`
        )
        
        if (!res.ok) {
          logger.warn(`轮询进度失败: ${res.status}`)
          return
        }
        
        const data = await res.json()
        
        // 处理进度数据
        processDownloadProgress(taskId, data)
        
        // 检查是否完成（需要停止轮询）
        if (['completed', 'failed', 'cancelled', 'paused', 'idle'].includes(data.status)) {
          stopProgressPolling(taskId)
          
          // 如果完成，刷新已安装列表
          if (data.status === 'completed') {
            setTimeout(() => loadInstalledModels(), 500)
          } else if (data.status === 'paused') {
            logger.info(`⏸️ LLM 下载已暂停: ${taskId}`)
          }
        }
      } catch (error) {
        logger.error(`轮询进度异常 [${taskId}]:`, error)
      }
    }
    
    // 立即执行一次
    pollProgress()
    
    // 每 1.5 秒轮询一次
    const intervalId = setInterval(pollProgress, 1500)
    pollingIntervals.value.set(taskId, intervalId)
    
    logger.debug(`📊 启动进度轮询: ${taskId}`)
  }
  
  /**
   * 停止进度轮询
   */
  function stopProgressPolling(taskId: string) {
    const intervalId = pollingIntervals.value.get(taskId)
    if (intervalId) {
      clearInterval(intervalId)
      pollingIntervals.value.delete(taskId)
      logger.debug(`📊 停止进度轮询: ${taskId}`)
    }
  }
  
  /**
   * 处理下载进度更新（兼容新的轮询模式响应格式）
   */
  function processDownloadProgress(taskId: string, data: Record<string, unknown>) {
    const currentTask = downloadTasks.value.get(taskId)
    if (!currentTask) return
    
    const updates: Partial<DownloadTask> = {
      updatedAt: new Date().toISOString()
    }
    
    // 新轮询模式的响应格式
    // 单文件模式: { downloaded_bytes, total_bytes, progress, speed, status, ... }
    // Repo模式: { downloaded_bytes, total_bytes, completed_files, total_files, progress, speed, status, ... }
    
    // 更新字节进度
    if (typeof data.downloaded_bytes === 'number' && typeof data.total_bytes === 'number' && data.total_bytes > 0) {
      updates.progress = (data.downloaded_bytes as number) / (data.total_bytes as number) * 100
      updates.downloadedBytes = data.downloaded_bytes as number
      updates.totalBytes = data.total_bytes as number
    }
    // 旧格式兼容（SSE 模式）
    else if (typeof data.total === 'number' && typeof data.completed === 'number' && data.total > 0) {
      updates.progress = (data.completed as number) / (data.total as number) * 100
      updates.downloadedBytes = data.completed as number
      updates.totalBytes = data.total as number
    }
    // 使用 progress 字段
    else if (typeof data.progress === 'number') {
      updates.progress = data.progress as number
    }
    
    // 更新文件进度（用于 Repo 下载）
    if (typeof data.completed_files === 'number') {
      updates.completedFiles = data.completed_files as number
    }
    if (typeof data.total_files === 'number') {
      updates.totalFiles = data.total_files as number
    }
    if (typeof data.current_file === 'string') {
      updates.currentFile = data.current_file as string
    }
    
    // 更新速度
    if (typeof data.speed === 'string' && data.speed) {
      updates.speed = data.speed as string
    } else if (typeof data.speed === 'number') {
      updates.speed = formatSpeed(data.speed as number)
    }
    
    // 处理状态变化 - 新格式
    const status = data.status as string
    if (status === 'completed' || status === 'success') {
      updates.status = 'completed'
      updates.progress = 100
      logger.info(`✅ 下载完成: ${taskId}`)
    } else if (status === 'downloading') {
      updates.status = 'downloading'
    } else if (status === 'paused') {
      updates.status = 'paused'
      logger.info(`⏸️ 下载已暂停: ${taskId}`)
    } else if (status === 'error' || status === 'failed') {
      updates.status = 'failed'
      updates.error = String(data.error_message || data.message || t.value.common.downloadFailed)
      logger.error(`❌ 下载失败 [${taskId}]: ${updates.error}`)
    } else if (status === 'cancelled') {
      updates.status = 'cancelled'
      logger.info(`⛔ 下载已取消: ${taskId}`)
    } else if (status === 'idle') {
      // 任务不存在或已完成
      // 检查文件是否已存在
      logger.debug(`📊 任务状态 idle: ${taskId}`)
    }
    
    updateTaskStatus(taskId, updates)
  }
  
  /**
   * 更新任务状态（合并更新）
   */
  function updateTaskStatus(taskId: string, updates: Partial<DownloadTask>) {
    const task = downloadTasks.value.get(taskId)
    if (task) {
      const updatedTask = { ...task, ...updates }
      downloadTasks.value.set(taskId, updatedTask)
    }
  }
  
  /**
   * 暂停下载（保留临时文件用于断点续传）
   */
  async function pauseDownload(modelId: string, filename: string) {
    const taskId = `${modelId}/${filename}`
    const task = downloadTasks.value.get(taskId)
    
    if (task && ['pending', 'downloading'].includes(task.status)) {
      try {
        logger.info(`⏸️ 请求暂停下载: ${taskId}`)
        
        // 立即更新前端状态（乐观更新）
        updateTaskStatus(taskId, { status: 'paused' })
        
        // 停止轮询
        stopProgressPolling(taskId)
        
        // 通知后端暂停下载
        const response = await fetch(`${API_BASE()}/huggingface/download/pause`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model_id: modelId, filename })
        })
        
        if (!response.ok) {
          const error = await response.json().catch(() => ({}))
          throw new Error(error.detail || t.value.models.pauseFailed)
        }
        
        logger.info(`⏸️ 已暂停下载: ${taskId}`)
      } catch (error) {
        logger.error(`暂停下载失败 [${taskId}]:`, error)
        // 恢复状态
        updateTaskStatus(taskId, { status: 'downloading' })
        // 恢复轮询
        startProgressPolling(taskId, modelId, filename)
      }
    }
  }
  
  /**
   * 恢复下载（断点续传）
   */
  function resumeDownload(modelId: string, filename: string) {
    logger.info(`▶️ 恢复下载: ${modelId}/${filename}`)
    downloadModel(modelId, filename, true)
  }
  
  /**
   * 取消下载（删除临时文件）
   */
  async function cancelDownload(modelId: string, filename: string) {
    const taskId = `${modelId}/${filename}`
    const task = downloadTasks.value.get(taskId)
    
    // 无论任务是否在下载中，都尝试取消（可能是暂停状态）
    try {
      // 1. 立即停止轮询
      stopProgressPolling(taskId)
      
      // 2. 如果有活跃的连接，先中断
      if (task?.abortController) {
        task.abortController.abort()
        logger.info(`⛔ 已中断前端连接: ${taskId}`)
      }
      
      // 3. 立即从任务列表移除（乐观更新）
      downloadTasks.value.delete(taskId)
      
      // 4. 从 pendingDownloads 中移除
      pendingDownloads.value = pendingDownloads.value.filter(
        p => !(p.model_id === modelId && p.filename === filename)
      )
      
      // 5. 通知后端取消下载（清理临时文件等）
      await fetch(`${API_BASE()}/huggingface/download/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId, filename })
      })
      
      logger.info(`⛔ 下载已取消: ${taskId}`)
    } catch (error) {
      logger.error(`取消下载失败 [${taskId}]:`, error)
      // 后端请求失败也不恢复状态，因为用户意图是取消
    }
  }
  
  function removeDownloadTask(modelId: string, filename: string) {
    const taskId = `${modelId}/${filename}`
    downloadTasks.value.delete(taskId)
  }
  
  // ============ 工具函数 ============
  
  function formatSpeed(bytesPerSecond: number): string {
    if (bytesPerSecond < 1024) return `${bytesPerSecond} B/s`
    if (bytesPerSecond < 1024 * 1024) return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`
    return `${(bytesPerSecond / (1024 * 1024)).toFixed(1)} MB/s`
  }
  
  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
  }
  
  /**
   * 检测模型格式
   */
  function detectModelFormat(filename: string): ModelFormat {
    const lower = filename.toLowerCase()
    if (lower.endsWith('.gguf')) return 'gguf'
    if (lower.includes('mlx') || lower.endsWith('.safetensors')) return 'mlx'
    return 'gguf' // 默认
  }
  
  /**
   * 设置镜像开关
   */
  function setUseMirror(value: boolean) {
    useMirror.value = value
    logger.info(`🌐 镜像设置: ${value ? '已开启' : '已关闭'}`)
  }
  
  /**
   * 设置格式过滤
   */
  function setFormatFilter(format: 'gguf' | 'mlx', enabled: boolean) {
    formatFilter.value[format] = enabled
    logger.info(`🔍 格式过滤: ${format} = ${enabled}`)
    loadMarketModels(true)
  }
  
  // ============ 返回 Store ============
  
  return {
    // 状态
    installedModels,
    installedLoading,
    marketModels,
    marketLoading,
    marketError,
    marketHasMore,
    marketSearchQuery,
    downloadTasks,
    downloadTasksList,
    activeDownloads,
    pausedDownloads,
    pendingDownloads,
    currentSource,
    useMirror,
    formatFilter,
    isMacOS,
    
    // 计算属性
    isModelInstalled,
    isModelDownloading,
    isModelPaused,
    
    // 已安装模型
    loadInstalledModels,
    deleteInstalledModel,
    
    // 模型市场
    loadMarketModels,
    searchMarketModels,
    loadMoreMarketModels,
    getModelFiles,
    getModelInfo,
    
    // 下载管理
    downloadModel,
    downloadRepository,
    pauseDownload,
    resumeDownload,
    cancelDownload,
    removeDownloadTask,
    loadPendingDownloads,
    
    // 设置
    setUseMirror,
    setFormatFilter,
    
    // 工具函数
    formatSize,
    detectModelFormat,
    REPO_DOWNLOAD_FILENAME
  }
})

/**
 * @deprecated 请改用 useModelHubStore，兼容导出将在后续清理阶段移除。
 */
export const useModelsStore = useModelHubStore
