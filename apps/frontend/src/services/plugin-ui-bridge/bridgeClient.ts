import { getBackendUrl } from '../../utils/backendUrl'
import { logger } from '../../utils/logger'
import { BRIDGE_MESSAGE_TYPE } from './constants'
import type {
  BridgeEventMessage,
  BridgeRequestMessage,
  BridgeResultOutbound
} from './messageProtocol'

type Handlers = {
  onRequest: (msg: BridgeRequestMessage) => void
  onEvent?: (msg: BridgeEventMessage) => void
  onDisconnect?: () => void
}

export class PluginUiBridgeClient {
  private pluginId: string
  private handlers: Handlers
  private ws: WebSocket | null = null
  private disposed = false
  private reconnectTimer: number | null = null

  constructor(pluginId: string, handlers: Handlers) {
    this.pluginId = pluginId
    this.handlers = handlers
  }

  connect() {
    this.disposed = false
    this.open()
  }

  disconnect() {
    this.disposed = true
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    try {
      this.ws?.close()
    } catch {
    }
    this.ws = null
  }

  sendResult(requestId: string, result: Record<string, unknown>) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      logger.warn('[plugin_ui_bridge] send result skipped, ws not open', { requestId })
      return
    }
    const payload: BridgeResultOutbound = {
      type: BRIDGE_MESSAGE_TYPE.RESULT,
      requestId,
      result
    }
    this.ws.send(JSON.stringify(payload))
  }

  private open() {
    if (this.disposed) return
    const base = new URL(getBackendUrl())
    base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
    base.pathname = '/ws/plugin-ui-bridge'
    base.searchParams.set('plugin_id', this.pluginId)
    const ws = new WebSocket(base.toString())
    this.ws = ws
    ws.onopen = () => {
      logger.info('[plugin_ui_bridge] connected', { pluginId: this.pluginId })
    }
    ws.onclose = () => {
      if (this.disposed) return
      this.handlers.onDisconnect?.()
      this.scheduleReconnect()
    }
    ws.onerror = (error) => {
      logger.warn('[plugin_ui_bridge] websocket error', { error: String(error) })
    }
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data || '{}')) as { type?: string }
        if (payload.type === BRIDGE_MESSAGE_TYPE.REQUEST) {
          this.handlers.onRequest(payload as BridgeRequestMessage)
          return
        }
        if (payload.type === BRIDGE_MESSAGE_TYPE.EVENT) {
          this.handlers.onEvent?.(payload as BridgeEventMessage)
        }
      } catch (error) {
        logger.warn('[plugin_ui_bridge] invalid message payload', { error: String(error) })
      }
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer)
    }
    this.reconnectTimer = window.setTimeout(() => this.open(), 1000)
  }
}

