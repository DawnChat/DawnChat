import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const exchangeDesktopTicketMock = vi.fn()
const getSessionMock = vi.fn()
const signOutMock = vi.fn()
const saveSupabaseSessionMock = vi.fn()
const deleteSupabaseSessionMock = vi.fn()
const getSupabaseSessionMock = vi.fn()
const loadAuthUserFromStorageMock = vi.fn()
const saveAuthUserToStorageMock = vi.fn()
const clearAuthUserStorageMock = vi.fn()
const setSessionMock = vi.fn()
let authStateChangeHandler: ((event: string, session: any) => Promise<void> | void) | null = null

vi.mock('@/shared/composables/supabaseClient', () => ({
  useSupabase: () => ({
    getSession: getSessionMock,
    signOut: signOutMock
  }),
  supabase: {
    auth: {
      getSession: vi.fn(async () => ({ data: { session: null } })),
      setSession: setSessionMock,
      onAuthStateChange: vi.fn((handler: any) => {
        authStateChangeHandler = handler
        return {
          data: {
            subscription: {
              unsubscribe: vi.fn()
            }
          }
        }
      })
    }
  }
}))

vi.mock('@/auth-bridge/useDesktopWebAuth', () => ({
  useDesktopWebAuth: () => ({
    exchangeDesktopTicket: exchangeDesktopTicketMock
  })
}))

vi.mock('@/shared/composables/useSecureStorage', () => ({
  getSupabaseSession: getSupabaseSessionMock,
  saveSupabaseSession: saveSupabaseSessionMock,
  deleteSupabaseSession: deleteSupabaseSessionMock
}))

vi.mock('@/shared/auth/userStorage', () => ({
  loadAuthUserFromStorage: loadAuthUserFromStorageMock,
  saveAuthUserToStorage: saveAuthUserToStorageMock,
  clearAuthUserStorage: clearAuthUserStorageMock
}))

vi.mock('@/composables/useI18n', () => ({
  useI18n: () => ({
    t: ref({
      auth: {
        authFailed: 'auth failed',
        logoutFailed: 'logout failed'
      }
    })
  })
}))

let tauriEventHandler: ((event: { payload: string }) => Promise<void> | void) | null = null

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(async (_event: string, handler: any) => {
    tauriEventHandler = handler
    return vi.fn()
  })
}))

const createSupabaseSession = () => ({
  access_token: 'access_token_value',
  refresh_token: 'refresh_token_value',
  expires_at: 123456,
  token_type: 'bearer',
  user: {
    id: 'user_1',
    email: 'user@example.com',
    user_metadata: {
      name: 'User'
    },
    app_metadata: {
      provider: 'google'
    },
    created_at: '2025-01-01T00:00:00.000Z',
    updated_at: '2025-01-02T00:00:00.000Z'
  }
})

describe('useAuth', () => {
  beforeEach(() => {
    vi.resetModules()
    tauriEventHandler = null
    authStateChangeHandler = null
    exchangeDesktopTicketMock.mockReset()
    getSessionMock.mockReset()
    signOutMock.mockReset()
    saveSupabaseSessionMock.mockReset()
    deleteSupabaseSessionMock.mockReset()
    getSupabaseSessionMock.mockReset()
    loadAuthUserFromStorageMock.mockReset()
    saveAuthUserToStorageMock.mockReset()
    clearAuthUserStorageMock.mockReset()
    setSessionMock.mockReset()

    getSessionMock.mockResolvedValue(null)
    signOutMock.mockResolvedValue({ success: true })
    getSupabaseSessionMock.mockResolvedValue(null)
    loadAuthUserFromStorageMock.mockResolvedValue(null)
    saveAuthUserToStorageMock.mockResolvedValue(undefined)
    clearAuthUserStorageMock.mockResolvedValue(undefined)
    deleteSupabaseSessionMock.mockResolvedValue(undefined)
    saveSupabaseSessionMock.mockResolvedValue(undefined)
    setSessionMock.mockResolvedValue({
      data: { session: createSupabaseSession() },
      error: null
    })

    ;(window as any).__TAURI_INTERNALS__ = {
      invoke: vi.fn(async (command: string) => {
        if (command === 'consume_pending_auth_callback') {
          return null
        }
        return null
      })
    }
  })

  it('consumes pending auth callback after listener registration', async () => {
    exchangeDesktopTicketMock.mockResolvedValue({
      session: createSupabaseSession(),
      nextPath: '/app/apps/hub'
    })
    ;(window as any).__TAURI_INTERNALS__.invoke = vi.fn(async (command: string) => {
      if (command === 'consume_pending_auth_callback') {
        return 'dawnchat://auth/callback?ticket=ticket_1&state=state_1'
      }
      return null
    })

    const { useAuth } = await import('../useAuth')
    const auth = useAuth()
    const signedInListener = vi.fn()
    window.addEventListener('dawnchat-auth-signed-in', signedInListener)

    await auth.initAuthListener()

    expect(tauriEventHandler).not.toBeNull()
    expect(exchangeDesktopTicketMock).toHaveBeenCalledWith('dawnchat://auth/callback?ticket=ticket_1&state=state_1')
    expect(signedInListener).toHaveBeenCalledTimes(1)
    const customEvent = signedInListener.mock.calls[0][0] as CustomEvent<{ redirectPath?: string }>
    expect(customEvent.detail?.redirectPath).toBe('/app/apps/hub')

    window.removeEventListener('dawnchat-auth-signed-in', signedInListener)
  })

  it('persists refreshed auth state into secure storage', async () => {
    const session = createSupabaseSession()
    const { useAuth } = await import('../useAuth')
    const auth = useAuth()

    await auth.initAuthListener()
    expect(authStateChangeHandler).not.toBeNull()

    await authStateChangeHandler?.('TOKEN_REFRESHED', session)

    expect(saveSupabaseSessionMock).toHaveBeenCalled()
    expect(saveAuthUserToStorageMock).toHaveBeenCalled()
    expect(auth.user.value?.id).toBe('user_1')
    expect(auth.session.value?.access_token).toBe('access_token_value')
  })

  it('clears persisted auth state when signed out', async () => {
    const { useAuth } = await import('../useAuth')
    const auth = useAuth()

    await auth.initAuthListener()
    await authStateChangeHandler?.('SIGNED_OUT', null)

    expect(deleteSupabaseSessionMock).toHaveBeenCalled()
    expect(clearAuthUserStorageMock).toHaveBeenCalled()
    expect(auth.user.value).toBeNull()
  })
})
