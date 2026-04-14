import { beforeEach, describe, expect, it, vi } from 'vitest'
import { openCodeAdapter } from '../openCodeAdapter'

const { mockCreateClient } = vi.hoisted(() => ({
  mockCreateClient: vi.fn<(...args: any[]) => any>()
}))

vi.mock('@opencode-ai/sdk/client', () => ({
  createOpencodeClient: (...args: any[]) => mockCreateClient(...args)
}))

function createFetchResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data)
  } as Response
}

describe('openCodeAdapter', () => {
  beforeEach(() => {
    mockCreateClient.mockReset()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/api/opencode/health')) {
          return createFetchResponse({
            status: 'success',
            data: {
              status: 'running',
              healthy: true,
              base_url: 'http://127.0.0.1:4096'
            }
          })
        }
        if (url.includes('/session')) {
          return createFetchResponse({ id: 'ses_123' })
        }
        if (url.includes('/question/') && url.endsWith('/reply')) {
          return createFetchResponse(true)
        }
        if (url.includes('/question/') && url.endsWith('/reject')) {
          return createFetchResponse(true)
        }
        if (url.includes('/question')) {
          return createFetchResponse([
            {
              id: 'que_1',
              sessionID: 'ses_123',
              questions: [{ question: 'pick one', header: 'Q1', options: [{ label: 'A', description: 'opt A' }] }]
            },
            {
              id: 'que_2',
              sessionID: 'ses_other',
              questions: [{ question: 'pick two', header: 'Q2', options: [{ label: 'B', description: 'opt B' }] }]
            }
          ])
        }
        if (url.endsWith('/permission')) {
          return createFetchResponse([
            {
              id: 'per_1',
              sessionID: 'ses_123',
              permission: 'external_directory',
              patterns: ['/tmp/*'],
              metadata: {}
            },
            {
              id: 'per_2',
              sessionID: 'ses_other',
              permission: 'edit',
              patterns: ['src/*'],
              metadata: {}
            }
          ])
        }
        throw new Error(`unexpected fetch: ${url}`)
      })
    )
  })

  it('createSession 只探活 /health，不会隐式调用 /api/opencode/start', async () => {
    const sessionId = await openCodeAdapter.createSession('test')
    expect(sessionId).toBe('ses_123')

    const urls = vi.mocked(globalThis.fetch).mock.calls.map((call) => String(call[0]))
    expect(urls.some((url) => url.includes('/api/opencode/health'))).toBe(true)
    expect(urls.some((url) => /\/api\/opencode\/start(?:\?|$)/.test(url))).toBe(false)
  })

  it('listSessions 会附带 directory 查询参数', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/api/opencode/health')) {
          return createFetchResponse({
            status: 'success',
            data: {
              status: 'running',
              healthy: true,
              base_url: 'http://127.0.0.1:4096'
            }
          })
        }
        if (url.includes('/session')) {
          return createFetchResponse([{ id: 'ses_123', title: 'test', directory: '/tmp/plugin-a' }])
        }
        throw new Error(`unexpected fetch: ${url}`)
      })
    )

    const rows = await openCodeAdapter.listSessions({ directory: '/tmp/plugin-a' })
    expect(rows).toHaveLength(1)

    const urls = vi.mocked(globalThis.fetch).mock.calls.map((call) => String(call[0]))
    expect(urls.some((url) => url.includes('/session?directory=%2Ftmp%2Fplugin-a'))).toBe(true)
  })

  it('createSession 会附带 directory 查询参数', async () => {
    await openCodeAdapter.createSession('test', { directory: '/tmp/plugin-a' })

    const urls = vi.mocked(globalThis.fetch).mock.calls.map((call) => String(call[0]))
    expect(urls.some((url) => url.includes('/session?directory=%2Ftmp%2Fplugin-a'))).toBe(true)
  })

  it('subscribeEvents 优先通过 SDK 订阅并转发 stream/status 事件', async () => {
    const subscribe = vi.fn(async () => ({
      stream: (async function* () {
        yield { type: 'server.connected', properties: {} }
      })()
    }))
    mockCreateClient.mockReturnValue({
      event: {
        subscribe
      }
    })

    const events: any[] = []
    const unsubscribe = await openCodeAdapter.subscribeEvents((evt) => {
      events.push(evt)
    })
    await Promise.resolve()
    await Promise.resolve()
    unsubscribe()

    expect(subscribe).toHaveBeenCalled()
    expect(events.some((evt) => evt?.type === 'stream.status' && evt?.properties?.status === 'connecting')).toBe(true)
    expect(events.some((evt) => evt?.type === 'stream.status' && evt?.properties?.status === 'streaming')).toBe(true)
    expect(events.some((evt) => evt?.type === 'server.connected')).toBe(true)
  })

  it('subscribeEvents 对 Failed to fetch 会重试直至成功', async () => {
    let calls = 0
    const subscribe = vi.fn(async () => {
      calls += 1
      if (calls < 3) {
        throw new Error('Failed to fetch')
      }
      return {
        stream: (async function* () {
          yield { type: 'server.connected', properties: {} }
        })()
      }
    })
    mockCreateClient.mockReturnValue({
      event: {
        subscribe
      }
    })

    const unsubscribe = await openCodeAdapter.subscribeEvents(() => {})
    await new Promise((r) => setTimeout(r, 1600))
    unsubscribe()

    expect(subscribe).toHaveBeenCalledTimes(3)
  }, 5000)

  it('subscribeEvents 对非网络错误不重试', async () => {
    const subscribe = vi.fn(async () => {
      throw new Error('Internal Server Error')
    })
    mockCreateClient.mockReturnValue({
      event: {
        subscribe
      }
    })

    const unsubscribe = await openCodeAdapter.subscribeEvents(() => {})
    await new Promise((r) => setTimeout(r, 50))
    unsubscribe()

    expect(subscribe).toHaveBeenCalledTimes(1)
  })

  it('onSseError Failed to fetch 会 abort 并 emit closed sdk_sse_error_abort', async () => {
    let capturedSignal: AbortSignal | undefined
    const subscribe = vi.fn(async (opts: any) => {
      capturedSignal = opts?.signal
      opts?.onSseError?.(new Error('Failed to fetch'))
      return {
        stream: (async function* () {
          // empty — for-await exits; abort already issued from onSseError
        })()
      }
    })
    mockCreateClient.mockReturnValue({
      event: { subscribe }
    })

    const events: unknown[] = []
    const unsubscribe = await openCodeAdapter.subscribeEvents((evt) => {
      events.push(evt)
    })
    await Promise.resolve()
    await Promise.resolve()
    expect(capturedSignal?.aborted).toBe(true)
    expect(
      events.some(
        (evt) =>
          (evt as { type?: string })?.type === 'stream.status' &&
          (evt as { properties?: { status?: string; recover_reason?: string } })?.properties?.status === 'closed' &&
          (evt as { properties?: { recover_reason?: string } })?.properties?.recover_reason === 'sdk_sse_error_abort'
      )
    ).toBe(true)
    unsubscribe()
  })

  it('SDK onSseError 会映射为 reconnecting 状态事件', async () => {
    const subscribe = vi.fn(async (opts: any) => {
      opts?.onSseError?.(new Error('net down'))
      return {
        stream: (async function* () {
          yield { type: 'server.connected', properties: {} }
        })()
      }
    })
    mockCreateClient.mockReturnValue({
      event: {
        subscribe
      }
    })

    const events: any[] = []
    const unsubscribe = await openCodeAdapter.subscribeEvents((evt) => {
      events.push(evt)
    })
    await Promise.resolve()
    await Promise.resolve()
    unsubscribe()

    expect(events.some((evt) => evt?.type === 'stream.status' && evt?.properties?.status === 'reconnecting')).toBe(
      true
    )
  })

  it('支持 question API，并可按 session 过滤列表', async () => {
    expect(openCodeAdapter.supportsQuestions?.()).toBe(true)
    const rows = await openCodeAdapter.listQuestions?.('ses_123')
    expect(rows?.length).toBe(1)
    expect(rows?.[0]?.id).toBe('que_1')
  })

  it('replyQuestion 会提交 answers payload', async () => {
    const ok = await openCodeAdapter.replyQuestion?.('que_1', [['A']])
    expect(ok).toBe(true)
    const call = vi
      .mocked(globalThis.fetch)
      .mock.calls.find((item) => String(item[0]).includes('/question/que_1/reply'))
    expect(call).toBeTruthy()
    expect(String((call?.[1] as RequestInit | undefined)?.body || '')).toContain('"answers":[["A"]]')
  })

  it('rejectQuestion 会请求 reject 端点', async () => {
    const ok = await openCodeAdapter.rejectQuestion?.('que_1')
    expect(ok).toBe(true)
    expect(
      vi
        .mocked(globalThis.fetch)
        .mock.calls.some((item) => String(item[0]).includes('/question/que_1/reject'))
    ).toBe(true)
  })

  it('listPermissions 支持按 session 过滤', async () => {
    const rows = await openCodeAdapter.listPermissions?.('ses_123')
    expect(rows?.length).toBe(1)
    expect(rows?.[0]?.id).toBe('per_1')
  })
})
