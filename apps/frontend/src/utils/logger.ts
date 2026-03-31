/**
 * 前端日志工具
 * 
 * 在 Tauri 应用中，console.log 的输出不容易查看
 * 这个工具将日志输出到控制台并批量上报到后端
 */

import { buildBackendUrl } from './backendUrl'

type FrontendLogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'
type FrontendRuntime = 'tauri' | 'web'

interface FrontendLogMeta {
  runtime: FrontendRuntime
  page?: string
  session_id: string
  client: string
}

interface FrontendLogEntry {
  level: FrontendLogLevel
  message: string
  data?: any
  timestamp: string
  meta?: FrontendLogMeta
}

class Logger {
  private readonly maxQueueSize = 2000
  private readonly maxBatchSize = 200
  private readonly sessionId = this.createSessionId()
  private backendQueue: FrontendLogEntry[] = []
  private flushTimer: number | null = null
  private flushInFlight = false
  private backoffMs = 500

  private createSessionId(): string {
    const randomUUID = (globalThis.crypto as any)?.randomUUID
    if (typeof randomUUID === 'function') {
      return randomUUID.call(globalThis.crypto)
    }
    return `fe-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  }

  /**
   * 格式化日志消息
   */
  private format(level: string, message: string, data?: any): string {
    const timestamp = new Date().toISOString()
    let logLine = `[${timestamp}] [${level}] ${message}`
    
    if (data !== undefined) {
      if (typeof data === 'object') {
        logLine += '\n' + JSON.stringify(data, null, 2)
      } else {
        logLine += ' ' + String(data)
      }
    }
    
    return logLine
  }

  private enqueueToBackend(entry: FrontendLogEntry) {
    if (typeof fetch !== 'function') {
      return
    }

    this.backendQueue.push(entry)
    if (this.backendQueue.length > this.maxQueueSize) {
      this.backendQueue.splice(0, this.backendQueue.length - this.maxQueueSize)
    }
    this.scheduleFlush(0)
  }

  private scheduleFlush(delayMs: number) {
    if (this.flushTimer !== null) {
      return
    }
    this.flushTimer = window.setTimeout(() => {
      this.flushTimer = null
      this.flushToBackend()
    }, delayMs)
  }

  private async flushToBackend() {
    if (this.flushInFlight) {
      return
    }
    if (this.backendQueue.length === 0) {
      return
    }
    if (typeof fetch !== 'function') {
      return
    }

    this.flushInFlight = true

    const batch = this.backendQueue.slice(0, this.maxBatchSize)
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 1500)

    try {
      const res = await fetch(buildBackendUrl('/api/frontend/logs'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logs: batch }),
        signal: controller.signal
      })

      if (!res.ok) {
        throw new Error(`http_${res.status}`)
      }

      this.backendQueue.splice(0, batch.length)
      this.backoffMs = 200

      if (this.backendQueue.length > 0) {
        this.scheduleFlush(0)
      }
    } catch {
      this.backoffMs = Math.min(Math.floor(this.backoffMs * 1.5), 5000)
      this.scheduleFlush(this.backoffMs)
    } finally {
      window.clearTimeout(timeoutId)
      this.flushInFlight = false
    }
  }

  /**
   * 输出日志
   */
  private log(level: string, message: string, data?: any) {
    // Release 模式下只允许 ERROR 日志
    // if (import.meta.env.PROD && level !== 'ERROR') {
    //   return
    // }

    const logLine = this.format(level, message, data)
    
    // 输出到控制台（logger内部允许使用console）
    switch (level) {
      case 'ERROR':
        console.error(logLine)
        if (data) console.error(data)
        break
      case 'WARN':
        console.warn(logLine)
        if (data) console.warn(data)
        break
      case 'INFO':
        console.info(logLine)
        if (data) console.info(data)
        break
      default:
        console.log(logLine)
        if (data) console.log(data)
    }

    this.enqueueToBackend({
      level: level as FrontendLogLevel,
      message,
      data,
      timestamp: new Date().toISOString(),
      meta: {
        runtime: '__TAURI_INTERNALS__' in window ? 'tauri' : 'web',
        page: typeof window.location?.pathname === 'string' ? window.location.pathname : undefined,
        session_id: this.sessionId,
        client: '@dawnchat/frontend'
      }
    })
  }

  info(message: string, data?: any) {
    this.log('INFO', message, data)
  }

  warn(message: string, data?: any) {
    this.log('WARN', message, data)
  }

  error(message: string, data?: any) {
    this.log('ERROR', message, data)
  }

  debug(message: string, data?: any) {
    this.log('DEBUG', message, data)
  }
}

// 导出单例
export const logger = new Logger()
