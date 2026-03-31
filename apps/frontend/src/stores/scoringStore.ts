/**
 * Scoring Store - 口语评分模型状态管理
 * 
 * 功能：
 * 1. Wav2Vec2 模型下载管理
 * 2. 模型安装状态查询
 * 3. 下载进度跟踪
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
 * 口语评分模型信息
 */
export interface ScoringModel {
  id: string
  name: string
  hfRepoId: string
  description: string
  sizeMb: number
  installed: boolean
  downloading: boolean
  progress: number
  path: string | null
}

/**
 * 模型下载进度
 */
export interface ModelDownloadProgress {
  status: DownloadStatus
  progress: number
  downloadedBytes: number
  totalBytes: number
  downloadedFiles: number
  totalFiles: number
  currentFile: string
  message: string
  errorMessage?: string
  speed?: string
}

// ============ Store 定义 ============

export const useScoringStore = defineStore('scoring', () => {
  const { t } = useI18n()

  // ============ 状态 ============
  
  // API 基础 URL
  const API_BASE = () => buildBackendUrl('/api/scoring')
  
  // 服务状态
  const status = ref<{
    available: boolean
    installedModels: string[]
    defaultModel: string | null
  }>({
    available: false,
    installedModels: [],
    defaultModel: null
  })
  
  // 模型列表
  const models = ref<ScoringModel[]>([])
  
  // 下载进度
  const downloadProgress = ref<Map<string, ModelDownloadProgress>>(new Map())
  
  // 是否使用镜像
  const useMirror = ref(true)
  
  // 轮询定时器
  const pollingTimers = ref<Map<string, number>>(new Map())
  
  // ============ 计算属性 ============
  
  const installedModels = computed(() => status.value.installedModels)
  
  const hasInstalledModels = computed(() => status.value.installedModels.length > 0)
  
  const activeDownloads = computed(() =>
    Array.from(downloadProgress.value.entries())
      .filter(([, p]) => ['pending', 'downloading'].includes(p.status))
      .map(([id, p]) => ({ id, ...p }))
  )
  
  const isDownloading = computed(() => activeDownloads.value.length > 0)
  
  // ============ 方法 ============
  
  /**
   * 加载服务状态
   */
  async function loadStatus() {
    try {
      const res = await fetch(`${API_BASE()}/status`)
      const data = await res.json()
      
      status.value = {
        available: data.available === true,
        installedModels: data.installed_models || [],
        defaultModel: data.default_model || null
      }
      
      logger.info(`🎯 口语评分状态: ${status.value.installedModels.length} 个模型已安装`)
    } catch (error) {
      logger.error('❌ 加载口语评分状态失败:', error)
    }
  }
  
  /**
   * 加载模型列表
   */
  async function loadModels() {
    try {
      const res = await fetch(`${API_BASE()}/models`)
      const data = await res.json()
      
      models.value = (data.models || []).map((m: any) => ({
        id: m.id,
        name: m.name,
        hfRepoId: m.hf_repo_id,
        description: m.description,
        sizeMb: m.size_mb,
        installed: m.installed,
        downloading: m.downloading,
        progress: m.progress || 0,
        path: m.path
      }))
      
      logger.info(`📦 加载口语评分模型列表: ${models.value.length} 个`)
    } catch (error) {
      logger.error('❌ 加载模型列表失败:', error)
    }
  }
  
  /**
   * 下载模型
   */
  async function downloadModel(modelId: string, resume = false) {
    try {
      logger.info(`📥 ${resume ? '恢复' : '开始'}下载口语评分模型 ${modelId}...`)
      
      const res = await fetch(`${API_BASE()}/models/${modelId}/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          use_mirror: useMirror.value
        })
      })
      
      const data = await res.json()
      
      if (data.status === 'already_installed') {
        logger.info(`✅ 模型 ${modelId} 已安装`)
        await loadStatus()
        await loadModels()
        return true
      }
      
      if (data.status === 'started' || data.status === 'already_downloading') {
        // 开始轮询进度
        startProgressPolling(modelId)
        return true
      }
      
      logger.error(`❌ 下载启动失败: ${data.message}`)
      return false
    } catch (error) {
      logger.error('❌ 下载模型异常:', error)
      return false
    }
  }
  
  /**
   * 开始轮询下载进度
   */
  function startProgressPolling(modelId: string) {
    // 清除已有的轮询
    stopProgressPolling(modelId)
    
    const pollProgress = async () => {
      try {
        const res = await fetch(`${API_BASE()}/models/${modelId}/progress`)
        const data = await res.json()
        
        const progress: ModelDownloadProgress = {
          status: data.status as DownloadStatus,
          progress: data.progress || 0,
          downloadedBytes: data.downloaded_bytes || 0,
          totalBytes: data.total_bytes || 0,
          downloadedFiles: data.completed_files || 0,
          totalFiles: data.total_files || 0,
          currentFile: data.current_file || '',
          message: data.message || '',
          errorMessage: data.error_message,
          speed: data.speed || ''
        }
        
        downloadProgress.value.set(modelId, progress)
        
        // 检查是否需要停止轮询
        if (['completed', 'failed', 'cancelled', 'paused'].includes(data.status)) {
          stopProgressPolling(modelId)
          
          if (data.status === 'completed') {
            logger.info(`✅ 模型 ${modelId} 下载完成`)
            await loadStatus()
            await loadModels()
          } else if (data.status === 'paused') {
            logger.info(`⏸️ 模型 ${modelId} 下载已暂停`)
          }
        }
      } catch (error) {
        logger.error(`轮询模型 ${modelId} 进度失败:`, error)
      }
    }
    
    // 立即执行一次
    pollProgress()
    
    // 每 1.5 秒轮询一次
    const timerId = window.setInterval(pollProgress, 1500)
    pollingTimers.value.set(modelId, timerId)
  }
  
  /**
   * 停止轮询
   */
  function stopProgressPolling(modelId: string) {
    const timerId = pollingTimers.value.get(modelId)
    if (timerId) {
      window.clearInterval(timerId)
      pollingTimers.value.delete(modelId)
    }
  }
  
  /**
   * 暂停下载
   */
  async function pauseDownload(modelId: string) {
    try {
      // 立即停止轮询
      stopProgressPolling(modelId)
      
      // 乐观更新
      const current = downloadProgress.value.get(modelId)
      if (current) {
        downloadProgress.value.set(modelId, {
          ...current,
          status: 'paused',
          message: t.value.common.downloadPaused || '已暂停'
        })
      }
      
      await fetch(`${API_BASE()}/models/${modelId}/download/pause`, {
        method: 'POST'
      })
      logger.info(`⏸️ 已暂停模型 ${modelId} 下载`)
    } catch (error) {
      logger.error('暂停下载失败:', error)
      // 恢复轮询
      startProgressPolling(modelId)
    }
  }
  
  /**
   * 取消下载
   */
  async function cancelDownload(modelId: string) {
    try {
      // 立即停止轮询
      stopProgressPolling(modelId)
      
      // 立即从进度列表移除
      downloadProgress.value.delete(modelId)
      
      await fetch(`${API_BASE()}/models/${modelId}/download/cancel`, {
        method: 'POST'
      })
      
      logger.info(`⛔ 已取消模型 ${modelId} 下载`)
    } catch (error) {
      logger.error('取消下载失败:', error)
    }
  }
  
  /**
   * 恢复下载
   */
  async function resumeDownload(modelId: string) {
    return await downloadModel(modelId, true)
  }
  
  /**
   * 删除模型
   */
  async function deleteModel(modelId: string) {
    try {
      const res = await fetch(`${API_BASE()}/models/${modelId}`, {
        method: 'DELETE'
      })
      
      const data = await res.json()
      
      if (data.status === 'deleted') {
        logger.info(`🗑️ 已删除模型 ${modelId}`)
        await loadStatus()
        await loadModels()
        return true
      }
      
      logger.error(`删除失败: ${data.message}`)
      return false
    } catch (error) {
      logger.error('删除模型失败:', error)
      return false
    }
  }
  
  /**
   * 加载待恢复的下载
   */
  async function loadPendingDownloads() {
    try {
      const res = await fetch(`${API_BASE()}/downloads/pending`)
      const data = await res.json()
      
      for (const download of (data.downloads || [])) {
        const progress: ModelDownloadProgress = {
          status: download.status as DownloadStatus,
          progress: download.progress || 0,
          downloadedBytes: download.downloaded_bytes || 0,
          totalBytes: download.total_bytes || 0,
          downloadedFiles: 0,
          totalFiles: 0,
          currentFile: '',
          message: '',
          errorMessage: download.error_message
        }
        downloadProgress.value.set(download.model_size, progress)
        
        // 如果是 downloading 状态，恢复轮询
        if (download.status === 'downloading') {
          startProgressPolling(download.model_size)
        }
      }
      
      logger.info(`📋 加载待恢复下载: ${data.downloads?.length || 0} 个`)
    } catch (error) {
      logger.error('加载待恢复下载失败:', error)
    }
  }
  
  /**
   * 设置是否使用镜像
   */
  function setUseMirror(value: boolean) {
    useMirror.value = value
  }
  
  /**
   * 初始化
   */
  async function initialize() {
    await Promise.all([
      loadStatus(),
      loadModels(),
      loadPendingDownloads()
    ])
  }
  
  /**
   * 清理（组件卸载时调用）
   */
  function cleanup() {
    for (const timerId of pollingTimers.value.values()) {
      window.clearInterval(timerId)
    }
    pollingTimers.value.clear()
  }
  
  // ============ 返回 ============
  
  return {
    // 状态
    status,
    models,
    downloadProgress,
    useMirror,
    
    // 计算属性
    installedModels,
    hasInstalledModels,
    activeDownloads,
    isDownloading,
    
    // 方法
    loadStatus,
    loadModels,
    downloadModel,
    pauseDownload,
    cancelDownload,
    resumeDownload,
    deleteModel,
    loadPendingDownloads,
    setUseMirror,
    initialize,
    cleanup
  }
})


