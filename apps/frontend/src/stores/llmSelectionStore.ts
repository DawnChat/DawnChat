/**
 * Model Store - 全局模型状态管理
 * 
 * 功能：
 * 1. 管理可用模型列表（本地 + 云端）
 * 2. 管理当前选中的模型
 * 3. 自动加载和缓存模型列表
 * 4. 持久化用户的模型选择偏好
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useI18n } from '@/composables/useI18n'
import { logger } from '@/utils/logger'
import { buildBackendUrl } from '@/utils/backendUrl'

// ============ 类型定义 ============

export interface ModelInfo {
  id: string
  model_key?: string  // 统一格式：provider:model_id，用于 LLM 调用
  name: string
  provider: string
  provider_name?: string
  format?: string
}

export interface AvailableModels {
  local: ModelInfo[]
  cloud: Record<string, ModelInfo[]>
}

export interface ModelConfig {
  provider: string
  model: string
}

// ============ 常量 ============

const API_BASE = () => buildBackendUrl('')
const STORAGE_KEY = 'lastSelectedModelId'

// ============ Store 定义 ============

export const useLlmSelectionStore = defineStore('llmSelection', () => {
  const { t } = useI18n()
  // ============ 状态 ============
  
  const availableModels = ref<AvailableModels>({ local: [], cloud: {} })
  const selectedModelId = ref<string>('')
  const isLoading = ref(false)
  const isLoaded = ref(false)
  const lastLoadTime = ref<number>(0)
  const loadError = ref<string | null>(null)
  
  // 缓存时间（5分钟）
  const CACHE_DURATION = 5 * 60 * 1000
  
  // ============ 计算属性 ============
  
  /**
   * 当前选中的模型对象
   */
  const currentModel = computed<ModelInfo | null>(() => {
    if (!selectedModelId.value) return null
    
    // 先查找本地模型
    const localModel = availableModels.value.local.find((m: ModelInfo) => m.id === selectedModelId.value)
    if (localModel) return localModel
    
    // 再查找云端模型
    for (const provider in availableModels.value.cloud) {
      const cloudModel = availableModels.value.cloud[provider].find((m: ModelInfo) => m.id === selectedModelId.value)
      if (cloudModel) return cloudModel
    }
    
    return null
  })
  
  /**
   * 当前模型名称（用于UI显示）
   */
  const currentModelName = computed(() => currentModel.value?.name || t.value.common.selectModel)
  
  /**
   * 是否有可用模型
   */
  const hasModels = computed(() => {
    return availableModels.value.local.length > 0 || 
           Object.keys(availableModels.value.cloud).length > 0
  })
  
  /**
   * 当前模型配置（用于发送请求）
   * 使用 model_key 作为 model 字段，确保后端能正确解析
   */
  const modelConfig = computed<ModelConfig | undefined>(() => {
    if (!currentModel.value) return undefined
    // 优先使用 model_key（包含 provider 前缀的完整格式）
    // 兼容旧数据：如果没有 model_key，则手动拼接
    const modelKey = currentModel.value.model_key || 
      `${currentModel.value.provider}:${currentModel.value.id}`
    return {
      provider: currentModel.value.provider,
      model: modelKey
    }
  })
  
  // ============ 方法 ============
  
  /**
   * 获取厂商显示名称
   */
  function getProviderName(providerId: string): string {
    const map: Record<string, string> = {
      'openai': 'OpenAI',
      'google': 'Google Gemini',
      'gemini': 'Google Gemini',
      'anthropic': 'Anthropic Claude',
      'siliconflow': 'SiliconFlow',
      'local': t.value.common.localModel
    }
    return map[providerId] || providerId.toUpperCase()
  }
  
  /**
   * 加载可用模型列表
   * 
   * @param force 是否强制刷新（忽略缓存）
   * @param retryCount 重试次数（内部使用）
   */
  async function loadModels(force = false, retryCount = 0): Promise<void> {
    // 检查缓存
    if (!force && isLoaded.value && Date.now() - lastLoadTime.value < CACHE_DURATION) {
      logger.debug('[ModelStore] 使用缓存的模型列表')
      return
    }
    
    // 避免重复加载
    if (isLoading.value) {
      logger.debug('[ModelStore] 模型列表正在加载中...')
      return
    }
    
    isLoading.value = true
    loadError.value = null
    
    try {
      logger.info('[ModelStore] 加载可用模型列表...')
      
      const response = await fetch(`${API_BASE()}/api/models/available`)
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      
      if (data.status === 'success' && data.models) {
        const models = data.models
        if (!models.local) models.local = []
        if (!models.cloud) models.cloud = {}

        const cloudProviders = Object.entries(models.cloud as Record<string, ModelInfo[]>)
        const prioritizedCloudProviders = cloudProviders.sort(([a], [b]) => {
          if (a === 'siliconflow') return -1
          if (b === 'siliconflow') return 1
          return 0
        })
        models.cloud = Object.fromEntries(prioritizedCloudProviders)
        
        availableModels.value = models
        isLoaded.value = true
        lastLoadTime.value = Date.now()
        
        logger.info(`[ModelStore] ✅ 加载模型列表成功: ${models.local.length} 本地, ${Object.keys(models.cloud).length} 云端厂商`)
        
        // 恢复上次选择或设置默认值
        restoreOrSetDefaultModel(models)
        
      } else {
        logger.warn('[ModelStore] ⚠️ 获取模型列表响应状态非成功:', data)
        loadError.value = t.value.common.fetchFailed
      }
      
    } catch (error: any) {
      logger.error('[ModelStore] ❌ 加载模型列表失败:', {
        message: error.message,
        name: error.name
      })
      
      loadError.value = error.message
      
      // 重试逻辑
      if (retryCount < 5) {
        const delay = Math.min(1000 * Math.pow(1.5, retryCount), 5000)
        logger.info(`[ModelStore] ⏳ ${delay}ms 后重试加载模型列表 (${retryCount + 1}/5)...`)
        
        setTimeout(() => {
          loadModels(force, retryCount + 1)
        }, delay)
      }
      
    } finally {
      isLoading.value = false
    }
  }
  
  /**
   * 恢复上次选择或设置默认模型
   */
  function restoreOrSetDefaultModel(models: AvailableModels): void {
    const lastSelected = localStorage.getItem(STORAGE_KEY)
    let modelFound = false
    
    if (lastSelected) {
      // 检查本地模型
      if (models.local.some(m => m.id === lastSelected)) {
        selectedModelId.value = lastSelected
        modelFound = true
      } else {
        // 检查云端模型
        for (const providerModels of Object.values(models.cloud)) {
          if (providerModels.some(m => m.id === lastSelected)) {
            selectedModelId.value = lastSelected
            modelFound = true
            break
          }
        }
      }
    }
    
    // 如果没找到上次选择的，使用默认值
    if (!modelFound) {
      if (models.local.length > 0) {
        selectedModelId.value = models.local[0].id
      } else {
        const firstProvider = Object.keys(models.cloud)[0]
        if (firstProvider && models.cloud[firstProvider].length > 0) {
          selectedModelId.value = models.cloud[firstProvider][0].id
        }
      }
      
      // 保存默认选择
      if (selectedModelId.value) {
        localStorage.setItem(STORAGE_KEY, selectedModelId.value)
      }
    }
  }
  
  /**
   * 选择模型
   */
  function selectModel(model: ModelInfo): void {
    selectedModelId.value = model.id
    localStorage.setItem(STORAGE_KEY, model.id)
    logger.info(`[ModelStore] 🤖 切换模型: ${model.provider}:${model.name}`)
    
    // 同步到后端数据库
    syncModelPreference(model.id)
  }
  
  /**
   * 通过 ID 选择模型
   */
  function selectModelById(modelId: string): void {
    selectedModelId.value = modelId
    localStorage.setItem(STORAGE_KEY, modelId)
    syncModelPreference(modelId)
  }
  
  /**
   * 同步模型偏好到后端
   */
  async function syncModelPreference(modelId: string): Promise<void> {
    try {
      await fetch(`${API_BASE()}/api/storage/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'user_preference:model', value: modelId })
      })
      logger.debug('[ModelStore] ✅ 同步模型偏好到后端成功:', modelId)
    } catch (e) {
      logger.error('[ModelStore] ❌ 同步模型偏好到后端失败:', e)
    }
  }
  
  // ============ 返回 Store ============
  
  return {
    // 状态
    availableModels,
    selectedModelId,
    isLoading,
    isLoaded,
    loadError,
    
    // 计算属性
    currentModel,
    currentModelName,
    hasModels,
    modelConfig,
    
    // 方法
    getProviderName,
    loadModels,
    selectModel,
    selectModelById
  }
})
