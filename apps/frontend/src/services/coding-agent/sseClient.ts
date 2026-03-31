export interface SseClientEvent {
  id?: string
  retry?: number
  event?: string
  data: string
}

interface StartSseClientOptions {
  url: string
  signal: AbortSignal
  headers?: Record<string, string>
  initialLastEventId?: string
  initialRetryDelayMs?: number
  maxRetryDelayMs?: number
  onStatus: (status: 'connecting' | 'reconnecting' | 'streaming' | 'closed', meta: Record<string, unknown>) => void
  onEvent: (event: SseClientEvent, meta: { lastEventId: string }) => void
  onError?: (error: unknown, meta: { reconnectDelay: number; lastEventId: string }) => void
}

function sleepWithSignal(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.resolve()
  }
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve()
    }, ms)
    const onAbort = () => {
      window.clearTimeout(timer)
      signal.removeEventListener('abort', onAbort)
      resolve()
    }
    signal.addEventListener('abort', onAbort)
  })
}

export async function startSseClient(options: StartSseClientOptions): Promise<void> {
  const {
    url,
    signal,
    headers,
    initialLastEventId = '',
    initialRetryDelayMs = 1000,
    maxRetryDelayMs = 30000,
    onStatus,
    onEvent,
    onError
  } = options

  let cancelled = false
  let lastEventId = initialLastEventId
  let reconnectDelay = initialRetryDelayMs
  let serverRetryDelay = initialRetryDelayMs
  let attempt = 0

  while (!cancelled && !signal.aborted) {
    try {
      attempt += 1
      onStatus(attempt === 1 ? 'connecting' : 'reconnecting', { reconnectDelay, lastEventId })
      const requestHeaders: Record<string, string> = { ...(headers || {}) }
      if (lastEventId) {
        requestHeaders['Last-Event-ID'] = lastEventId
      }
      const resp = await fetch(url, {
        signal,
        headers: requestHeaders
      })
      if (!resp.ok || !resp.body) {
        throw new Error(`订阅事件失败: ${resp.status}`)
      }
      onStatus('streaming', { reconnectDelay, lastEventId })
      reconnectDelay = initialRetryDelayMs
      attempt = 0

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (!cancelled && !signal.aborted) {
        const chunk = await reader.read()
        if (chunk.done) break
        buffer += decoder.decode(chunk.value, { stream: true })
        const segments = buffer.split(/\r?\n\r?\n/)
        buffer = segments.pop() || ''
        for (const rawEvent of segments) {
          const lines = rawEvent.split(/\r?\n/)
          const dataLines: string[] = []
          let parsedId = ''
          let parsedEvent = ''
          for (const line of lines) {
            if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).trim())
              continue
            }
            if (line.startsWith('id:')) {
              parsedId = line.slice(3).trim()
              continue
            }
            if (line.startsWith('event:')) {
              parsedEvent = line.slice(6).trim()
              continue
            }
            if (line.startsWith('retry:')) {
              const parsedRetry = Number.parseInt(line.slice(6).trim(), 10)
              if (Number.isFinite(parsedRetry) && parsedRetry > 0) {
                serverRetryDelay = parsedRetry
              }
            }
          }
          if (dataLines.length === 0) continue
          const data = dataLines.join('\n').trim()
          if (!data) continue
          if (parsedId) {
            lastEventId = parsedId
          }
          onEvent(
            {
              id: parsedId || undefined,
              event: parsedEvent || undefined,
              retry: serverRetryDelay,
              data
            },
            { lastEventId }
          )
        }
      }
    } catch (error) {
      if (signal.aborted) {
        cancelled = true
        break
      }
      onStatus('reconnecting', { reconnectDelay, lastEventId, error: error instanceof Error ? error.message : String(error) })
      onError?.(error, { reconnectDelay, lastEventId })
    }
    if (cancelled || signal.aborted) break
    await sleepWithSignal(reconnectDelay, signal)
    reconnectDelay = Math.min(Math.max(serverRetryDelay, reconnectDelay * 2), maxRetryDelayMs)
  }

  onStatus('closed', { lastEventId })
}
