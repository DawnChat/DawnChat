/**
 * Tools Store - 集中管理工具市场相关状态
 * 
 * 功能：
 * 1. FFmpeg 状态管理
 * 2. VibeVoice TTS 模型下载管理
 * 3. Whisper ASR 模型下载管理
 * 4. Speaker Diarization 状态管理
 * 5. 已安装工具列表
 * 6. 工具市场列表
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useI18n } from '@/composables/useI18n'
import { logger } from '@/utils/logger'
import { buildBackendUrl } from '@/utils/backendUrl'

// ============ 类型定义 ============

/**
 * 下载状态
 */
export type DownloadStatus = 'idle' | 'pending' | 'downloading' | 'paused' | 'completed' | 'failed' | 'cancelled'

/**
 * 模型选项（用于 VibeVoice / Whisper）
 */
export interface ModelOption {
  id: string
  name: string
  description: string
  hfRepoId: string
}

/**
 * 市场工具信息
 */
export interface MarketTool {
  id: string
  name: string
  description: string
  protocol: string
  version: string
  author: string
  icon: string
  capabilities: string[]
  downloads: number
  rating: number
  isInstalled: boolean
  installedModels?: string[]
  modelOptions?: ModelOption[]
  bundled?: boolean  // 是否为内置模型（不需要下载）
}

/**
 * 模型下载进度
 */
export interface ModelDownloadProgress {
  status: DownloadStatus
  progress: number
  // 整体字节进度
  downloadedBytes: number
  totalBytes: number
  // 文件级进度（用于 repo 下载）
  downloadedFiles: number
  totalFiles: number
  currentFile: string
  message: string
  errorMessage?: string
  speed?: string
}

/**
 * 已安装的工具
 */
export interface InstalledTool {
  id: string
  name: string
  description: string
  icon: string
  protocol: string
  version: string
  author: string
  capabilities: string[]
}

// ============ Store 定义 ============

