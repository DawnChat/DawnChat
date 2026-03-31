import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { createStreamWatchdog } from '@/features/coding-agent/store/streamWatchdog'

describe('streamWatchdog', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('静默超时后会触发恢复回调', () => {
    vi.useFakeTimers()
    const onStale = vi.fn()
    const streamWatchdogs = ref<Record<string, number>>({})
    const watchdog = createStreamWatchdog({
      streamWatchdogs,
      getOrCreateSessionState: () => ({}) as any,
      reconcileMessages: async () => {},
      onStale,
      staleTimeoutMs: 20
    })

    watchdog.startStreamWatchdog('s1')
    vi.advanceTimersByTime(21)

    expect(onStale).toHaveBeenCalledTimes(1)
    expect(onStale.mock.calls[0]?.[0]).toBe('s1')
  })

  it('恢复回调会按最小间隔节流', () => {
    vi.useFakeTimers()
    const onStale = vi.fn()
    const streamWatchdogs = ref<Record<string, number>>({})
    const watchdog = createStreamWatchdog({
      streamWatchdogs,
      getOrCreateSessionState: () => ({}) as any,
      reconcileMessages: async () => {},
      onStale,
      staleTimeoutMs: 20,
      minRecoverIntervalMs: 100
    })

    watchdog.startStreamWatchdog('s1')
    vi.advanceTimersByTime(21)
    watchdog.startStreamWatchdog('s1')
    vi.advanceTimersByTime(21)
    expect(onStale).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(101)
    watchdog.startStreamWatchdog('s1')
    vi.advanceTimersByTime(21)
    expect(onStale).toHaveBeenCalledTimes(2)
  })
})
