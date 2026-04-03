import { describe, expect, it, vi } from 'vitest'

import { createAssistantRuntimeEventWaitRegistry } from '@/features/plugin-dev-workbench/composables/assistantRuntimeEventWaitRegistry'

describe('assistantRuntimeEventWaitRegistry', () => {
  it('matches a realtime event by session, type, and payload', async () => {
    const registry = createAssistantRuntimeEventWaitRegistry()
    const waiting = registry.startWait({
      sessionId: 'sess-1',
      eventTypes: ['assistant.guide.quiz.submitted'],
      match: {
        quiz_id: 'quiz-1',
      },
      timeoutMs: 1000,
    })

    registry.handleEvent({
      type: 'assistant.guide.quiz.submitted',
      ts_ms: 10,
      source: 'guide',
      session_id: 'sess-1',
      payload: {
        quiz_id: 'quiz-1',
        selected_option: 'A',
      },
    })

    await expect(waiting.promise).resolves.toEqual(
      expect.objectContaining({
        type: 'assistant.guide.quiz.submitted',
        session_id: 'sess-1',
      })
    )
  })

  it('times out when no matching event arrives', async () => {
    vi.useFakeTimers()
    const registry = createAssistantRuntimeEventWaitRegistry()
    const waiting = registry.startWait({
      sessionId: 'sess-1',
      eventTypes: ['assistant.guide.quiz.submitted'],
      match: {},
      timeoutMs: 100,
    })

    const timeoutExpectation = expect(waiting.promise).rejects.toThrow('wait_timeout')
    await vi.advanceTimersByTimeAsync(120)
    await timeoutExpectation
    vi.useRealTimers()
  })

  it('cancels all waiters on dispose', async () => {
    const registry = createAssistantRuntimeEventWaitRegistry()
    const waiting = registry.startWait({
      sessionId: 'sess-1',
      eventTypes: ['assistant.guide.confirm.responded'],
      match: {},
      timeoutMs: 1000,
    })

    registry.dispose()

    await expect(waiting.promise).rejects.toThrow('wait_cancelled')
  })
})