export const useToolsStore = defineStore('tools', () => {
  const { t } = useI18n()

  // ============ 状态 ============
  
  // API 基础 URL
  const API_BASE = () => buildBackendUrl('/api')
  
  // 已安装工具
  const installedTools = ref<InstalledTool[]>([])
  const installedLoading = ref(false)
  
  // 工具市场
  const marketTools = ref<MarketTool[]>([])
  const marketLoading = ref(false)
  
  // FFmpeg 状态
  const ffmpegInstalled = ref(false)
  const ffmpegInstalling = ref(false)
  
  // VibeVoice 状态
  const vibevoiceStatus = ref<{
    available: boolean
    installedModels: string[]
    currentLoaded: string | null
  }>({
    available: false,
    installedModels: [],
    currentLoaded: null
  })
  const vibevoiceDownloadProgress = ref<Map<string, ModelDownloadProgress>>(new Map())

  // CosyVoice 状态
  const cosyvoiceStatus = ref<{
    available: boolean
    installedModels: string[]
    currentLoaded: string | null
  }>({
    available: false,
    installedModels: [],
    currentLoaded: null
  })
  const cosyvoiceDownloadProgress = ref<Map<string, ModelDownloadProgress>>(new Map())
  
  // Whisper 状态
  const whisperStatus = ref<{
    available: boolean
    installedModels: string[]
    loadedModel: string | null
    defaultModel: string | null
  }>({
    available: false,
    installedModels: [],
    loadedModel: null,
    defaultModel: null
  })
  const whisperDownloadProgress = ref<Map<string, ModelDownloadProgress>>(new Map())
  
  // Speaker Diarization 状态
  const diarizationStatus = ref<{
    available: boolean
    loaded: boolean
    modelPath: string | null
    device: string | null
  }>({
    available: false,
    loaded: false,
    modelPath: null,
    device: null
  })
  
  // 镜像设置
  const useMirror = ref(true)
  
  // 轮询定时器
  const pollingTimers = ref<Map<string, number>>(new Map())
  
  // ============ 计算属性 ============
  
  const activeVibevoiceDownloads = computed(() => 
    Array.from(vibevoiceDownloadProgress.value.entries())
      .filter(([, p]) => ['pending', 'downloading'].includes(p.status))
      .map(([id, p]) => ({ id, ...p }))
  )
  
  const activeWhisperDownloads = computed(() =>
    Array.from(whisperDownloadProgress.value.entries())
      .filter(([, p]) => ['pending', 'downloading'].includes(p.status))
      .map(([id, p]) => ({ id, ...p }))
  )

  const activeCosyvoiceDownloads = computed(() =>
    Array.from(cosyvoiceDownloadProgress.value.entries())
      .filter(([, p]) => ['pending', 'downloading'].includes(p.status))
      .map(([id, p]) => ({ id, ...p }))
  )
  
  // 暂停的任务（用于冷启动后恢复）
  const pausedVibevoiceDownloads = computed(() =>
    Array.from(vibevoiceDownloadProgress.value.entries())
      .filter(([, p]) => p.status === 'paused')
      .map(([id, p]) => ({ id, ...p }))
  )
  
  const pausedWhisperDownloads = computed(() =>
    Array.from(whisperDownloadProgress.value.entries())
      .filter(([, p]) => p.status === 'paused')
      .map(([id, p]) => ({ id, ...p }))
  )

  const pausedCosyvoiceDownloads = computed(() =>
    Array.from(cosyvoiceDownloadProgress.value.entries())
      .filter(([, p]) => p.status === 'paused')
      .map(([id, p]) => ({ id, ...p }))
  )
  
  // ============ FFmpeg 管理 ============
  
  async function checkFFmpegStatus() {
    try {
      const res = await fetch(`${API_BASE()}/tools/ffmpeg/status`)
      const data = await res.json()
      ffmpegInstalled.value = data.available === true
      logger.info(`📦 FFmpeg 状态: ${ffmpegInstalled.value ? '已安装' : '未安装'}`)
    } catch (error) {
      logger.error('❌ 检查 FFmpeg 状态失败:', error)
      ffmpegInstalled.value = false
    }
  }
  
  async function installFFmpeg(): Promise<boolean> {
    if (ffmpegInstalling.value) return false
    
    ffmpegInstalling.value = true
    try {
      logger.info('📥 开始安装 FFmpeg...')
      const res = await fetch(`${API_BASE()}/tools/ffmpeg/install`, { method: 'POST' })
      const data = await res.json()
      
      if (data.status === 'success') {
        ffmpegInstalled.value = true
        logger.info('✅ FFmpeg 安装成功')
        return true
      } else {
        logger.error('❌ FFmpeg 安装失败:', data.message)
        return false
      }
    } catch (error) {
      logger.error('❌ FFmpeg 安装异常:', error)
      return false
    } finally {
      ffmpegInstalling.value = false
    }
  }
  
  // ============ VibeVoice 管理 ============
  
  async function loadVibevoiceStatus() {
    vibevoiceStatus.value = { available: false, installedModels: [], currentLoaded: null }
  }
  
  async function downloadVibevoiceModel(modelSize: string, resume = false) {
    logger.warn(`VibeVoice 模型管理已迁移到插件 UI: model=${modelSize}, resume=${resume}`)
    return false
  }
  
  async function pauseVibevoiceDownload(modelSize: string) {
    stopProgressPolling(`vibevoice-${modelSize}`)
  }
  
  async function cancelVibevoiceDownload(modelSize: string) {
    stopProgressPolling(`vibevoice-${modelSize}`)
    vibevoiceDownloadProgress.value.delete(modelSize)
  }

  // ============ CosyVoice 管理 ============

  async function loadCosyvoiceStatus() {
    cosyvoiceStatus.value = { available: false, installedModels: [], currentLoaded: null }
  }

  async function downloadCosyvoiceModel(modelId: string, resume = false) {
    logger.warn(`CosyVoice 模型管理已迁移到插件 UI: model=${modelId}, resume=${resume}`)
    return false
  }

  async function pauseCosyvoiceDownload(modelId: string) {
    stopProgressPolling(`cosyvoice-${modelId}`)
  }

  async function cancelCosyvoiceDownload(modelId: string) {
    stopProgressPolling(`cosyvoice-${modelId}`)
    cosyvoiceDownloadProgress.value.delete(modelId)
  }
  
  // ============ Whisper 管理 ============
  
  async function loadWhisperStatus() {
    try {
      const res = await fetch(`${API_BASE()}/tools/whisper/status`)
      const data = await res.json()
      
      whisperStatus.value = {
        available: data.available === true,
        installedModels: data.installed_models || [],
        loadedModel: data.loaded_model || null,
        defaultModel: data.default_model || null
      }
      
      logger.info(`🎤 Whisper 状态: ${whisperStatus.value.installedModels.length} 个模型已安装`)
    } catch (error) {
      logger.error('❌ 加载 Whisper 状态失败:', error)
    }
  }
  
  async function downloadWhisperModel(modelSize: string, resume = false) {
    try {
      logger.info(`📥 ${resume ? '恢复' : '开始'}下载 Whisper ${modelSize}...`)
      
      const res = await fetch(`${API_BASE()}/tools/whisper/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_size: modelSize,
          use_mirror: useMirror.value,
          resume
        })
      })
      
      const data = await res.json()
      
      if (data.installed) {
        logger.info(`✅ Whisper ${modelSize} 已安装`)
        await loadWhisperStatus()
        return true
      }
      
      if (data.status === 'started' || data.status === 'success') {
        // 开始轮询进度
        startWhisperProgressPolling(modelSize)
        return true
      }
      
      logger.error(`❌ 下载启动失败: ${data.message}`)
      return false
    } catch (error) {
      logger.error('❌ 下载 Whisper 异常:', error)
      return false
    }
  }
  
  function startWhisperProgressPolling(modelSize: string) {
    // 清除已有的轮询
    stopProgressPolling(`whisper-${modelSize}`)
    
    const pollProgress = async () => {
      try {
        const res = await fetch(`${API_BASE()}/tools/whisper/download/progress/${modelSize}`)
        const data = await res.json()
        
        const progress: ModelDownloadProgress = {
          status: data.status as DownloadStatus,
          progress: data.progress || 0,
          // 整体字节进度
          downloadedBytes: data.downloaded_bytes || 0,
          totalBytes: data.total_bytes || 0,
          // 文件级进度（用于 repo 下载）
          downloadedFiles: data.completed_files || 0,
          totalFiles: data.total_files || 0,
          currentFile: data.current_file || '',
          message: data.message || '',
          errorMessage: data.error_message,
          speed: data.speed || ''
        }
        
        whisperDownloadProgress.value.set(modelSize, progress)
        
        // 检查是否需要停止轮询（包括 paused 状态）
        if (['completed', 'failed', 'cancelled', 'paused'].includes(data.status)) {
          stopProgressPolling(`whisper-${modelSize}`)
          
          if (data.status === 'completed') {
            logger.info(`✅ Whisper ${modelSize} 下载完成`)
            await loadWhisperStatus()
          } else if (data.status === 'paused') {
            logger.info(`⏸️ Whisper ${modelSize} 下载已暂停`)
          }
        }
      } catch (error) {
        logger.error(`轮询 Whisper ${modelSize} 进度失败:`, error)
      }
    }
    
    // 立即执行一次
    pollProgress()
    
    // 每 1.5 秒轮询一次
    const timerId = window.setInterval(pollProgress, 1500)
    pollingTimers.value.set(`whisper-${modelSize}`, timerId)
  }
  
  async function pauseWhisperDownload(modelSize: string) {
    try {
      // 立即停止轮询
      stopProgressPolling(`whisper-${modelSize}`)
      
      // 立即更新状态（乐观更新）
      const current = whisperDownloadProgress.value.get(modelSize)
      if (current) {
        whisperDownloadProgress.value.set(modelSize, {
          ...current,
          status: 'paused',
          message: t.value.common.downloadPaused
        })
      }
      
      await fetch(`${API_BASE()}/tools/whisper/download/pause`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_size: modelSize })
      })
      logger.info(`⏸️ 已暂停 Whisper ${modelSize} 下载`)
    } catch (error) {
      logger.error('暂停下载失败:', error)
      // 恢复轮询
      startWhisperProgressPolling(modelSize)
    }
  }
  
  async function cancelWhisperDownload(modelSize: string) {
    try {
      // 立即停止轮询
      stopProgressPolling(`whisper-${modelSize}`)
      
      // 立即从进度列表移除（乐观更新）
      whisperDownloadProgress.value.delete(modelSize)
      
      await fetch(`${API_BASE()}/tools/whisper/download/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_size: modelSize })
      })
      
      logger.info(`⛔ 已取消 Whisper ${modelSize} 下载`)
    } catch (error) {
      logger.error('取消下载失败:', error)
    }
  }
  
  // ============ Speaker Diarization 管理 ============
  
  async function loadDiarizationStatus() {
    try {
      const res = await fetch(`${API_BASE()}/tools/call`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_name: 'plugin.com.dawnchat.diarization.status',
          arguments: {},
          timeout: 30
        })
      })
      const response = await res.json()
      const content = response?.result?.content
      const payload = content && typeof content === 'object' ? content : {}
      const data = payload?.data && typeof payload.data === 'object' ? payload.data : {}

      diarizationStatus.value = {
        available: data.available === true,
        loaded: data.loaded === true,
        modelPath: data.model_path || null,
        device: data.device || null
      }
      
      logger.info(`🎭 Diarization 状态: ${diarizationStatus.value.available ? '可用' : '不可用'}`)
    } catch (error) {
      logger.error('❌ 加载 Diarization 状态失败:', error)
    }
  }
  
  // ============ 通用工具 ============
  
  function stopProgressPolling(key: string) {
    const timerId = pollingTimers.value.get(key)
    if (timerId) {
      window.clearInterval(timerId)
      pollingTimers.value.delete(key)
    }
  }
  
  function stopAllPolling() {
    for (const [_, timerId] of pollingTimers.value.entries()) {
      window.clearInterval(timerId)
    }
    pollingTimers.value.clear()
  }
  
  // ============ 已安装工具 ============
  
  async function loadInstalledTools() {
    installedLoading.value = true
    try {
      const res = await fetch(`${API_BASE()}/tools/installed`)
      const data = await res.json()
      
      if (data.status === 'success') {
        installedTools.value = data.tools.map((t: any) => ({
          id: t.id,
          name: t.name,
          description: t.description,
          icon: t.icon || 'Package',
          protocol: t.protocol,
          version: t.version,
          author: t.author,
          capabilities: t.capabilities || []
        }))
        
        logger.info(`📦 已加载 ${installedTools.value.length} 个已安装工具`)
      }
    } catch (error) {
      logger.error('❌ 加载已安装工具失败:', error)
    } finally {
      installedLoading.value = false
    }
  }
  
  // ============ 工具市场 ============
  
  async function loadMarketTools() {
    marketLoading.value = true
    try {
      const res = await fetch(`${API_BASE()}/tools/market`)
      const data = await res.json()
      
      if (data.status === 'success') {
        marketTools.value = data.tools
        logger.info(`🏪 已加载 ${marketTools.value.length} 个市场工具`)
      }
    } catch (error) {
      logger.error('❌ 加载工具市场失败:', error)
    } finally {
      marketLoading.value = false
    }
  }
  
  // ============ 加载可恢复的下载任务（冷启动后） ============
  
  /**
   * 加载可恢复的 VibeVoice 下载任务
   */
  async function loadPendingVibevoiceDownloads() {
    vibevoiceDownloadProgress.value.clear()
  }
  
  /**
   * 加载可恢复的 Whisper 下载任务
   */
  async function loadPendingWhisperDownloads() {
    try {
      logger.info('📋 加载可恢复的 Whisper 下载任务...')
      const res = await fetch(`${API_BASE()}/tools/whisper/download/pending`)
      const data = await res.json()
      
      if (data.status === 'success' && data.tasks) {
        for (const task of data.tasks) {
          const modelSize = task.model_id || task.model_size
          const progress: ModelDownloadProgress = {
            status: task.status || 'paused',
            progress: task.progress || 0,
            downloadedBytes: task.downloaded_bytes || 0,
            totalBytes: task.total_bytes || 0,
            downloadedFiles: task.completed_files || 0,
            totalFiles: task.total_files || 0,
            currentFile: task.current_file || '',
            message: task.error_message || t.value.common.paused,
            speed: ''
          }
          whisperDownloadProgress.value.set(modelSize, progress)

          if (['pending', 'downloading'].includes(progress.status)) {
            startWhisperProgressPolling(modelSize)
          }
        }
        
        if (data.tasks.length > 0) {
          logger.info(`✅ 发现 ${data.tasks.length} 个可恢复的 Whisper 下载任务`)
        }
      }
    } catch (error) {
      logger.error('❌ 加载 Whisper 可恢复任务失败:', error)
    }
  }

  /**
   * 加载可恢复的 CosyVoice 下载任务
   */
  async function loadPendingCosyvoiceDownloads() {
    cosyvoiceDownloadProgress.value.clear()
  }
  
  // ============ 初始化 ============
  
  async function initialize() {
    logger.info('🔧 初始化 Tools Store...')
    
    await Promise.all([
      checkFFmpegStatus(),
      loadVibevoiceStatus(),
      loadCosyvoiceStatus(),
      loadWhisperStatus(),
      loadDiarizationStatus(),
      loadInstalledTools(),
      loadMarketTools(),
      // 加载可恢复的下载任务
      loadPendingVibevoiceDownloads(),
      loadPendingCosyvoiceDownloads(),
      loadPendingWhisperDownloads()
    ])
    
    logger.info('✅ Tools Store 初始化完成')
  }
  
  // ============ 设置 ============
  
  function setUseMirror(value: boolean) {
    useMirror.value = value
    logger.info(`🌐 镜像设置: ${value ? '已开启' : '已关闭'}`)
  }
  
  // ============ 返回 Store ============
  
  return {
    // 状态
    installedTools,
    installedLoading,
    marketTools,
    marketLoading,
    useMirror,
    
    // FFmpeg
    ffmpegInstalled,
    ffmpegInstalling,
    checkFFmpegStatus,
    installFFmpeg,
    
    // VibeVoice
    vibevoiceStatus,
    vibevoiceDownloadProgress,
    activeVibevoiceDownloads,
    pausedVibevoiceDownloads,
    loadVibevoiceStatus,
    downloadVibevoiceModel,
    pauseVibevoiceDownload,
    cancelVibevoiceDownload,
    loadPendingVibevoiceDownloads,

    // CosyVoice
    cosyvoiceStatus,
    cosyvoiceDownloadProgress,
    activeCosyvoiceDownloads,
    pausedCosyvoiceDownloads,
    loadCosyvoiceStatus,
    downloadCosyvoiceModel,
    pauseCosyvoiceDownload,
    cancelCosyvoiceDownload,
    loadPendingCosyvoiceDownloads,
    
    // Whisper
    whisperStatus,
    whisperDownloadProgress,
    activeWhisperDownloads,
    pausedWhisperDownloads,
    loadWhisperStatus,
    downloadWhisperModel,
    pauseWhisperDownload,
    cancelWhisperDownload,
    loadPendingWhisperDownloads,
    
    // Diarization
    diarizationStatus,
    loadDiarizationStatus,
    
    // 工具管理
    loadInstalledTools,
    loadMarketTools,
    
    // 通用
    initialize,
    setUseMirror,
    stopAllPolling
  }
})
