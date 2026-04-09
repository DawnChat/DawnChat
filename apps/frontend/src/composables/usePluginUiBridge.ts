import { onMounted, onUnmounted, type ComputedRef, type Ref } from 'vue'
import {
  BRIDGE_EVENT,
  IFRAME_UI_AGENT_MESSAGE,
  UI_AGENT_RESPONSE_TYPES
} from '@dawnchat/host-orchestration-sdk/assistant-client'
import type {
  AssistantRuntimeEventPayload,
  BridgeRequestMessage,
  CapabilityInvokeExecutionContext,
  CapabilityInvokeRequest,
  ContextPushPayload,
  HostInvokeExecutionContext,
  HostInvokeRequest,
  TtsSpeakAcceptedPayload,
  TtsStoppedPayload
} from '@dawnchat/host-orchestration-sdk/assistant-client'
import {
  createBridgeRequestTimeoutStrategy,
  createPendingBridgeRequestTracker,
  type PendingBridgeRequestSource
} from '@dawnchat/host-orchestration-sdk/transport'
import { logger } from '../utils/logger'
import { PluginUiBridgeClient } from '../services/plugin-ui-bridge/bridgeClient'

interface UiBridgeOptions {
  pluginId: ComputedRef<string>
  iframeRef: Ref<HTMLIFrameElement | null>
  expectedOrigin: ComputedRef<string>
  onContextPush: (payload: ContextPushPayload) => void
  onTtsSpeakAccepted?: (payload: TtsSpeakAcceptedPayload) => void
  onTtsStopped?: (payload: TtsStoppedPayload) => void
  onAssistantRuntimeEvent?: (payload: AssistantRuntimeEventPayload) => void
  onCapabilityInvokeRequest?: (
    context: CapabilityInvokeExecutionContext
  ) => Promise<Record<string, unknown> | null> | Record<string, unknown> | null
  onHostInvokeRequest?: (
    context: HostInvokeExecutionContext
  ) => Promise<Record<string, unknown>> | Record<string, unknown>
}

function isContextPushPayload(payload: unknown): payload is ContextPushPayload {
  if (!payload || typeof payload !== 'object') return false
  const data = payload as { items?: unknown }
  return Array.isArray(data.items)
}

function isTtsSpeakAcceptedPayload(payload: unknown): payload is TtsSpeakAcceptedPayload {
  if (!payload || typeof payload !== 'object') return false
  const data = payload as Record<string, unknown>
  return (
    typeof data.plugin_id === 'string' &&
    typeof data.task_id === 'string' &&
    typeof data.stream_url === 'string' &&
    typeof data.status_url === 'string'
  )
}

function isTtsStoppedPayload(payload: unknown): payload is TtsStoppedPayload {
  if (!payload || typeof payload !== 'object') return false
  const data = payload as Record<string, unknown>
  if (typeof data.plugin_id !== 'string') return false
  if (typeof data.stopped !== 'boolean') return false
  if (data.task_id !== undefined && typeof data.task_id !== 'string') return false
  return true
}

function isAssistantRuntimeEventPayload(payload: unknown): payload is AssistantRuntimeEventPayload {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return false
  const data = payload as Record<string, unknown>
  return (
    typeof data.type === 'string' &&
    typeof data.ts_ms === 'number' &&
    Number.isFinite(data.ts_ms) &&
    typeof data.source === 'string' &&
    typeof data.payload === 'object' &&
    data.payload !== null &&
    !Array.isArray(data.payload)
  )
}

const REQUEST_TYPE_MAP: Record<string, string> = {
  describe: IFRAME_UI_AGENT_MESSAGE.SNAPSHOT_REQUEST,
  query: IFRAME_UI_AGENT_MESSAGE.QUERY_REQUEST,
  act: IFRAME_UI_AGENT_MESSAGE.ACTION_REQUEST,
  scroll: IFRAME_UI_AGENT_MESSAGE.SCROLL_REQUEST,
  capabilities_list: IFRAME_UI_AGENT_MESSAGE.CAPABILITIES_LIST_REQUEST,
  capability_invoke: IFRAME_UI_AGENT_MESSAGE.CAPABILITY_INVOKE_REQUEST,
  runtime_refresh: IFRAME_UI_AGENT_MESSAGE.RUNTIME_REFRESH_REQUEST
}

