export interface AssistantSessionTerminalWaitState {
  sessionId: string
}

type TerminalWaiter<TState extends AssistantSessionTerminalWaitState> = (state: TState) => void

export function createAssistantSessionTerminalWaitRegistry<
  TState extends AssistantSessionTerminalWaitState,
>() {
  const waitersBySession = new Map<string, Set<TerminalWaiter<TState>>>()

  const addWaiter = (sessionId: string, waiter: TerminalWaiter<TState>) => {
    const waiters = waitersBySession.get(sessionId) || new Set<TerminalWaiter<TState>>()
    waiters.add(waiter)
    waitersBySession.set(sessionId, waiters)
    return () => {
      const currentWaiters = waitersBySession.get(sessionId)
      if (!currentWaiters) {
        return
      }
      currentWaiters.delete(waiter)
      if (currentWaiters.size === 0) {
        waitersBySession.delete(sessionId)
      }
    }
  }

  const notify = (state: TState) => {
    const waiters = waitersBySession.get(state.sessionId)
    if (!waiters || waiters.size === 0) {
      return
    }
    waitersBySession.delete(state.sessionId)
    for (const waiter of waiters) {
      waiter(state)
    }
  }

  const dispose = () => {
    waitersBySession.clear()
  }

  return {
    addWaiter,
    notify,
    dispose,
  }
}
