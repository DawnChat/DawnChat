import { beforeEach, describe, expect, it, vi } from 'vitest'

const startCheckingMock = vi.fn()
const stopCheckingMock = vi.fn()
const markFailedMock = vi.fn()
const markRestartingMock = vi.fn()

const eventHandlers = new Map<string, (event: { payload: unknown }) => void>()

vi.mock('@/composables/useBackendStatus', () => ({
  useBackendStatus: () => ({
    startChecking: startCheckingMock,
    stopChecking: stopCheckingMock,
    markFailed: markFailedMock,
    markRestarting: markRestartingMock
  })
}))

vi.mock('@/adapters/events', () => ({
  EVENTS: {
    BACKEND_START_FAILED: 'backend-start-failed',
    BACKEND_CRASHED: 'backend-crashed',
    BACKEND_RESTARTING: 'backend-restarting'
  },
  listen: vi.fn(async (eventName: string, handler: (event: { payload: unknown }) => void) => {
    eventHandlers.set(eventName, handler)
    return vi.fn(() => eventHandlers.delete(eventName))
  })
}))

describe('initBackendBootstrap', () => {
  beforeEach(() => {
    eventHandlers.clear()
    startCheckingMock.mockReset()
    stopCheckingMock.mockReset()
    markFailedMock.mockReset()
    markRestartingMock.mockReset()
    startCheckingMock.mockResolvedValue(undefined)
  })

  it('starts backend checking on bootstrap', async () => {
    const { initBackendBootstrap } = await import('../initBackend')
    const cleanup = await initBackendBootstrap()

    expect(startCheckingMock).toHaveBeenCalledWith('waiting_for_backend')
    cleanup()
    expect(stopCheckingMock).toHaveBeenCalled()
  })

  it('marks fatal state when backend start fails', async () => {
    const { initBackendBootstrap } = await import('../initBackend')
    await initBackendBootstrap()

    eventHandlers.get('backend-start-failed')?.({ payload: 'Python 启动失败' })

    expect(markFailedMock).toHaveBeenCalledWith('Python 启动失败')
  })

  it('restarts health checking when backend restarts or crashes', async () => {
    const { initBackendBootstrap } = await import('../initBackend')
    await initBackendBootstrap()

    eventHandlers.get('backend-restarting')?.({ payload: null })
    eventHandlers.get('backend-crashed')?.({ payload: null })

    expect(markRestartingMock).toHaveBeenCalledTimes(2)
    expect(startCheckingMock).toHaveBeenNthCalledWith(2, 'backend_restarting')
    expect(startCheckingMock).toHaveBeenNthCalledWith(3, 'backend_restarting')
  })
})
