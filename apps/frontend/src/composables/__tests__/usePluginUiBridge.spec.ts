import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { IFRAME_UI_AGENT_MESSAGE } from '@dawnchat/host-orchestration-sdk/assistant-client'

import { usePluginUiBridge } from '../usePluginUiBridge'

type BridgeHandlers = {
  onRequest: (msg: any) => void
  onEvent?: (msg: any) => void
  onDisconnect?: () => void
}

type BridgeClientStubInstance = {
  pluginId: string
  handlers: BridgeHandlers
  sentResults: Array<{ requestId: string; result: Record<string, unknown> }>
}

const bridgeClientMockState = vi.hoisted(() => ({
  instances: [] as BridgeClientStubInstance[]
}))

vi.mock('../../services/plugin-ui-bridge/bridgeClient', () => {
  class PluginUiBridgeClient {
    readonly pluginId: string
    readonly handlers: BridgeHandlers
    sentResults: Array<{ requestId: string; result: Record<string, unknown> }> = []

    constructor(pluginId: string, handlers: BridgeHandlers) {
      this.pluginId = pluginId
      this.handlers = handlers
      bridgeClientMockState.instances.push(this)
    }

    connect() {}
    disconnect() {}

    sendResult(requestId: string, result: Record<string, unknown>) {
      this.sentResults.push({ requestId, result })
    }
  }
  return { PluginUiBridgeClient }
})

vi.mock('../../utils/logger', () => ({
  logger: {
    info: vi.fn(),
    warn: vi.fn()
  }
}))

