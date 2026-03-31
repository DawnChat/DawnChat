import { beforeEach, describe, expect, it, vi } from 'vitest'
import { agentV3Adapter } from '../agentV3Adapter'
import type { CodingAgentEvent } from '../engineAdapter'

function createFetchResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data)
  } as Response
}

describe('agentV3Adapter', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/api/agentv3/engine/meta')) {
          return createFetchResponse({
            engine: 'agentv3',
            version: '0.1.0',
            protocol_version: 'dep/1',
            capabilities: {}
          })
        }
        if (url.includes('/api/agentv3/session') && !url.includes('/message')) {
          return createFetchResponse({ id: 'ses_v3_1' })
        }
        throw new Error(`unexpected fetch: ${url}`)
      })
    )
  })

  it('createSession 走 /api/agentv3/session 且会先探活 meta', async () => {
    const sessionId = await agentV3Adapter.createSession('test')
    expect(sessionId).toBe('ses_v3_1')

    const urls = vi.mocked(globalThis.fetch).mock.calls.map((call) => String(call[0]))
    expect(urls.some((url) => url.includes('/api/agentv3/engine/meta'))).toBe(true)
    expect(urls.some((url) => url.includes('/api/agentv3/session'))).toBe(true)
  })

  it('subscribeEvents 能解析 SSE id 并透传 eventID', async () => {
    const encoder = new TextEncoder()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/api/agentv3/engine/meta')) {
          return createFetchResponse({
            engine: 'agentv3',
            version: '0.1.0',
            protocol_version: 'dep/1',
            capabilities: {}
          })
        }
        if (url.includes('/api/agentv3/event')) {
          const stream = new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(
                encoder.encode('id: 12\ndata: {"type":"run.progress","properties":{"sessionID":"ses_1"}}\n\n')
              )
              controller.close()
            }
          })
          return new Response(stream, {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' }
          })
        }
        throw new Error(`unexpected fetch: ${url}`)
      })
    )

    const events: Array<CodingAgentEvent & { eventID?: number }> = []
    const unsubscribe = await agentV3Adapter.subscribeEvents((evt) => {
      events.push(evt as CodingAgentEvent & { eventID?: number })
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    unsubscribe()
    const progress = events.find((item) => item.type === 'run.progress')
    expect(progress).toBeTruthy()
    expect(progress?.eventID).toBe(12)
  })

  it('subscribeEvents 会带 Last-Event-ID 重连并读取 retry 指令', async () => {
    vi.useFakeTimers()
    try {
      const encoder = new TextEncoder()
      let eventCallCount = 0
      vi.stubGlobal(
        'fetch',
        vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
          const url = String(input)
          if (url.includes('/api/agentv3/engine/meta')) {
            return createFetchResponse({
              engine: 'agentv3',
              version: '0.1.0',
              protocol_version: 'dep/1',
              capabilities: {}
            })
          }
          if (url.includes('/api/agentv3/event')) {
            eventCallCount += 1
            if (eventCallCount === 2) {
              const headers = (init?.headers || {}) as Record<string, string>
              expect(headers['Last-Event-ID']).toBe('12')
            }
            const stream = new ReadableStream<Uint8Array>({
              start(controller) {
                if (eventCallCount === 1) {
                  controller.enqueue(
                    encoder.encode('retry: 5\nid: 12\ndata: {"type":"run.progress","properties":{"sessionID":"ses_1"}}\n\n')
                  )
                  controller.close()
                  return
                }
                controller.enqueue(
                  encoder.encode('id: 13\ndata: {"type":"run.completed","properties":{"sessionID":"ses_1"}}\n\n')
                )
                controller.close()
              }
            })
            return new Response(stream, {
              status: 200,
              headers: { 'Content-Type': 'text/event-stream' }
            })
          }
          throw new Error(`unexpected fetch: ${url}`)
        })
      )

      const events: Array<CodingAgentEvent> = []
      const unsubscribe = await agentV3Adapter.subscribeEvents((evt) => {
        events.push(evt)
      })
      await vi.advanceTimersByTimeAsync(2500)
      await Promise.resolve()
      await Promise.resolve()
      unsubscribe()
      expect(eventCallCount).toBeGreaterThanOrEqual(2)
      expect(events.some((item) => item.type === 'run.progress')).toBe(true)
      expect(events.some((item) => item.type === 'run.completed')).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })
})

