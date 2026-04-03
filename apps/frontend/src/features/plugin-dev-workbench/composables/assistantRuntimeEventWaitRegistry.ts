import type { AssistantSessionRuntimeEvent } from '@/features/plugin-dev-workbench/composables/assistantRuntimeEventTypes'

export interface AssistantRuntimeEventWaitRequest {
  sessionId?: string
  eventTypes: string[]
  match: Record<string, unknown>
  timeoutMs: number
}

interface RuntimeEventWaiter {
  sessionId?: string
  eventTypes: string[]
  match: Record<string, unknown>
  settled: boolean
  timer: number
  resolve: (event: AssistantSessionRuntimeEvent) => void
  reject: (error: Error) => void
}

function matchesRuntimeEvent(
  event: AssistantSessionRuntimeEvent,
  waitRequest: Pick<AssistantRuntimeEventWaitRequest, 'sessionId' | 'eventTypes' | 'match'>
): boolean {
  if (waitRequest.sessionId && event.sessionId && event.sessionId !== waitRequest.sessionId) {
    return false
  }
  if (waitRequest.eventTypes.length > 0 && !waitRequest.eventTypes.includes(event.type)) {
    return false
  }
  return Object.entries(waitRequest.match).every(([key, value]) => event.payload[key] === value)
}

export function createAssistantRuntimeEventWaitRegistry() {
  const waiters = new Set<RuntimeEventWaiter>()

  const cleanupWaiter = (waiter: RuntimeEventWaiter) => {
    window.clearTimeout(waiter.timer)
    waiters.delete(waiter)
  }

  const settleWaiter = (
    waiter: RuntimeEventWaiter,
    settle: 'resolve' | 'reject',
    value: AssistantSessionRuntimeEvent | Error
  ) => {
    if (waiter.settled) {
      return
    }
    waiter.settled = true
    cleanupWaiter(waiter)
    if (settle === 'resolve') {
      waiter.resolve(value as AssistantSessionRuntimeEvent)
      return
    }
    waiter.reject(value as Error)
  }

  const startWait = (request: AssistantRuntimeEventWaitRequest) => {
    let waiter: RuntimeEventWaiter
    const promise = new Promise<AssistantSessionRuntimeEvent>((resolve, reject) => {
      waiter = {
        sessionId: request.sessionId,
        eventTypes: request.eventTypes,
        match: request.match,
        settled: false,
        timer: window.setTimeout(() => {
          settleWaiter(waiter, 'reject', new Error('wait_timeout'))
        }, request.timeoutMs),
        resolve,
        reject,
      }
      waiters.add(waiter)
    })
    return {
      promise,
      cancel: () => {
        settleWaiter(waiter!, 'reject', new Error('wait_cancelled'))
      },
    }
  }

  const handleEvent = (event: AssistantSessionRuntimeEvent) => {
    for (const waiter of Array.from(waiters)) {
      if (!matchesRuntimeEvent(event, waiter)) {
        continue
      }
      settleWaiter(waiter, 'resolve', event)
    }
  }

  const dispose = () => {
    for (const waiter of Array.from(waiters)) {
      settleWaiter(waiter, 'reject', new Error('wait_cancelled'))
    }
  }

  return {
    startWait,
    handleEvent,
    dispose,
  }
}
