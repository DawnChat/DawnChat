import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BRIDGE_MESSAGE_TYPE } from '../constants'
import { PluginUiBridgeClient } from '../bridgeClient'

vi.mock('../../../utils/backendUrl', () => ({
  getBackendUrl: () => 'http://127.0.0.1:18080'
}))

vi.mock('../../../utils/logger', () => ({
  logger: {
    info: vi.fn(),
    warn: vi.fn()
  }
}))

class FakeWebSocket {
  static readonly OPEN = 1
  static instances: FakeWebSocket[] = []

  readonly url: string
  readyState = FakeWebSocket.OPEN
  sent: string[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: ((error: unknown) => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(payload: string) {
    this.sent.push(payload)
  }

  close() {}
}

describe('PluginUiBridgeClient', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket as unknown as typeof WebSocket)
  })

  it('connects and dispatches bridge messages', () => {
    const onRequest = vi.fn()
    const onEvent = vi.fn()
    const client = new PluginUiBridgeClient('plugin.demo', { onRequest, onEvent })
    client.connect()

    const ws = FakeWebSocket.instances[0]
    expect(ws.url).toContain('/ws/plugin-ui-bridge')
    expect(ws.url).toContain('plugin_id=plugin.demo')

    ws.onmessage?.({
      data: JSON.stringify({
        type: BRIDGE_MESSAGE_TYPE.REQUEST,
        requestId: 'r1',
        pluginId: 'plugin.demo',
        op: 'describe',
        payload: {}
      })
    })
    expect(onRequest).toHaveBeenCalledTimes(1)

    ws.onmessage?.({
      data: JSON.stringify({
        type: BRIDGE_MESSAGE_TYPE.EVENT,
        event: 'context_push',
        pluginId: 'plugin.demo',
        payload: { items: [] }
      })
    })
    expect(onEvent).toHaveBeenCalledTimes(1)
  })

  it('sends result payload when websocket is open', () => {
    const client = new PluginUiBridgeClient('plugin.demo', { onRequest: vi.fn() })
    client.connect()
    const ws = FakeWebSocket.instances[0]

    client.sendResult('req_1', { ok: true })
    expect(ws.sent).toHaveLength(1)
    const payload = JSON.parse(ws.sent[0])
    expect(payload.type).toBe(BRIDGE_MESSAGE_TYPE.RESULT)
    expect(payload.requestId).toBe('req_1')
  })
})
