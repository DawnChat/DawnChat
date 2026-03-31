import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DESKTOP_AUTH_PENDING_KEY } from '@dawnchat/auth-bridge'

const setSessionMock = vi.fn()
const saveSupabaseSessionMock = vi.fn()

vi.mock('@/shared/composables/supabaseClient', () => ({
  supabase: {
    auth: {
      setSession: setSessionMock
    }
  }
}))

vi.mock('@/shared/composables/useSecureStorage', () => ({
  generatePersistentDeviceId: vi.fn(async () => 'device-fixed'),
  saveSupabaseSession: saveSupabaseSessionMock
}))

const setPendingState = (state = 'state_ok', deviceId = 'device_ok') => {
  localStorage.setItem(
    DESKTOP_AUTH_PENDING_KEY,
    JSON.stringify({
      state,
      deviceId,
      createdAt: Date.now(),
      nextPath: '/app/workbench'
    })
  )
}

const mockFetchError = (payload: Record<string, unknown>, status = 401) => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: false,
      status,
      text: async () => JSON.stringify(payload)
    }))
  )
}

const mockFetchSuccess = (payload: Record<string, unknown>) => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => payload
    }))
  )
}

const loadComposable = async () => {
  vi.resetModules()
  vi.stubEnv('VITE_SUPABASE_URL', 'https://example.supabase.co')
  vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'anon-key')
  return import('../useDesktopWebAuth')
}

describe('useDesktopWebAuth.exchangeDesktopTicket', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    setSessionMock.mockReset()
    saveSupabaseSessionMock.mockReset()
    setSessionMock.mockResolvedValue({
      data: {
        session: {
          access_token: 'desktop_access',
          refresh_token: 'desktop_refresh',
          expires_at: 123456,
          token_type: 'bearer',
          user: { id: 'user_1' }
        }
      },
      error: null
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('rejects when pending state is missing', async () => {
    mockFetchSuccess({ access_token: 'a', refresh_token: 'b' })
    const { useDesktopWebAuth } = await loadComposable()
    const auth = useDesktopWebAuth()
    await expect(auth.exchangeDesktopTicket('dawnchat://auth/callback?ticket=t1&state=s1')).rejects.toThrow(
      '登录状态已失效，请重新发起登录'
    )
  })

  it('rejects and clears pending state when state mismatches', async () => {
    setPendingState('state_ok', 'device_ok')
    mockFetchSuccess({ access_token: 'a', refresh_token: 'b' })
    const { useDesktopWebAuth } = await loadComposable()
    const auth = useDesktopWebAuth()
    await expect(
      auth.exchangeDesktopTicket('dawnchat://auth/callback?ticket=t1&state=state_bad')
    ).rejects.toThrow('登录状态校验失败，请重新登录')
    expect(localStorage.getItem(DESKTOP_AUTH_PENDING_KEY)).toBeNull()
  })

  it('returns ticket_expired error message from exchange API', async () => {
    setPendingState('state_ok', 'device_ok')
    mockFetchError({ code: 'ticket_expired', message: 'Ticket expired' })
    const { useDesktopWebAuth } = await loadComposable()
    const auth = useDesktopWebAuth()
    await expect(
      auth.exchangeDesktopTicket('dawnchat://auth/callback?ticket=t1&state=state_ok')
    ).rejects.toThrow('Ticket expired')
  })

  it('returns ticket_used error message from exchange API', async () => {
    setPendingState('state_ok', 'device_ok')
    mockFetchError({ code: 'ticket_used', message: 'Ticket already consumed' })
    const { useDesktopWebAuth } = await loadComposable()
    const auth = useDesktopWebAuth()
    await expect(
      auth.exchangeDesktopTicket('dawnchat://auth/callback?ticket=t1&state=state_ok')
    ).rejects.toThrow('Ticket already consumed')
  })

  it('completes exchange and clears pending state on success', async () => {
    setPendingState('state_ok', 'device_ok')
    mockFetchSuccess({
      access_token: 'a',
      refresh_token: 'b',
      next_path: '/app/apps/hub'
    })
    const { useDesktopWebAuth } = await loadComposable()
    const auth = useDesktopWebAuth()
    const result = await auth.exchangeDesktopTicket('dawnchat://auth/callback?ticket=t1&state=state_ok')
    expect(result.nextPath).toBe('/app/apps/hub')
    expect(localStorage.getItem(DESKTOP_AUTH_PENDING_KEY)).toBeNull()
    expect(saveSupabaseSessionMock).toHaveBeenCalledTimes(1)
  })

  it('supports retry after transient exchange failure', async () => {
    setPendingState('state_ok', 'device_ok')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        text: async () => JSON.stringify({ code: 'unexpected_error', message: 'temporary failure' })
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          access_token: 'a',
          refresh_token: 'b',
          next_path: '/app/workbench'
        })
      })
    vi.stubGlobal('fetch', fetchMock)
    const { useDesktopWebAuth } = await loadComposable()
    const auth = useDesktopWebAuth()
    await expect(
      auth.exchangeDesktopTicket('dawnchat://auth/callback?ticket=t1&state=state_ok')
    ).rejects.toThrow('temporary failure')
    expect(localStorage.getItem(DESKTOP_AUTH_PENDING_KEY)).not.toBeNull()
    const result = await auth.exchangeDesktopTicket('dawnchat://auth/callback?ticket=t1&state=state_ok')
    expect(result.nextPath).toBe('/app/workbench')
    expect(localStorage.getItem(DESKTOP_AUTH_PENDING_KEY)).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
