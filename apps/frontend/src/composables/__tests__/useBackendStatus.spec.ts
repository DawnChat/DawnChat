import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: ref({
      backend: {
        checkTimeout: '服务启动超时，请检查应用日志'
      }
    })
  })
}))

describe('useBackendStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.resetModules()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('auto-recovers after timeout once backend becomes ready', async () => {
    let callCount = 0
    vi.stubGlobal('fetch', vi.fn(async () => {
      callCount += 1
      if (callCount >= 63) {
        return {
          ok: true,
          json: async () => ({ status: 'ok', name: 'DawnChat' })
        }
      }
      throw new Error('not ready')
    }))

    const { useBackendStatus } = await import('../useBackendStatus')
    const backend = useBackendStatus()

    await backend.startChecking('waiting_for_backend')
    await vi.advanceTimersByTimeAsync(64000)

    expect(backend.status.value.phase).toBe('backend_ready')
    expect(backend.status.value.isReady).toBe(true)
    expect(callCount).toBeGreaterThanOrEqual(63)
  })

  it('stops accumulating retries after backend becomes ready', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'ok', name: 'DawnChat' })
    }))
    vi.stubGlobal('fetch', fetchMock)

    const { useBackendStatus } = await import('../useBackendStatus')
    const backend = useBackendStatus()

    await backend.startChecking('waiting_for_backend')
    expect(backend.status.value.phase).toBe('backend_ready')
    expect(backend.status.value.retryCount).toBe(0)

    await vi.advanceTimersByTimeAsync(10000)

    expect(backend.status.value.phase).toBe('backend_ready')
    expect(backend.status.value.retryCount).toBe(0)
  })
})
