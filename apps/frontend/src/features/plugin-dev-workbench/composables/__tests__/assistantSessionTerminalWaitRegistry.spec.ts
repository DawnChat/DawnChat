import { describe, expect, it, vi } from 'vitest'

import { createAssistantSessionTerminalWaitRegistry } from '@/features/plugin-dev-workbench/composables/assistantSessionTerminalWaitRegistry'

describe('assistantSessionTerminalWaitRegistry', () => {
  it('notifies waiters for the matching session', () => {
    const registry = createAssistantSessionTerminalWaitRegistry<{ sessionId: string; status: string }>()
    const waiter = vi.fn()

    registry.addWaiter('sess-1', waiter)
    registry.notify({
      sessionId: 'sess-1',
      status: 'completed',
    })

    expect(waiter).toHaveBeenCalledWith({
      sessionId: 'sess-1',
      status: 'completed',
    })
  })

  it('removes waiter after unsubscribe', () => {
    const registry = createAssistantSessionTerminalWaitRegistry<{ sessionId: string; status: string }>()
    const waiter = vi.fn()

    const unsubscribe = registry.addWaiter('sess-1', waiter)
    unsubscribe()
    registry.notify({
      sessionId: 'sess-1',
      status: 'completed',
    })

    expect(waiter).not.toHaveBeenCalled()
  })
})
