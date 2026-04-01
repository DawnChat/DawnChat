import { computed } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useAssistantSessionOrchestrator } from '@/features/plugin-dev-workbench/composables/useAssistantSessionOrchestrator'
import type { CapabilityInvokeExecutionContext } from '@/composables/usePluginUiBridge'

const createContext = (
  functionName: string,
  payload: Record<string, unknown>,
  executePluginCapability: CapabilityInvokeExecutionContext['executePluginCapability']
): CapabilityInvokeExecutionContext => {
  return {
    requestId: 'req_1',
    pluginId: 'com.demo.plugin',
    invoke: {
      functionName,
      payload,
      options: {},
    },
    executePluginCapability,
  }
}

const resolvePendingStep = (
  resolveStep: ((value: Record<string, unknown>) => void) | null,
  value: Record<string, unknown>
) => {
  if (typeof resolveStep === 'function') {
    resolveStep(value)
  }
}

describe('useAssistantSessionOrchestrator', () => {
  it('handles session.start and executes step capability', async () => {
    const executePluginCapability = vi.fn(async () => ({
      ok: true,
      data: { status: 'applied' },
    }))
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const result = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              id: 'step-1',
              action: {
                type: 'guide.card.show',
                payload: {
                  card_type: 'word',
                  data: { word: 'sync' },
                },
              },
            },
          ],
        },
        executePluginCapability
      )
    )

    expect(executePluginCapability).toHaveBeenCalledTimes(1)
    expect(result).toEqual(
      expect.objectContaining({
        ok: true,
        data: expect.objectContaining({
          session_id: expect.any(String),
          status: 'running',
          current_step_id: 'step-1',
          completed_steps: 0,
          total_steps: 1,
          progress_percent: 0,
          elapsed_ms: expect.any(Number),
          accepted: true,
        }),
      })
    )
  })

  it('executes multi-step guide session in order', async () => {
    const executePluginCapability = vi.fn(async () => ({
      ok: true,
      data: { status: 'applied' },
    }))
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const startResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              id: 'step-card',
              action: {
                type: 'guide.card.show',
                payload: {
                  card_type: 'word',
                  data: { word: 'sync' },
                },
              },
            },
            {
              id: 'step-narrate',
              action: {
                type: 'guide.narrate',
                payload: {
                  text: 'hello world',
                },
              },
            },
          ],
        },
        executePluginCapability
      )
    )

    await Promise.resolve()

    expect(startResult).toEqual(
      expect.objectContaining({
        ok: true,
      })
    )
    expect(executePluginCapability).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        payload: expect.objectContaining({
          step_id: 'step-card',
          action: expect.objectContaining({
            type: 'guide.card.show',
          }),
        }),
      })
    )
    expect(executePluginCapability).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        payload: expect.objectContaining({
          step_id: 'step-narrate',
          action: expect.objectContaining({
            type: 'guide.narrate',
          }),
        }),
      })
    )
  })

  it('executes view and guide steps in order', async () => {
    const executePluginCapability = vi.fn(async () => ({
      ok: true,
      data: { status: 'applied' },
    }))
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const startResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              id: 'step-view-open',
              action: {
                type: 'view.open',
                payload: {
                  view_id: 'word.main',
                  resource: {
                    resource_type: 'word',
                    data: {
                      word: 'sync',
                    },
                  },
                },
              },
            },
            {
              id: 'step-view-focus',
              action: {
                type: 'view.focus',
                payload: {
                  view_id: 'word.main',
                  anchor: 'word.meaning',
                },
              },
            },
            {
              id: 'step-guide',
              action: {
                type: 'guide.narrate',
                payload: {
                  text: 'hello view runtime',
                },
              },
            },
          ],
        },
        executePluginCapability
      )
    )

    expect(startResult).toEqual(
      expect.objectContaining({
        ok: true,
      })
    )
    await vi.waitFor(() => {
      expect(executePluginCapability).toHaveBeenNthCalledWith(
        1,
        expect.objectContaining({
          payload: expect.objectContaining({
            step_id: 'step-view-open',
            action: expect.objectContaining({
              type: 'view.open',
            }),
          }),
        })
      )
      expect(executePluginCapability).toHaveBeenNthCalledWith(
        2,
        expect.objectContaining({
          payload: expect.objectContaining({
            step_id: 'step-view-focus',
            action: expect.objectContaining({
              type: 'view.focus',
            }),
          }),
        })
      )
      expect(executePluginCapability).toHaveBeenNthCalledWith(
        3,
        expect.objectContaining({
          payload: expect.objectContaining({
            step_id: 'step-guide',
            action: expect.objectContaining({
              type: 'guide.narrate',
            }),
          }),
        })
      )
    })
  })

  it('rejects session.start when active session is running', async () => {
    let resolveStep: ((value: Record<string, unknown>) => void) | null = null
    const executePluginCapability = vi.fn(
      async () =>
        await new Promise<Record<string, unknown>>((resolve) => {
          resolveStep = resolve
        })
    )
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const startPayload = {
      steps: [
        {
          action: {
            type: 'guide.card.show',
            payload: {},
          },
        },
      ],
    }
    const first = await orchestrator.handleCapabilityInvokeRequest(
      createContext('assistant.session.start', startPayload, executePluginCapability)
    )
    const second = await orchestrator.handleCapabilityInvokeRequest(
      createContext('assistant.session.start', startPayload, executePluginCapability)
    )
    const firstData = (first as Record<string, unknown>).data as Record<string, unknown>
    expect(second).toEqual({
      ok: false,
      error_code: 'session_busy',
      message: expect.any(String),
      data: {
        active_session_id: String(firstData.session_id || ''),
      },
    })
    expect(firstData.session_id).toBeTruthy()
    expect(executePluginCapability).toHaveBeenCalledTimes(1)
    resolvePendingStep(resolveStep, {
      ok: true,
      data: { status: 'applied' },
    })
    await vi.waitFor(async () => {
      const status = await orchestrator.handleCapabilityInvokeRequest(
        createContext(
          'assistant.session.status',
          {
            session_id: String(firstData.session_id || ''),
          },
          executePluginCapability
        )
      )
      expect(status).toEqual({
        ok: true,
        data: expect.objectContaining({
          status: 'completed',
        }),
      })
    })
    const third = await orchestrator.handleCapabilityInvokeRequest(
      createContext('assistant.session.start', startPayload, executePluginCapability)
    )
    expect(third).toEqual(
      expect.objectContaining({
        ok: true,
        data: expect.objectContaining({
          status: 'running',
          accepted: true,
        }),
      })
    )
  })

  it('returns running then completed status by session_id', async () => {
    let resolveStep: ((value: Record<string, unknown>) => void) | null = null
    const executePluginCapability = vi.fn(
      async () =>
        await new Promise<Record<string, unknown>>((resolve) => {
          resolveStep = resolve
        })
    )
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const startResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              action: {
                type: 'guide.card.show',
                payload: {},
              },
            },
          ],
        },
        executePluginCapability
      )
    )
    const sessionId = String(
      ((startResult as Record<string, unknown>).data as Record<string, unknown>).session_id || ''
    )
    const statusResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.status',
        {
          session_id: sessionId,
        },
        executePluginCapability
      )
    )
    expect(statusResult).toEqual({
      ok: true,
      data: expect.objectContaining({
        session_id: sessionId,
        status: 'running',
        current_step_index: 0,
        current_step_id: 'step-1',
        completed_steps: 0,
        progress_percent: 0,
        elapsed_ms: expect.any(Number),
      }),
    })
    resolvePendingStep(resolveStep, {
      ok: true,
      data: { status: 'applied' },
    })
    await vi.waitFor(async () => {
      const completedStatus = await orchestrator.handleCapabilityInvokeRequest(
        createContext(
          'assistant.session.status',
          {
            session_id: sessionId,
          },
          executePluginCapability
        )
      )
      expect(completedStatus).toEqual({
        ok: true,
        data: expect.objectContaining({
          session_id: sessionId,
          status: 'completed',
          completed_steps: 1,
          progress_percent: 100,
          ended_at_ms: expect.any(Number),
        }),
      })
    })
  })

  it('passes timeout_ms to plugin step executor', async () => {
    const executePluginCapability = vi.fn(async () => ({
      ok: true,
      data: { status: 'applied' },
    }))
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const sessionResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              action: {
                type: 'guide.card.show',
                payload: {},
              },
              timeout_ms: 45000,
            },
          ],
        },
        executePluginCapability
      )
    )
    expect(sessionResult).toEqual(
      expect.objectContaining({
        ok: true,
      })
    )
    expect(executePluginCapability).toHaveBeenCalledWith(
      expect.objectContaining({
        functionName: 'assistant.session_step_execute',
        payload: expect.objectContaining({
          step_index: 0,
          total_steps: 1,
          timeout_ms: 45000,
        }),
      })
    )
  })

  it('moves session to failed when step execution returns error', async () => {
    const executePluginCapability = vi.fn(async () => ({
      ok: false,
      error_code: 'step_failed',
      message: 'boom',
    }))
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const startResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              action: {
                type: 'guide.card.show',
                payload: {},
              },
            },
          ],
        },
        executePluginCapability
      )
    )
    const sessionId = String(
      ((startResult as Record<string, unknown>).data as Record<string, unknown>).session_id || ''
    )
    await Promise.resolve()
    const statusResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.status',
        {
          session_id: sessionId,
        },
        executePluginCapability
      )
    )
    expect(statusResult).toEqual({
      ok: true,
      data: expect.objectContaining({
        session_id: sessionId,
        status: 'failed',
        last_error: 'boom',
        last_error_code: 'step_failed',
      }),
    })
  })

  it('stops running session and returns cancelled status', async () => {
    let resolveStep: ((value: Record<string, unknown>) => void) | null = null
    const executePluginCapability = vi.fn(async (invoke) => {
      if (invoke.functionName === 'assistant.session_step_execute') {
        return await new Promise<Record<string, unknown>>((resolve) => {
          resolveStep = resolve
        })
      }
      if (invoke.functionName === 'assistant.session_step_cancel') {
        return {
          ok: true,
          data: {
            session_id: 'sess_cancel',
            step_id: 'step-1',
            active_step_found: true,
            cancel_requested: true,
          },
        }
      }
      return {
        ok: false,
        error_code: 'unsupported',
        message: 'unsupported',
      }
    })
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const startResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              action: {
                type: 'guide.card.show',
                payload: {},
              },
            },
          ],
        },
        executePluginCapability
      )
    )
    const sessionId = String(
      ((startResult as Record<string, unknown>).data as Record<string, unknown>).session_id || ''
    )
    const stopResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.stop',
        {
          session_id: sessionId,
          reason: 'agent_interrupted',
        },
        executePluginCapability
      )
    )
    expect(stopResult).toEqual({
      ok: true,
      data: expect.objectContaining({
        session_id: sessionId,
        status: 'cancelled',
        stopped: true,
        already_terminal: false,
        cancel_propagated: true,
        cancelled_step_id: 'step-1',
        last_error_code: 'session_stopped',
      }),
    })
    const blockedRestart = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              action: {
                type: 'guide.card.show',
                payload: {},
              },
            },
          ],
        },
        executePluginCapability
      )
    )
    expect(blockedRestart).toEqual({
      ok: false,
      error_code: 'session_busy',
      message: expect.any(String),
      data: {
        active_session_id: sessionId,
      },
    })
    resolvePendingStep(resolveStep, {
      ok: false,
      error_code: 'step_cancelled',
      message: 'guide narration cancelled',
    })
    await vi.waitFor(async () => {
      const statusResult = await orchestrator.handleCapabilityInvokeRequest(
        createContext(
          'assistant.session.status',
          {
            session_id: sessionId,
          },
          executePluginCapability
        )
      )
      expect(statusResult).toEqual({
        ok: true,
        data: expect.objectContaining({
          session_id: sessionId,
          status: 'cancelled',
          last_error_code: 'session_stopped',
        }),
      })
    })
    const restartCapability = vi.fn(async () => ({
      ok: true,
      data: { status: 'applied' },
    }))
    await vi.waitFor(async () => {
      const nextStart = await orchestrator.handleCapabilityInvokeRequest(
        createContext(
          'assistant.session.start',
          {
            steps: [
              {
                action: {
                  type: 'guide.card.show',
                  payload: {},
                },
              },
            ],
          },
          restartCapability
        )
      )
      expect(nextStart).toEqual(
        expect.objectContaining({
          ok: true,
          data: expect.objectContaining({
            status: 'running',
          }),
        })
      )
    })
  })

  it('waits for session terminal completion without polling status', async () => {
    let resolveStep: ((value: Record<string, unknown>) => void) | null = null
    const executePluginCapability = vi.fn(async (invoke) => {
      if (invoke.functionName === 'assistant.session_step_execute') {
        return await new Promise<Record<string, unknown>>((resolve) => {
          resolveStep = resolve
        })
      }
      return {
        ok: false,
        error_code: 'unsupported',
        message: 'unsupported',
      }
    })
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const startResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              action: {
                type: 'guide.card.show',
                payload: {},
              },
            },
          ],
        },
        executePluginCapability
      )
    )
    const sessionId = String(
      ((startResult as Record<string, unknown>).data as Record<string, unknown>).session_id || ''
    )
    const waitPromise = orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.wait',
        {
          session_id: sessionId,
        },
        executePluginCapability
      )
    )
    resolvePendingStep(resolveStep, {
      ok: true,
      data: { status: 'applied' },
    })
    await expect(waitPromise).resolves.toEqual({
      ok: true,
      data: expect.objectContaining({
        session_id: sessionId,
        wait_for: 'session_terminal',
        status: 'terminal',
        session_status: expect.objectContaining({
          status: 'completed',
        }),
      }),
    })
  })

  it('wakes session.wait when the running session is stopped', async () => {
    let resolveStep: ((value: Record<string, unknown>) => void) | null = null
    const executePluginCapability = vi.fn(async (invoke) => {
      if (invoke.functionName === 'assistant.session_step_execute') {
        return await new Promise<Record<string, unknown>>((resolve) => {
          resolveStep = resolve
        })
      }
      if (invoke.functionName === 'assistant.session_step_cancel') {
        return {
          ok: true,
          data: {
            session_id: 'sess_cancel',
            step_id: 'step-1',
            active_step_found: true,
            cancel_requested: true,
          },
        }
      }
      return {
        ok: false,
        error_code: 'unsupported',
        message: 'unsupported',
      }
    })
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const startResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              action: {
                type: 'guide.card.show',
                payload: {},
              },
            },
          ],
        },
        executePluginCapability
      )
    )
    const sessionId = String(
      ((startResult as Record<string, unknown>).data as Record<string, unknown>).session_id || ''
    )
    const waitPromise = orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.wait',
        {
          session_id: sessionId,
        },
        executePluginCapability
      )
    )
    await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.stop',
        {
          session_id: sessionId,
          reason: 'agent_interrupted',
        },
        executePluginCapability
      )
    )
    await expect(waitPromise).resolves.toEqual({
      ok: true,
      data: expect.objectContaining({
        session_id: sessionId,
        wait_for: 'session_terminal',
        status: 'terminal',
        session_status: expect.objectContaining({
          status: 'cancelled',
        }),
      }),
    })
    resolvePendingStep(resolveStep, {
      ok: false,
      error_code: 'step_cancelled',
      message: 'guide narration cancelled',
    })
  })

  it('waits for runtime events through assistant.runtime.event.peek', async () => {
    let resolveStep: ((value: Record<string, unknown>) => void) | null = null
    const executePluginCapability = vi.fn(async (invoke) => {
      if (invoke.functionName === 'assistant.session_step_execute') {
        return await new Promise<Record<string, unknown>>((resolve) => {
          resolveStep = resolve
        })
      }
      if (invoke.functionName === 'assistant.runtime.event.peek') {
        return {
          ok: true,
          data: {
            latest_seq: 5,
            events: [
              {
                seq: 5,
                type: 'assistant.guide.quiz.submitted',
                session_id: 'sess-runtime',
                payload: {
                  quiz_id: 'quiz-1',
                  selected_option: 'A',
                },
              },
            ],
          },
        }
      }
      return {
        ok: false,
        error_code: 'unsupported',
        message: 'unsupported',
      }
    })
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const startResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              action: {
                type: 'guide.card.show',
                payload: {},
              },
            },
          ],
        },
        executePluginCapability
      )
    )
    const sessionId = String(
      ((startResult as Record<string, unknown>).data as Record<string, unknown>).session_id || ''
    )
    const waitResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.wait',
        {
          session_id: sessionId,
          wait_for: 'runtime_event',
          event_types: ['assistant.guide.quiz.submitted'],
          match: {
            quiz_id: 'quiz-1',
          },
          since_seq: 3,
        },
        executePluginCapability
      )
    )
    expect(waitResult).toEqual({
      ok: true,
      data: expect.objectContaining({
        session_id: sessionId,
        wait_for: 'runtime_event',
        status: 'matched',
        latest_seq: 5,
        matched_event: expect.objectContaining({
          type: 'assistant.guide.quiz.submitted',
        }),
      }),
    })
    expect(executePluginCapability).toHaveBeenCalledWith(
      expect.objectContaining({
        functionName: 'assistant.runtime.event.peek',
        payload: expect.objectContaining({
          session_id: sessionId,
          since_seq: 3,
          event_types: ['assistant.guide.quiz.submitted'],
          match: {
            quiz_id: 'quiz-1',
          },
        }),
      })
    )
    resolvePendingStep(resolveStep, {
      ok: true,
      data: { status: 'applied' },
    })
  })

  it('returns timed_out when runtime events do not arrive before timeout', async () => {
    vi.useFakeTimers()
    let resolveStep: ((value: Record<string, unknown>) => void) | null = null
    const executePluginCapability = vi.fn(async (invoke) => {
      if (invoke.functionName === 'assistant.session_step_execute') {
        return await new Promise<Record<string, unknown>>((resolve) => {
          resolveStep = resolve
        })
      }
      if (invoke.functionName === 'assistant.runtime.event.peek') {
        return {
          ok: true,
          data: {
            latest_seq: 0,
            events: [],
          },
        }
      }
      return {
        ok: false,
        error_code: 'unsupported',
        message: 'unsupported',
      }
    })
    const orchestrator = useAssistantSessionOrchestrator({
      pluginId: computed(() => 'com.demo.plugin'),
    })
    const startResult = await orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.start',
        {
          steps: [
            {
              action: {
                type: 'guide.card.show',
                payload: {},
              },
            },
          ],
        },
        executePluginCapability
      )
    )
    const sessionId = String(
      ((startResult as Record<string, unknown>).data as Record<string, unknown>).session_id || ''
    )
    const waitPromise = orchestrator.handleCapabilityInvokeRequest(
      createContext(
        'assistant.session.wait',
        {
          session_id: sessionId,
          wait_for: 'runtime_event',
          event_types: ['assistant.guide.quiz.submitted'],
          timeout_ms: 400,
        },
        executePluginCapability
      )
    )
    await vi.advanceTimersByTimeAsync(600)
    await expect(waitPromise).resolves.toEqual({
      ok: true,
      data: expect.objectContaining({
        session_id: sessionId,
        wait_for: 'runtime_event',
        status: 'timed_out',
        latest_seq: 0,
      }),
    })
    resolvePendingStep(resolveStep, {
      ok: true,
      data: { status: 'applied' },
    })
    vi.useRealTimers()
  })
})