describe('usePluginUiBridge', () => {
  beforeEach(() => {
    bridgeClientMockState.instances = []
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('forwards request to iframe and sends response back', async () => {
    const postMessage = vi.fn()
    const TestComp = defineComponent({
      setup() {
        const frameRef = ref({
          contentWindow: {
            postMessage
          }
        } as unknown as HTMLIFrameElement)
        usePluginUiBridge({
          pluginId: ref('plugin.demo') as any,
          iframeRef: frameRef,
          expectedOrigin: ref('http://plugin.local') as any,
          onContextPush: vi.fn()
        })
        return () => null
      }
    })
    mount(TestComp)

    const client = bridgeClientMockState.instances[0]
    client.handlers.onRequest({
      type: 'bridge.request',
      requestId: 'req_1',
      pluginId: 'plugin.demo',
      op: 'describe',
      payload: { max_nodes: 10 }
    })

    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: IFRAME_UI_AGENT_MESSAGE.SNAPSHOT_REQUEST, requestId: 'req_1' }),
      'http://plugin.local'
    )

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'http://plugin.local',
        data: {
          type: IFRAME_UI_AGENT_MESSAGE.SNAPSHOT_RESPONSE,
          requestId: 'req_1',
          result: { ok: true, data: { nodes: [] } }
        }
      })
    )

    expect(client.sentResults[0]).toEqual({
      requestId: 'req_1',
      result: { ok: true, data: { nodes: [] } }
    })
  })

  it('returns timeout error when iframe does not respond', async () => {
    const TestComp = defineComponent({
      setup() {
        const frameRef = ref({
          contentWindow: {
            postMessage: vi.fn()
          }
        } as unknown as HTMLIFrameElement)
        usePluginUiBridge({
          pluginId: ref('plugin.demo') as any,
          iframeRef: frameRef,
          expectedOrigin: ref('http://plugin.local') as any,
          onContextPush: vi.fn()
        })
        return () => null
      }
    })
    mount(TestComp)

    const client = bridgeClientMockState.instances[0]
    client.handlers.onRequest({
      type: 'bridge.request',
      requestId: 'req_timeout',
      pluginId: 'plugin.demo',
      op: 'describe',
      payload: {}
    })

    vi.advanceTimersByTime(20_001)
    expect(client.sentResults[0].requestId).toBe('req_timeout')
    expect(client.sentResults[0].result).toEqual(
      expect.objectContaining({ ok: false, error_code: 'iframe_timeout' })
    )
  })

  it('uses extended timeout for assistant.session step invoke requests', async () => {
    const TestComp = defineComponent({
      setup() {
        const frameRef = ref({
          contentWindow: {
            postMessage: vi.fn()
          }
        } as unknown as HTMLIFrameElement)
        usePluginUiBridge({
          pluginId: ref('plugin.demo') as any,
          iframeRef: frameRef,
          expectedOrigin: ref('http://plugin.local') as any,
          onContextPush: vi.fn()
        })
        return () => null
      }
    })
    mount(TestComp)

    const client = bridgeClientMockState.instances[0]
    client.handlers.onRequest({
      type: 'bridge.request',
      requestId: 'req_session_step_timeout',
      pluginId: 'plugin.demo',
      op: 'capability_invoke',
      payload: {
        function: 'assistant.session_step_execute',
        payload: {
          session_id: 'sess_1',
          action: {
            type: 'guide.narrate',
            payload: {
              text: 'long narration'
            }
          }
        },
        options: {}
      }
    })

    vi.advanceTimersByTime(20_001)
    expect(client.sentResults).toHaveLength(0)

    vi.advanceTimersByTime(100_000)
    expect(client.sentResults).toHaveLength(1)
    expect(client.sentResults[0]).toEqual({
      requestId: 'req_session_step_timeout',
      result: expect.objectContaining({
        ok: false,
        error_code: 'iframe_timeout'
      })
    })
  })

  it('keeps assistant.event.wait alive until requested timeout plus buffer', async () => {
    const TestComp = defineComponent({
      setup() {
        const frameRef = ref({
          contentWindow: {
            postMessage: vi.fn()
          }
        } as unknown as HTMLIFrameElement)
        usePluginUiBridge({
          pluginId: ref('plugin.demo') as any,
          iframeRef: frameRef,
          expectedOrigin: ref('http://plugin.local') as any,
          onContextPush: vi.fn()
        })
        return () => null
      }
    })
    mount(TestComp)

    const client = bridgeClientMockState.instances[0]
    client.handlers.onRequest({
      type: 'bridge.request',
      requestId: 'req_event_wait_timeout',
      pluginId: 'plugin.demo',
      op: 'capability_invoke',
      payload: {
        function: 'assistant.event.wait',
        payload: {
          event_types: ['assistant.guide.quiz.submitted'],
          timeout_ms: 130_000
        },
        options: {}
      }
    })

    vi.advanceTimersByTime(130_001)
    expect(client.sentResults).toHaveLength(0)

    vi.advanceTimersByTime(5_000)
    expect(client.sentResults).toHaveLength(1)
    expect(client.sentResults[0]).toEqual({
      requestId: 'req_event_wait_timeout',
      result: expect.objectContaining({
        ok: false,
        error_code: 'iframe_timeout'
      })
    })
  })

  it('forwards scroll op to dedicated iframe message type', async () => {
    const postMessage = vi.fn()
    const TestComp = defineComponent({
      setup() {
        const frameRef = ref({
          contentWindow: {
            postMessage
          }
        } as unknown as HTMLIFrameElement)
        usePluginUiBridge({
          pluginId: ref('plugin.demo') as any,
          iframeRef: frameRef,
          expectedOrigin: ref('http://plugin.local') as any,
          onContextPush: vi.fn()
        })
        return () => null
      }
    })
    mount(TestComp)

    const client = bridgeClientMockState.instances[0]
    client.handlers.onRequest({
      type: 'bridge.request',
      requestId: 'req_scroll',
      pluginId: 'plugin.demo',
      op: 'scroll',
      payload: { direction: 'bottom' }
    })

    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: IFRAME_UI_AGENT_MESSAGE.SCROLL_REQUEST, requestId: 'req_scroll' }),
      'http://plugin.local'
    )

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'http://plugin.local',
        data: {
          type: IFRAME_UI_AGENT_MESSAGE.SCROLL_RESULT,
          requestId: 'req_scroll',
          result: { ok: true, data: { y: 123 } }
        }
      })
    )

    expect(client.sentResults[0]).toEqual({
      requestId: 'req_scroll',
      result: { ok: true, data: { y: 123 } }
    })
  })

  it('dispatches tts events to callbacks', async () => {
    const onTtsSpeakAccepted = vi.fn()
    const onTtsStopped = vi.fn()
    const TestComp = defineComponent({
      setup() {
        const frameRef = ref({
          contentWindow: {
            postMessage: vi.fn()
          }
        } as unknown as HTMLIFrameElement)
        usePluginUiBridge({
          pluginId: ref('plugin.demo') as any,
          iframeRef: frameRef,
          expectedOrigin: ref('http://plugin.local') as any,
          onContextPush: vi.fn(),
          onTtsSpeakAccepted,
          onTtsStopped
        })
        return () => null
      }
    })
    mount(TestComp)
    const client = bridgeClientMockState.instances[0]
    client.handlers.onEvent?.({
      type: 'bridge.event',
      event: 'tts_speak_accepted',
      pluginId: 'plugin.demo',
      payload: {
        plugin_id: 'plugin.demo',
        task_id: 'task-1',
        stream_url: '/api/tts/stream/task-1',
        status_url: '/api/tts/tasks/task-1'
      }
    })
    client.handlers.onEvent?.({
      type: 'bridge.event',
      event: 'tts_stopped',
      pluginId: 'plugin.demo',
      payload: {
        plugin_id: 'plugin.demo',
        task_id: 'task-1',
        stopped: true
      }
    })
    expect(onTtsSpeakAccepted).toHaveBeenCalledTimes(1)
    expect(onTtsStopped).toHaveBeenCalledTimes(1)
  })

  it('allows orchestrator to intercept capability_invoke request', async () => {
    const postMessage = vi.fn()
    const TestComp = defineComponent({
      setup() {
        const frameRef = ref({
          contentWindow: {
            postMessage
          }
        } as unknown as HTMLIFrameElement)
        usePluginUiBridge({
          pluginId: ref('plugin.demo') as any,
          iframeRef: frameRef,
          expectedOrigin: ref('http://plugin.local') as any,
          onContextPush: vi.fn(),
          onCapabilityInvokeRequest: async (context) => {
            if (context.invoke.functionName !== 'assistant.session.status') {
              return null
            }
            return {
              ok: true,
              data: {
                session_id: 'sess_1',
                status: 'completed'
              }
            }
          }
        })
        return () => null
      }
    })
    mount(TestComp)
    const client = bridgeClientMockState.instances[0]
    client.handlers.onRequest({
      type: 'bridge.request',
      requestId: 'req_session_status',
      pluginId: 'plugin.demo',
      op: 'capability_invoke',
      payload: {
        function: 'assistant.session.status',
        payload: { session_id: 'sess_1' },
        options: {}
      }
    })
    await Promise.resolve()
    expect(postMessage).not.toHaveBeenCalled()
    expect(client.sentResults[0]).toEqual({
      requestId: 'req_session_status',
      result: {
        ok: true,
        data: {
          session_id: 'sess_1',
          status: 'completed'
        }
      }
    })
  })

  it('supports orchestrator executing plugin capability via local invoke', async () => {
    const postMessage = vi.fn((message: Record<string, unknown>) => {
      if (message.type !== IFRAME_UI_AGENT_MESSAGE.CAPABILITY_INVOKE_REQUEST) {
        return
      }
      const payload = message.payload as Record<string, unknown>
      if (String(payload.function || '') !== 'assistant.session_step_execute') {
        return
      }
      window.dispatchEvent(
        new MessageEvent('message', {
          origin: 'http://plugin.local',
          data: {
            type: IFRAME_UI_AGENT_MESSAGE.CAPABILITY_INVOKE_RESULT,
            requestId: message.requestId,
            result: { ok: true, data: { status: 'applied' } }
          }
        })
      )
    })
    const TestComp = defineComponent({
      setup() {
        const frameRef = ref({
          contentWindow: {
            postMessage
          }
        } as unknown as HTMLIFrameElement)
        usePluginUiBridge({
          pluginId: ref('plugin.demo') as any,
          iframeRef: frameRef,
          expectedOrigin: ref('http://plugin.local') as any,
          onContextPush: vi.fn(),
          onCapabilityInvokeRequest: async (context) => {
            if (context.invoke.functionName !== 'assistant.session.start') {
              return null
            }
            const stepResult = await context.executePluginCapability({
              functionName: 'assistant.session_step_execute',
              payload: {
                action: {
                  type: 'card.show',
                  payload: {
                    card_type: 'word',
                    data: {}
                  }
                }
              },
              options: {}
            })
            return {
              ok: true,
              data: {
                accepted: Boolean(stepResult.ok)
              }
            }
          }
        })
        return () => null
      }
    })
    mount(TestComp)
    const client = bridgeClientMockState.instances[0]
    client.handlers.onRequest({
      type: 'bridge.request',
      requestId: 'req_session_start',
      pluginId: 'plugin.demo',
      op: 'capability_invoke',
      payload: {
        function: 'assistant.session.start',
        payload: { steps: [] },
        options: {}
      }
    })
    await Promise.resolve()
    await Promise.resolve()
    await vi.waitFor(() => {
      expect(client.sentResults.length).toBe(1)
    })
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: IFRAME_UI_AGENT_MESSAGE.CAPABILITY_INVOKE_REQUEST
      }),
      'http://plugin.local'
    )
    expect(client.sentResults[0]).toEqual({
      requestId: 'req_session_start',
      result: {
        ok: true,
        data: {
          accepted: true
        }
      }
    })
  })

  it('handles host invoke request from iframe and returns host result', async () => {
    const postMessage = vi.fn()
    const TestComp = defineComponent({
      setup() {
        const frameRef = ref({
          contentWindow: {
            postMessage
          }
        } as unknown as HTMLIFrameElement)
        usePluginUiBridge({
          pluginId: ref('plugin.demo') as any,
          iframeRef: frameRef,
          expectedOrigin: ref('http://plugin.local') as any,
          onContextPush: vi.fn(),
          onHostInvokeRequest: async (context) => {
            if (context.invoke.functionName !== 'dawnchat.host.voice.status') {
              return { ok: false, error_code: 'unsupported', message: 'unsupported' }
            }
            return {
              ok: true,
              data: {
                status: 'completed',
                task_id: 'task-1'
              }
            }
          }
        })
        return () => null
      }
    })
    mount(TestComp)

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'http://plugin.local',
        data: {
          type: IFRAME_UI_AGENT_MESSAGE.HOST_INVOKE_REQUEST,
          requestId: 'host_req_1',
          payload: {
            function: 'dawnchat.host.voice.status',
            payload: { task_id: 'task-1' },
            options: {}
          }
        }
      })
    )

    await Promise.resolve()

    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: IFRAME_UI_AGENT_MESSAGE.HOST_INVOKE_RESULT,
        requestId: 'host_req_1',
        result: expect.objectContaining({
          ok: true,
          data: expect.objectContaining({
            task_id: 'task-1'
          })
        })
      }),
      'http://plugin.local'
    )
  })

  it('dispatches assistant runtime events from iframe to host callback', async () => {
    const onAssistantRuntimeEvent = vi.fn()
    const TestComp = defineComponent({
      setup() {
        const frameRef = ref({
          contentWindow: {
            postMessage: vi.fn()
          }
        } as unknown as HTMLIFrameElement)
        usePluginUiBridge({
          pluginId: ref('plugin.demo') as any,
          iframeRef: frameRef,
          expectedOrigin: ref('http://plugin.local') as any,
          onContextPush: vi.fn(),
          onAssistantRuntimeEvent
        })
        return () => null
      }
    })
    mount(TestComp)

    window.dispatchEvent(
      new MessageEvent('message', {
        origin: 'http://plugin.local',
        data: {
          type: IFRAME_UI_AGENT_MESSAGE.ASSISTANT_RUNTIME_EVENT,
          payload: {
            type: 'assistant.game.tictactoe.cell_selected',
            ts_ms: 123,
            source: 'view',
            payload: {
              resource_id: 'tictactoe:neon-grid',
              move_index: 12,
              row: 2,
              col: 2,
              player: 'X'
            }
          }
        }
      })
    )

    expect(onAssistantRuntimeEvent).toHaveBeenCalledWith({
      type: 'assistant.game.tictactoe.cell_selected',
      ts_ms: 123,
      source: 'view',
      payload: {
        resource_id: 'tictactoe:neon-grid',
        move_index: 12,
        row: 2,
        col: 2,
        player: 'X'
      }
    })
  })
})
