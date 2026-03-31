import { BRIDGE_MESSAGE_TYPE } from './constants'

export type BridgeRequestOp =
  | 'describe'
  | 'query'
  | 'act'
  | 'scroll'
  | 'capabilities_list'
  | 'capability_invoke'
  | 'runtime_refresh'

export interface BridgeRequestMessage {
  type: typeof BRIDGE_MESSAGE_TYPE.REQUEST
  requestId: string
  pluginId: string
  op: BridgeRequestOp
  payload: Record<string, unknown>
}

export interface BridgeEventMessage {
  type: typeof BRIDGE_MESSAGE_TYPE.EVENT
  event: string
  pluginId: string
  payload: Record<string, unknown>
}

export interface BridgeResultOutbound {
  type: typeof BRIDGE_MESSAGE_TYPE.RESULT
  requestId: string
  result: Record<string, unknown>
}

export interface ContextPushItem {
  type: 'text' | 'image'
  text?: string
  uri?: string
  mime?: string
}

export interface ContextPushPayload {
  items: ContextPushItem[]
  mode?: string
  metadata?: Record<string, unknown>
}

export interface TtsSpeakAcceptedPayload {
  plugin_id: string
  task_id: string
  stream_url: string
  status_url: string
  mode?: string
  source?: string
}

export interface TtsStoppedPayload {
  plugin_id: string
  task_id?: string
  stopped: boolean
  source?: string
}
