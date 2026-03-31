/**
 * 环境管理相关类型定义
 */

/**
 * 下载任务状态
 */
export type DownloadStatus = 'idle' | 'pending' | 'downloading' | 'paused' | 'completed' | 'failed' | 'cancelled' | 'not_found'

/**
 * 环境类别
 */
export type EnvironmentCategory = 'llm' | 'tts' | 'asr' | 'ffmpeg' | 'cloud' | 'image_gen' | 'scoring'

/**
 * 图像生成任务类型
 */
export type ImageGenTaskType = 
  | 'text_to_image' 
  | 'image_to_image' 
  | 'inpaint' 
  | 'upscale' 
  | 'video_gen'

/**
 * 图像生成模型信息
 */
export interface ImageGenModel {
  id: string
  name: string
  description: string
  types: ImageGenTaskType[]
  sizeGb: number
  downloadUrl: string
  filename: string
  recommendedWorkflows: string[]
  vramRequiredGb: number
  tags: string[]
  modelType: string
  installed: boolean
  downloading: boolean
  progress?: number
}

/**
 * 图像生成工作流模板
 */
export interface ImageGenWorkflow {
  id: string
  name: string
  description: string
  taskType: ImageGenTaskType
  requiredModels: string[]
  previewImage?: string
  inputSchema: Record<string, any>
  available: boolean
  missingModels: string[]
}

/**
 * 图像生成服务状态
 */
export interface ImageGenServiceStatus {
  installed: boolean
  running: boolean
  ready: boolean
  hasModels: boolean
  canStart: boolean
  startBlockedReason?: string
  installedCount: number
  totalModels: number
}

/**
 * 统一下载任务接口
 * 用于聚合不同类型的下载任务，在 UI 层统一展示
 */
export interface UnifiedDownloadTask {
  /** 唯一标识 */
  id: string
  /** 任务类别 */
  category: 'llm' | 'tts' | 'asr' | 'ffmpeg' | 'image_gen' | 'scoring'
  /** 显示名称 */
  name: string
  /** 下载状态 */
  status: DownloadStatus
  /** 下载进度 (0-100) */
  progress: number
  /** 已下载字节数 */
  downloadedSize: number
  /** 总字节数 */
  totalSize: number
  /** 下载速度 (格式化字符串，如 "1.5 MB/s") */
  speed?: string
  /** 状态消息 */
  message?: string
  /** 错误消息 */
  errorMessage?: string
  /** 原始任务 ID（用于调用具体 store 的方法） */
  originalId?: string
  /** 额外信息（如文件数量等） */
  extra?: {
    downloadedFiles?: number
    totalFiles?: number
    /** 当前正在下载的文件名 */
    currentFile?: string
    /** 当前文件总大小 */
    currentFileSize?: number
    /** 当前文件已下载 */
    currentFileDownloaded?: number
  }
}

/**
 * 单个环境类别的状态
 */
export interface CategoryStatus {
  /** 是否就绪（有可用资源） */
  ready: boolean
  /** 正在进行的下载任务数 */
  activeDownloads: number
  /** 是否正在安装/配置 */
  installing?: boolean
}

/**
 * 所有环境的状态
 */
export interface EnvironmentStatus {
  llm: CategoryStatus
  tts: CategoryStatus
  asr: CategoryStatus
  ffmpeg: CategoryStatus & { installing: boolean }
  cloud: { configured: boolean }
  imageGen: CategoryStatus & { 
    running: boolean
    canStart: boolean 
  }
  scoring: CategoryStatus
}

/**
 * 环境导航项
 */
export interface EnvironmentNavItem {
  id: EnvironmentCategory
  icon: string
  label: string
  status: 'ready' | 'warning' | 'downloading' | 'error'
  badge?: number
}

/**
 * Plugin 环境依赖等级
 */
export type RequirementLevel = 'required' | 'optional' | 'local_only' | 'cloud_only' | false

/**
 * Plugin 环境依赖声明
 * 
 * AI 依赖语义：
 * - ai: 通用 AI 能力，本地 LLM 或 云端 API 满足其一即可
 * - local_ai: 必须本地运行，需要已下载的 LLM 模型
 * - cloud_ai: 必须云端，需要配置云端 API Key
 */
export interface EnvironmentRequirements {
  /** 通用 AI（本地 OR 云端） */
  ai?: RequirementLevel
  /** 仅本地 AI（需要已下载 LLM 模型） */
  local_ai?: RequirementLevel
  /** 仅云端 AI（需要配置 API Key） */
  cloud_ai?: RequirementLevel
  /** TTS 模型依赖 */
  tts?: RequirementLevel
  /** ASR 模型依赖 */
  asr?: RequirementLevel
  /** FFmpeg 依赖 */
  ffmpeg?: RequirementLevel
  /** 图像生成依赖 */
  image_gen?: RequirementLevel
  /** 口语评分依赖 */
  scoring?: RequirementLevel
}

/**
 * 环境检查结果
 */
export interface EnvironmentCheckResult {
  /** 是否满足所有依赖 */
  satisfied: boolean
  /** 缺失的环境项 */
  missing: EnvironmentCategory[]
  /** 详细信息 */
  details: {
    category: EnvironmentCategory
    requirement: RequirementLevel
    currentStatus: 'ready' | 'not_ready'
    message?: string
  }[]
}

