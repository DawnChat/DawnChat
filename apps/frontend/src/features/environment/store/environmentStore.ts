/**
 * Environment Store - 统一环境状态管理
 * 
 * 功能：
 * 1. 聚合 modelsStore 和 toolsStore 的下载任务
 * 2. 提供统一的环境状态视图
 * 3. 管理环境管理页面的显示状态
 * 4. 检查 Plugin 环境依赖
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useModelHubStore } from '@/stores/modelHubStore'
import { useLlmSelectionStore } from '@/stores/llmSelectionStore'
import { useToolsStore } from '@/stores/toolsStore'
import { useImageGenStore } from '@/stores/imageGenStore'
import { useScoringStore } from '@/stores/scoringStore'
import { useI18n } from '@/composables/useI18n'
import type { 
  EnvironmentCategory, 
  UnifiedDownloadTask, 
  EnvironmentStatus,
  EnvironmentNavItem,
  EnvironmentRequirements,
  EnvironmentCheckResult,
  RequirementLevel
} from '@/types/environment'
import { logger } from '@/utils/logger'

export const useEnvironmentStore = defineStore('environment', () => {
  // ============ 状态 ============
  
  /** 是否显示环境管理页面 */
  const showEnvironmentManager = ref(false)
  
  /** 当前选中的环境类别 */
  const currentCategory = ref<EnvironmentCategory>('llm')
  
  /** 是否显示下载任务悬浮窗 */
  const showDownloadPopover = ref(false)
  
  // ============ 依赖的 Store ============
  
  const modelsStore = useModelHubStore()
  const modelStore = useLlmSelectionStore()
  const toolsStore = useToolsStore()
  const imageGenStore = useImageGenStore()
  const scoringStore = useScoringStore()
  const { t } = useI18n()
  
  // ============ 计算属性：聚合下载任务 ============
  
  /**
   * 所有下载任务的统一视图
   */
  const allDownloadTasks = computed<UnifiedDownloadTask[]>(() => {
    const tasks: UnifiedDownloadTask[] = []
    
    // 1. LLM 模型下载任务 (from modelsStore)
    for (const task of modelsStore.downloadTasksList) {
      const unifiedTask: UnifiedDownloadTask = {
        id: `llm-${task.modelId}/${task.filename}`,
        category: 'llm',
        name: task.filename,
        status: task.status,
        progress: task.progress,
        downloadedSize: task.downloadedBytes,
        totalSize: task.totalBytes,
        speed: task.speed,
        errorMessage: task.error,
        originalId: `${task.modelId}/${task.filename}`
      }
      
      // 添加文件进度信息（用于 Repo 下载）
      if (task.totalFiles && task.totalFiles > 0) {
        unifiedTask.extra = {
          downloadedFiles: task.completedFiles || 0,
          totalFiles: task.totalFiles,
          currentFile: task.currentFile
        }
      }
      
      tasks.push(unifiedTask)
    }
    
    // 2. ASR (Whisper) 下载任务 (from toolsStore)
    for (const [modelSize, progress] of toolsStore.whisperDownloadProgress.entries()) {
      tasks.push({
        id: `asr-${modelSize}`,
        category: 'asr',
        name: `Whisper ${modelSize}`,
        status: progress.status,
        progress: progress.progress,
        // 使用整体字节进度
        downloadedSize: progress.downloadedBytes || 0,
        totalSize: progress.totalBytes || 0,
        speed: progress.speed,
        message: progress.message,
        errorMessage: progress.errorMessage,
        originalId: modelSize,
        extra: {
          downloadedFiles: progress.downloadedFiles,
          totalFiles: progress.totalFiles,
          currentFile: progress.currentFile
        }
      })
    }
    
    // 3. FFmpeg 安装任务
    if (toolsStore.ffmpegInstalling) {
      tasks.push({
        id: 'ffmpeg-install',
        category: 'ffmpeg',
        name: 'FFmpeg',
        status: 'downloading',
        progress: 0, // FFmpeg 安装没有进度
        downloadedSize: 0,
        totalSize: 0,
        message: t.value.zmp.environment.installing
      })
    }
    
    // 4. Scoring (口语评分) 模型下载任务 (from scoringStore)
    for (const [modelId, progress] of scoringStore.downloadProgress.entries()) {
      // 跳过已完成和已取消的任务
      if (['completed', 'cancelled'].includes(progress.status)) {
        continue
      }
      const model = scoringStore.models.find(m => m.id === modelId)
      tasks.push({
        id: `scoring-${modelId}`,
        category: 'scoring',
        name: model?.name || `Wav2Vec2 ${modelId}`,
        status: progress.status,
        progress: progress.progress,
        downloadedSize: progress.downloadedBytes || 0,
        totalSize: progress.totalBytes || 0,
        speed: progress.speed,
        message: progress.message,
        errorMessage: progress.errorMessage,
        originalId: modelId,
        extra: {
          downloadedFiles: progress.downloadedFiles,
          totalFiles: progress.totalFiles,
          currentFile: progress.currentFile
        }
      })
    }
    
    return tasks
  })
  
  /**
   * 正在进行的下载任务
   */
  const activeDownloadTasks = computed(() => 
    allDownloadTasks.value.filter(t => 
      ['pending', 'downloading'].includes(t.status)
    )
  )
  
  /**
   * 正在进行的下载任务数量
   */
  const activeDownloadCount = computed(() => activeDownloadTasks.value.length)
  
  /**
   * 暂停的下载任务
   */
  const pausedDownloadTasks = computed(() =>
    allDownloadTasks.value.filter(t => t.status === 'paused')
  )
  
  // ============ 计算属性：环境状态 ============
  
  /**
   * 所有环境的状态
   */
  const environmentStatus = computed<EnvironmentStatus>(() => {
    const llmActiveDownloads = allDownloadTasks.value.filter(
      t => t.category === 'llm' && ['pending', 'downloading'].includes(t.status)
    ).length
    
    const ttsActiveDownloads = allDownloadTasks.value.filter(
      t => t.category === 'tts' && ['pending', 'downloading'].includes(t.status)
    ).length
    
    const asrActiveDownloads = allDownloadTasks.value.filter(
      t => t.category === 'asr' && ['pending', 'downloading'].includes(t.status)
    ).length
    
    const imageGenActiveDownloads = allDownloadTasks.value.filter(
      t => t.category === 'image_gen' && ['pending', 'downloading'].includes(t.status)
    ).length
    
    const scoringActiveDownloads = allDownloadTasks.value.filter(
      t => t.category === 'scoring' && ['pending', 'downloading'].includes(t.status)
    ).length
    
    return {
      llm: {
        ready: modelsStore.installedModels.length > 0,
        activeDownloads: llmActiveDownloads
      },
      tts: {
        ready: toolsStore.vibevoiceStatus.installedModels.length > 0 || toolsStore.cosyvoiceStatus.installedModels.length > 0,
        activeDownloads: ttsActiveDownloads
      },
      asr: {
        ready: toolsStore.whisperStatus.installedModels.length > 0,
        activeDownloads: asrActiveDownloads
      },
      ffmpeg: {
        ready: toolsStore.ffmpegInstalled,
        activeDownloads: 0,
        installing: toolsStore.ffmpegInstalling
      },
      cloud: {
        configured: false // TODO: 从 cloud 配置获取
      },
      imageGen: {
        ready: imageGenStore.hasModelsInstalled,
        activeDownloads: imageGenActiveDownloads,
        running: imageGenStore.serviceStatus.running,
        canStart: imageGenStore.serviceStatus.canStart
      },
      scoring: {
        ready: scoringStore.hasInstalledModels,
        activeDownloads: scoringActiveDownloads
      }
    }
  })
  
  /**
   * 导航项列表（包含状态）
   */
  const navItems = computed<EnvironmentNavItem[]>(() => {
    const status = environmentStatus.value
    
    const getItemStatus = (
      ready: boolean, 
      activeDownloads: number
    ): 'ready' | 'warning' | 'downloading' => {
      if (activeDownloads > 0) return 'downloading'
      if (ready) return 'ready'
      return 'warning'
    }
    
    return [
      {
        id: 'llm' as EnvironmentCategory,
        icon: 'Bot',
        label: t.value.models.llm.title,
        status: getItemStatus(status.llm.ready, status.llm.activeDownloads),
        badge: status.llm.activeDownloads > 0 ? status.llm.activeDownloads : undefined
      },
      {
        id: 'ffmpeg' as EnvironmentCategory,
        icon: 'Film',
        label: t.value.models.ffmpeg.title,
        status: status.ffmpeg.installing ? 'downloading' : 
                (status.ffmpeg.ready ? 'ready' : 'warning'),
        badge: status.ffmpeg.installing ? 1 : undefined
      },
      {
        id: 'cloud' as EnvironmentCategory,
        icon: 'Cloud',
        label: t.value.models.cloud.title,
        status: status.cloud.configured ? 'ready' : 'warning'
      },
      {
        id: 'scoring' as EnvironmentCategory,
        icon: 'AudioWaveform',
        label: t.value.models.scoring?.title || '口语评分',
        status: getItemStatus(status.scoring.ready, status.scoring.activeDownloads),
        badge: status.scoring.activeDownloads > 0 ? status.scoring.activeDownloads : undefined
      }
    ]
  })
  
  // ============ 方法 ============
  
  /**
   * 打开环境管理页面
   */
  function openEnvironmentManager(category?: EnvironmentCategory) {
    if (category) {
      currentCategory.value = category
    }
    showEnvironmentManager.value = true
    logger.info('📦 打开环境管理页面', { category: currentCategory.value })
  }
  
  /**
   * 关闭环境管理页面
   */
  function closeEnvironmentManager() {
    showEnvironmentManager.value = false
    logger.info('📦 关闭环境管理页面')
  }
  
  /**
   * 切换环境类别
   */
  function setCategory(category: EnvironmentCategory) {
    currentCategory.value = category
  }
  
  /**
   * 切换下载任务悬浮窗
   */
  function toggleDownloadPopover() {
    showDownloadPopover.value = !showDownloadPopover.value
  }
  
  /**
   * 关闭下载任务悬浮窗
   */
  function closeDownloadPopover() {
    showDownloadPopover.value = false
  }
  
  /**
   * 暂停下载任务
   */
  async function pauseTask(task: UnifiedDownloadTask) {
    logger.info('⏸️ 暂停下载任务', { id: task.id, category: task.category, originalId: task.originalId })
    
    switch (task.category) {
      case 'llm': {
        // originalId 格式: "modelId/filename"，modelId 本身可能包含 /，如 "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
        const parts = task.originalId?.split('/') || []
        if (parts.length >= 2) {
          const filename = parts.pop()!
          const modelId = parts.join('/')
          logger.debug('⏸️ LLM 暂停解析', { modelId, filename })
          await modelsStore.pauseDownload(modelId, filename)
        }
        break
      }
      case 'tts':
        logger.info('TTS 下载任务已迁移到插件 UI，宿主不再处理 pause')
        break
      case 'asr':
        if (task.originalId) {
          await toolsStore.pauseWhisperDownload(task.originalId)
        }
        break
      case 'image_gen':
        logger.info('ComfyUI 模型下载任务已迁移到插件 UI，宿主不再处理 pause')
        break
      case 'scoring':
        if (task.originalId) {
          await scoringStore.pauseDownload(task.originalId)
        }
        break
    }
  }
  
  /**
   * 继续下载任务
   */
  async function resumeTask(task: UnifiedDownloadTask) {
    logger.info('▶️ 继续下载任务', { id: task.id, category: task.category, originalId: task.originalId })
    
    switch (task.category) {
      case 'llm': {
        // originalId 格式: "modelId/filename"，modelId 本身可能包含 /，如 "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
        const parts = task.originalId?.split('/') || []
        if (parts.length >= 2) {
          const filename = parts.pop()!
          const modelId = parts.join('/')
          logger.debug('▶️ LLM 恢复解析', { modelId, filename })
          modelsStore.resumeDownload(modelId, filename)
        }
        break
      }
      case 'tts':
        logger.info('TTS 下载任务已迁移到插件 UI，宿主不再处理 resume')
        break
      case 'asr':
        if (task.originalId) {
          await toolsStore.downloadWhisperModel(task.originalId, true)
        }
        break
      case 'image_gen':
        logger.info('ComfyUI 模型下载任务已迁移到插件 UI，宿主不再处理 resume')
        break
      case 'scoring':
        if (task.originalId) {
          await scoringStore.resumeDownload(task.originalId)
        }
        break
    }
  }
  
  /**
   * 取消下载任务
   */
  async function cancelTask(task: UnifiedDownloadTask) {
    logger.info('❌ 取消下载任务', { id: task.id, category: task.category })
    
    switch (task.category) {
      case 'llm': {
        // originalId 格式: "modelId/filename"，需要完整解析
        const parts = task.originalId?.split('/') || []
        if (parts.length >= 2) {
          const filename = parts.pop()!
          const modelId = parts.join('/')
          await modelsStore.cancelDownload(modelId, filename)
        }
        break
      }
      case 'tts':
        logger.info('TTS 下载任务已迁移到插件 UI，宿主不再处理 cancel')
        break
      case 'asr':
        if (task.originalId) {
          await toolsStore.cancelWhisperDownload(task.originalId)
        }
        break
      case 'image_gen':
        logger.info('ComfyUI 模型下载任务已迁移到插件 UI，宿主不再处理 cancel')
        break
      case 'scoring':
        if (task.originalId) {
          await scoringStore.cancelDownload(task.originalId)
        }
        break
    }
  }
  
  /**
   * 重试失败的下载任务
   */
  async function retryTask(task: UnifiedDownloadTask) {
    logger.info('🔄 重试下载任务', { id: task.id, category: task.category })
    
    switch (task.category) {
      case 'llm': {
        // 先取消（清理状态），然后重新下载
        const parts = task.originalId?.split('/') || []
        if (parts.length >= 2) {
          const filename = parts.pop()!
          const modelId = parts.join('/')
          await modelsStore.cancelDownload(modelId, filename)
          // 稍微延迟后重新下载
          setTimeout(() => {
            modelsStore.downloadModel(modelId, filename, true) // resume=true
          }, 300)
        }
        break
      }
      case 'tts':
        logger.info('TTS 下载任务已迁移到插件 UI，宿主不再处理 retry')
        break
      case 'asr':
        if (task.originalId) {
          await toolsStore.cancelWhisperDownload(task.originalId)
          setTimeout(() => {
            toolsStore.downloadWhisperModel(task.originalId!, true) // resume=true
          }, 300)
        }
        break
      case 'image_gen':
        logger.info('ComfyUI 模型下载任务已迁移到插件 UI，宿主不再处理 retry')
        break
      case 'scoring':
        if (task.originalId) {
          // 重试 = 恢复下载
          await scoringStore.resumeDownload(task.originalId)
        }
        break
    }
  }

  /**
   * 检查 Plugin 环境依赖是否满足
   */
  function checkPluginRequirements(requirements: EnvironmentRequirements): EnvironmentCheckResult {
    const status = environmentStatus.value
    const missing: EnvironmentCategory[] = []
    const details: EnvironmentCheckResult['details'] = []
    
    // 辅助函数：检查单个非 AI 依赖
    const checkSimpleRequirement = (
      category: EnvironmentCategory,
      requirement: RequirementLevel | undefined,
      isReady: boolean
    ) => {
      // 不需要或可选的情况
      if (!requirement || requirement === 'optional') {
        return
      }
      if (typeof requirement === 'boolean' && requirement === false) {
        return
      }
      
      const satisfied = isReady
      const message = satisfied ? '' : t.value.zmp.environment.installRequired.replace('{category}', category)
      
      if (!satisfied) {
        missing.push(category)
      }
      
      details.push({
        category,
        requirement,
        currentStatus: satisfied ? 'ready' : 'not_ready',
        message
      })
    }
    
    // 检查 AI 依赖（三种类型）
    const hasLocalLLM = status.llm.ready
    const hasCloudAI = status.cloud.configured
    
    // ai: 通用 AI（本地 OR 云端满足其一）
    // 注意：requirements.ai && 已经排除了 false 和 undefined
    if (requirements.ai && requirements.ai !== 'optional') {
      const satisfied = hasLocalLLM || hasCloudAI
      if (!satisfied) {
        missing.push('llm') // 跳转到 llm 页面
      }
      details.push({
        category: 'llm',
        requirement: requirements.ai,
        currentStatus: satisfied ? 'ready' : 'not_ready',
        message: satisfied ? '' : t.value.zmp.environment.requirements.ai
      })
    }
    
    // local_ai: 仅本地
    if (requirements.local_ai && requirements.local_ai !== 'optional') {
      const satisfied = hasLocalLLM
      if (!satisfied) {
        missing.push('llm')
      }
      details.push({
        category: 'llm',
        requirement: requirements.local_ai,
        currentStatus: satisfied ? 'ready' : 'not_ready',
        message: satisfied ? '' : t.value.zmp.environment.requirements.localAi
      })
    }
    
    // cloud_ai: 仅云端
    if (requirements.cloud_ai && requirements.cloud_ai !== 'optional') {
      const satisfied = hasCloudAI
      if (!satisfied) {
        missing.push('cloud')
      }
      details.push({
        category: 'cloud',
        requirement: requirements.cloud_ai,
        currentStatus: satisfied ? 'ready' : 'not_ready',
        message: satisfied ? '' : t.value.zmp.environment.requirements.cloudAi
      })
    }
    
    // 检查其他依赖
    checkSimpleRequirement('tts', requirements.tts, status.tts.ready)
    checkSimpleRequirement('asr', requirements.asr, status.asr.ready)
    checkSimpleRequirement('ffmpeg', requirements.ffmpeg, status.ffmpeg.ready)
    checkSimpleRequirement('scoring', requirements.scoring, status.scoring.ready)
    
    const result: EnvironmentCheckResult = {
      satisfied: missing.length === 0,
      missing,
      details
    }
    
    logger.info('🔍 检查 Plugin 环境依赖', { requirements, result })
    
    return result
  }
  
  /**
   * 初始化（确保依赖的 store 已加载数据）
   */
  async function initialize() {
    logger.info('🔧 初始化 Environment Store...')
    
    // 加载模型列表
    await modelsStore.loadInstalledModels()
    await modelsStore.loadPendingDownloads()
    
    // 加载工具状态
    await toolsStore.initialize()
    
    logger.info('✅ Environment Store 初始化完成')
  }
  
  /**
   * 刷新所有环境状态
   * 在打开环境管理页面时调用，确保显示最新状态
   */
  async function refreshAllStatus() {
    logger.info('🔄 刷新所有环境状态...')
    
    await Promise.all([
      modelsStore.loadInstalledModels(),
      modelsStore.loadPendingDownloads(),
      toolsStore.loadWhisperStatus(),
      toolsStore.checkFFmpegStatus(),
      toolsStore.loadPendingWhisperDownloads(),
      // 刷新云端模型和 ImageGen 状态
      modelStore.loadModels(true),
      imageGenStore.loadWorkflows(),
      imageGenStore.loadStatus(),
      // 刷新口语评分状态
      scoringStore.loadStatus(),
      scoringStore.loadModels(),
      scoringStore.loadPendingDownloads()
    ])
    
    logger.info('✅ 环境状态刷新完成')
  }
  
  // ============ 返回 Store ============
  
  return {
    // 状态
    showEnvironmentManager,
    currentCategory,
    showDownloadPopover,
    
    // 计算属性
    allDownloadTasks,
    activeDownloadTasks,
    activeDownloadCount,
    pausedDownloadTasks,
    environmentStatus,
    navItems,
    
    // 方法
    openEnvironmentManager,
    closeEnvironmentManager,
    setCategory,
    toggleDownloadPopover,
    closeDownloadPopover,
    pauseTask,
    resumeTask,
    cancelTask,
    retryTask,
    checkPluginRequirements,
    initialize,
    refreshAllStatus
  }
})
