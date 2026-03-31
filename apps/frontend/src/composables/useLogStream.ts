/**
 * Log Stream Composable
 *
 * 管理 SSE 日志流连接，支持实时日志推送和断线重连。
 */

import { ref, shallowRef, onUnmounted, computed } from 'vue'
import { useBackendStatus } from './useBackendStatus'
import { logger } from '../utils/logger'

// ========== 类型定义 ==========

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | 'STDOUT' | 'STDERR'

export interface LogEntry {
  timestamp: string
  level: LogLevel
  message: string
  stage_id: string
  pipeline_id: string
  worker_id: string
  execution_id?: string
  source: string
  line_number?: number
  metadata: Record<string, unknown>
}

export interface LogStreamOptions {
  stageId?: string
  pipelineId?: string
  workerId?: string
  minLevel?: LogLevel
  includeHistory?: boolean
  historyLimit?: number
  maxEntries?: number // 最大缓存条目数
  autoReconnect?: boolean
  reconnectInterval?: number
}

export interface LogStreamState {
  isConnecting: boolean
  isConnected: boolean
  error: string | null
  historyLoaded: boolean
  entryCount: number
}

// ========== 日志级别优先级 ==========

const LOG_LEVEL_PRIORITY: Record<LogLevel, number> = {
  DEBUG: 0,
  INFO: 1,
  STDOUT: 1,
  WARNING: 2,
  ERROR: 3,
  STDERR: 3,
  CRITICAL: 4,
}

// ========== Composable ==========