function readEnvTimeoutMs(name: string, fallback: number): number {
  const rawValue = import.meta.env[name]
  if (rawValue === undefined) {
    return fallback
  }
  const parsed = Number(rawValue)
  if (!Number.isFinite(parsed) || parsed < 0) {
    return fallback
  }
  return parsed
}

function toRecord(raw: unknown): Record<string, unknown> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return {}
  }
  return raw as Record<string, unknown>
}

function parseCapabilityInvoke(payload: unknown): CapabilityInvokeRequest | null {
  const record = toRecord(payload)
  const functionName = String(record.function || '').trim()
  if (!functionName) {
    return null
  }
  return {
    functionName,
    payload: toRecord(record.payload),
    options: toRecord(record.options),
  }
}

function parseHostInvoke(payload: unknown): HostInvokeRequest | null {
  const record = toRecord(payload)
  const functionName = String(record.function || '').trim()
  if (!functionName) {
    return null
  }
  return {
    functionName,
    payload: toRecord(record.payload),
    options: toRecord(record.options),
  }
}

export function usePluginUiBridge(options: UiBridgeOptions) {
  let bridge: PluginUiBridgeClient | null = null
  const REQUEST_TIMEOUT_DEFAULT_MS = readEnvTimeoutMs('VITE_PLUGIN_UI_BRIDGE_REQUEST_TIMEOUT_MS', 20_000)
  const REQUEST_TIMEOUT_SESSION_INVOKE_MS = readEnvTimeoutMs(
    'VITE_PLUGIN_UI_BRIDGE_SESSION_INVOKE_TIMEOUT_MS',
    120_000
  )
  const REQUEST_TIMEOUT_SESSION_WAIT_BUFFER_MS = readEnvTimeoutMs(
    'VITE_PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_BUFFER_MS',
    5_000
  )
  let localRequestSeq = 0
  const requestTimeoutStrategy = createBridgeRequestTimeoutStrategy({
    defaultTimeoutMs: REQUEST_TIMEOUT_DEFAULT_MS,
    sessionInvokeTimeoutMs: REQUEST_TIMEOUT_SESSION_INVOKE_MS,
    sessionWaitTimeoutBufferMs: REQUEST_TIMEOUT_SESSION_WAIT_BUFFER_MS
  })

  const postToIframe = (message: Record<string, unknown>) => {
    const frame = options.iframeRef.value?.contentWindow
    if (!frame) return false
    const targetOrigin = options.expectedOrigin.value || '*'
    frame.postMessage(message, targetOrigin)
    return true
  }
  const pendingRequests = createPendingBridgeRequestTracker<Record<string, unknown>>({
    onTimeout: (requestId, pending) => {
      const timeoutResult = {
        ok: false,
        error_code: 'iframe_timeout',
        message: 'plugin iframe response timeout'
      }
      if (pending.source === 'bridge') {
        bridge?.sendResult(requestId, timeoutResult)
        return
      }
      pending.resolve?.(timeoutResult)
    },
    onReplaced: (_requestId, pending) => {
      if (pending.source === 'local') {
        pending.resolve?.({
          ok: false,
          error_code: 'iframe_cancelled',
          message: 'iframe request cancelled by newer request'
        })
      }
    }
  })

  const sendRequestToIframe = (
    requestId: string,
    op: string,
    payload: Record<string, unknown>,
    pluginId: string,
    source: PendingBridgeRequestSource,
    resolve?: (result: Record<string, unknown>) => void
  ) => {
    const type = REQUEST_TYPE_MAP[op]
    if (!type) {
      const unsupportedResult = {
        ok: false,
        error_code: 'unsupported_op',
        message: `unsupported op: ${String(op)}`
      }
      if (source === 'bridge') {
        bridge?.sendResult(requestId, unsupportedResult)
      } else {
        resolve?.(unsupportedResult)
      }
      return false
    }
    const timeoutMs = requestTimeoutStrategy.resolveTimeoutMs(op, payload)
    pendingRequests.schedule({
      requestId,
      source,
      timeoutMs,
      resolve
    })
    const success = postToIframe({
      type,
      pluginId,
      requestId,
      payload
    })
    if (!success) {
      const pending = pendingRequests.finalize(requestId)
      const notReadyResult = {
        ok: false,
        error_code: 'iframe_not_ready',
        message: 'plugin iframe not ready'
      }
      if (source === 'bridge') {
        bridge?.sendResult(requestId, notReadyResult)
      } else {
        pending?.resolve?.(notReadyResult)
      }
      return false
    }
    return true
  }

  const executePluginCapability = async (context: {
    pluginId: string
    invoke: CapabilityInvokeRequest
  }): Promise<Record<string, unknown>> => {
    const requestId = `local_${Date.now()}_${localRequestSeq}`
    localRequestSeq += 1
    return await new Promise<Record<string, unknown>>((resolve) => {
      const payload = {
        function: context.invoke.functionName,
        payload: context.invoke.payload,
        options: context.invoke.options
      }
      sendRequestToIframe(
        requestId,
        'capability_invoke',
        payload,
        context.pluginId,
        'local',
        resolve
      )
    })
  }

  const handleBridgeRequest = async (msg: BridgeRequestMessage) => {
    if (msg.op === 'capability_invoke' && options.onCapabilityInvokeRequest) {
      const invoke = parseCapabilityInvoke(msg.payload)
      if (invoke) {
        try {
          const interceptedResult = await options.onCapabilityInvokeRequest({
            requestId: msg.requestId,
            pluginId: msg.pluginId,
            invoke,
            executePluginCapability: (request) =>
              executePluginCapability({
                pluginId: msg.pluginId,
                invoke: request
              }),
          })
          if (interceptedResult) {
            bridge?.sendResult(msg.requestId, interceptedResult)
            return
          }
        } catch (error) {
          bridge?.sendResult(msg.requestId, {
            ok: false,
            error_code: 'orchestrator_failed',
            message: String(error)
          })
          return
        }
      }
    }
    sendRequestToIframe(
      msg.requestId,
      msg.op,
      msg.payload,
      msg.pluginId,
      'bridge'
    )
  }

  const handleWindowMessage = (event: MessageEvent<Record<string, unknown>>) => {
    if (!event.data || typeof event.data !== 'object') return
    if (options.expectedOrigin.value && event.origin !== options.expectedOrigin.value) return
    const type = String(event.data.type || '')
    const requestId = String(event.data.requestId || '')
    if (UI_AGENT_RESPONSE_TYPES.has(type)) {
      if (!requestId) return
      const pending = pendingRequests.finalize(requestId)
      if (!pending) return
      const result =
        (event.data.result as Record<string, unknown>) ||
        (event.data.payload as Record<string, unknown>) || {
          ok: false,
          error_code: 'invalid_iframe_result',
          message: 'missing result payload'
        }
      if (pending.source === 'bridge') {
        bridge?.sendResult(requestId, result)
      } else {
        pending.resolve?.(result)
      }
      return
    }
    if (type === IFRAME_UI_AGENT_MESSAGE.HOST_INVOKE_REQUEST) {
      if (!requestId) return
      const invoke = parseHostInvoke(event.data.payload)
      if (!invoke || !options.onHostInvokeRequest) {
        postToIframe({
          type: IFRAME_UI_AGENT_MESSAGE.HOST_INVOKE_RESULT,
          pluginId: options.pluginId.value,
          requestId,
          result: {
            ok: false,
            error_code: 'host_invoke_not_supported',
            message: 'host invoke is not available',
          },
        })
        return
      }
      void Promise.resolve(
        options.onHostInvokeRequest({
          requestId,
          pluginId: options.pluginId.value,
          invoke,
        })
      )
        .then((result) => {
          postToIframe({
            type: IFRAME_UI_AGENT_MESSAGE.HOST_INVOKE_RESULT,
            pluginId: options.pluginId.value,
            requestId,
            result,
          })
        })
        .catch((error) => {
          postToIframe({
            type: IFRAME_UI_AGENT_MESSAGE.HOST_INVOKE_RESULT,
            pluginId: options.pluginId.value,
            requestId,
            result: {
              ok: false,
              error_code: 'host_invoke_failed',
              message: String(error),
            },
          })
        })
      return
    }
    if (type === IFRAME_UI_AGENT_MESSAGE.ASSISTANT_RUNTIME_EVENT) {
      if (!isAssistantRuntimeEventPayload(event.data.payload)) {
        logger.warn('[plugin_ui_bridge] ignore invalid assistant_runtime_event payload', {
          pluginId: options.pluginId.value
        })
        return
      }
      logger.info('[plugin_ui_bridge] recv assistant_runtime_event', {
        pluginId: options.pluginId.value,
        eventType: event.data.payload.type,
        source: event.data.payload.source,
        sessionId: event.data.payload.session_id,
        stepId: event.data.payload.step_id,
        payload: event.data.payload.payload
      })
      options.onAssistantRuntimeEvent?.(event.data.payload)
    }
  }

  onMounted(() => {
    bridge = new PluginUiBridgeClient(options.pluginId.value, {
      onRequest: (msg) => {
        void handleBridgeRequest(msg)
      },
      onDisconnect: () => {
        pendingRequests.failAll((pending, requestId) => {
          const disconnectResult = {
            ok: false,
            error_code: 'bridge_disconnected',
            message: 'plugin bridge disconnected'
          }
          if (pending.source === 'bridge') {
            bridge?.sendResult(requestId, disconnectResult)
            return null
          }
          return disconnectResult
        })
      },
      onEvent: (msg) => {
        if (msg.event === BRIDGE_EVENT.CONTEXT_PUSH) {
          if (!isContextPushPayload(msg.payload)) {
            logger.warn('[plugin_ui_bridge] ignore invalid context_push payload', {
              pluginId: options.pluginId.value
            })
            return
          }
          options.onContextPush(msg.payload)
          return
        }
        if (msg.event === BRIDGE_EVENT.TTS_SPEAK_ACCEPTED) {
          if (!isTtsSpeakAcceptedPayload(msg.payload)) {
            logger.warn('[plugin_ui_bridge] ignore invalid tts_speak_accepted payload', {
              pluginId: options.pluginId.value
            })
            return
          }
          logger.info('[plugin_ui_bridge] recv tts_speak_accepted', {
            pluginId: options.pluginId.value,
            taskId: msg.payload.task_id
          })
          options.onTtsSpeakAccepted?.(msg.payload)
          return
        }
        if (msg.event === BRIDGE_EVENT.TTS_STOPPED) {
          if (!isTtsStoppedPayload(msg.payload)) {
            logger.warn('[plugin_ui_bridge] ignore invalid tts_stopped payload', {
              pluginId: options.pluginId.value
            })
            return
          }
          logger.info('[plugin_ui_bridge] recv tts_stopped', {
            pluginId: options.pluginId.value,
            taskId: msg.payload.task_id || ''
          })
          options.onTtsStopped?.(msg.payload)
        }
      }
    })
    bridge.connect()
    window.addEventListener('message', handleWindowMessage)
    logger.info('[plugin_ui_bridge] composable mounted', { pluginId: options.pluginId.value })
  })

  onUnmounted(() => {
    window.removeEventListener('message', handleWindowMessage)
    bridge?.disconnect()
    bridge = null
    pendingRequests.failAll((pending) => {
      if (pending.source === 'local') {
        return {
          ok: false,
          error_code: 'bridge_unmounted',
          message: 'plugin iframe bridge unmounted'
        }
      }
      return null
    })
  })
}