export function useLogStream(options: LogStreamOptions = {}) {
  const {
    stageId,
    pipelineId,
    workerId,
    minLevel,
    includeHistory = true,
    historyLimit = 100,
    maxEntries = 10000,
    autoReconnect = true,
    reconnectInterval = 3000,
  } = options

  // 状态
  const entries = shallowRef<LogEntry[]>([])
  const state = ref<LogStreamState>({
    isConnecting: false,
    isConnected: false,
    error: null,
    historyLoaded: false,
    entryCount: 0,
  })

  // 内部变量
  let eventSource: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let isManualClose = false

  const { backendUrl } = useBackendStatus()

  // 构建 SSE URL
  const buildUrl = (): string => {
    const base = backendUrl.value
    let path = ''
    const params = new URLSearchParams()

    if (stageId) {
      path = `/api/pipeline/stages/${stageId}/logs/stream`
    } else if (pipelineId) {
      path = `/api/pipeline/pipelines/${pipelineId}/logs/stream`
    } else {
      throw new Error('必须指定 stageId 或 pipelineId')
    }

    params.set('include_history', String(includeHistory))
    params.set('history_limit', String(historyLimit))
    if (minLevel) {
      params.set('level', minLevel)
    }

    return `${base}${path}?${params.toString()}`
  }

  // 添加日志条目
  const addEntry = (entry: LogEntry) => {
    // 级别过滤
    if (minLevel) {
      const priority = LOG_LEVEL_PRIORITY[entry.level] ?? 0
      const minPriority = LOG_LEVEL_PRIORITY[minLevel] ?? 0
      if (priority < minPriority) {
        return
      }
    }

    // Worker 过滤
    if (workerId && entry.worker_id !== workerId) {
      return
    }

    // 添加到列表
    const current = entries.value
    const newEntries = [...current, entry]

    // 限制最大条目数
    if (newEntries.length > maxEntries) {
      newEntries.splice(0, newEntries.length - maxEntries)
    }

    entries.value = newEntries
    state.value.entryCount = newEntries.length
  }

  // 连接 SSE
  const connect = () => {
    if (eventSource) {
      disconnect()
    }

    isManualClose = false
    state.value.isConnecting = true
    state.value.error = null

    try {
      const url = buildUrl()
      logger.info('[LogStream] 连接 SSE:', url)

      eventSource = new EventSource(url)

      eventSource.onopen = () => {
        logger.info('[LogStream] SSE 连接已建立')
        state.value.isConnecting = false
        state.value.isConnected = true
      }

      eventSource.onmessage = (event) => {
        try {
          const entry = JSON.parse(event.data) as LogEntry
          addEntry(entry)
        } catch (e) {
          logger.warn('[LogStream] 解析日志失败:', e)
        }
      }

      // 处理历史日志事件
      eventSource.addEventListener('history', (event) => {
        try {
          const entry = JSON.parse((event as MessageEvent).data) as LogEntry
          addEntry(entry)
        } catch (e) {
          logger.warn('[LogStream] 解析历史日志失败:', e)
        }
      })

      // 历史日志加载完成
      eventSource.addEventListener('history_end', () => {
        logger.info('[LogStream] 历史日志加载完成')
        state.value.historyLoaded = true
      })

      eventSource.onerror = (error) => {
        logger.error('[LogStream] SSE 错误:', error)
        state.value.isConnecting = false
        state.value.isConnected = false
        state.value.error = '连接断开'

        if (!isManualClose && autoReconnect) {
          scheduleReconnect()
        }
      }
    } catch (e) {
      logger.error('[LogStream] 连接失败:', e)
      state.value.isConnecting = false
      state.value.error = String(e)
    }
  }

  // 断开连接
  const disconnect = () => {
    isManualClose = true

    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    if (eventSource) {
      eventSource.close()
      eventSource = null
    }

    state.value.isConnecting = false
    state.value.isConnected = false
    logger.info('[LogStream] SSE 连接已断开')
  }

  // 计划重连
  const scheduleReconnect = () => {
    if (reconnectTimer) return

    logger.info(`[LogStream] ${reconnectInterval}ms 后重连...`)
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, reconnectInterval)
  }

  // 清空日志
  const clearEntries = () => {
    entries.value = []
    state.value.entryCount = 0
    state.value.historyLoaded = false
  }

  // 过滤日志
  const filteredEntries = computed(() => {
    return entries.value
  })

  // 按级别统计
  const stats = computed(() => {
    const result: Record<LogLevel, number> = {
      DEBUG: 0,
      INFO: 0,
      WARNING: 0,
      ERROR: 0,
      CRITICAL: 0,
      STDOUT: 0,
      STDERR: 0,
    }

    for (const entry of entries.value) {
      result[entry.level]++
    }

    return {
      ...result,
      total: entries.value.length,
      errors: result.ERROR + result.CRITICAL,
      warnings: result.WARNING,
    }
  })

  // 搜索日志
  const searchEntries = (keyword: string): LogEntry[] => {
    if (!keyword.trim()) {
      return entries.value
    }

    const lowerKeyword = keyword.toLowerCase()
    return entries.value.filter(
      (entry) => entry.message.toLowerCase().includes(lowerKeyword)
    )
  }

  // 导出日志
  const exportLogs = (format: 'json' | 'text' = 'text'): string => {
    if (format === 'json') {
      return JSON.stringify(entries.value, null, 2)
    }

    return entries.value
      .map(
        (e) =>
          `[${e.timestamp}] [${e.level}] [${e.source}] ${e.message}`
      )
      .join('\n')
  }

  // 下载日志文件
  const downloadLogs = (filename?: string, format: 'json' | 'text' = 'text') => {
    const content = exportLogs(format)
    const ext = format === 'json' ? 'json' : 'log'
    const name = filename || `logs_${stageId || pipelineId}_${Date.now()}.${ext}`
    const mimeType = format === 'json' ? 'application/json' : 'text/plain'

    const blob = new Blob([content], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  }

  // 组件卸载时断开连接
  onUnmounted(() => {
    disconnect()
  })

  return {
    // 状态
    entries: filteredEntries,
    state,
    stats,

    // 方法
    connect,
    disconnect,
    clearEntries,
    searchEntries,
    exportLogs,
    downloadLogs,

    // 工具
    LOG_LEVEL_PRIORITY,
  }
}

// ========== 工具函数 ==========

/**
 * 获取日志级别颜色
 */
export function getLogLevelColor(level: LogLevel): string {
  const colors: Record<LogLevel, string> = {
    DEBUG: '#9ca3af',
    INFO: '#3b82f6',
    STDOUT: '#10b981',
    WARNING: '#f59e0b',
    ERROR: '#ef4444',
    STDERR: '#ef4444',
    CRITICAL: '#dc2626',
  }
  return colors[level] || '#6b7280'
}

/**
 * 获取日志级别标签
 */
export function getLogLevelLabel(level: LogLevel): string {
  const labels: Record<LogLevel, string> = {
    DEBUG: '调试',
    INFO: '信息',
    STDOUT: '输出',
    WARNING: '警告',
    ERROR: '错误',
    STDERR: '错误',
    CRITICAL: '严重',
  }
  return labels[level] || level
}

/**
 * 格式化时间戳
 */
export function formatLogTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    fractionalSecondDigits: 3,
  } as Intl.DateTimeFormatOptions)
}
