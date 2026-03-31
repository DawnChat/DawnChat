import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import type { Router } from 'vue-router'

const authState = {
  isAuthenticated: ref(false),
  loadUserFromStorage: vi.fn()
}

vi.mock('@/shared/composables/useAuth', () => ({
  useAuth: () => authState
}))

import { setupRouterGuards } from '../guards'

type GuardFn = (to: any) => Promise<any>

describe('router guards', () => {
  let guard: GuardFn

  beforeEach(() => {
    guard = async () => true
    authState.isAuthenticated.value = false
    authState.loadUserFromStorage.mockClear()
    authState.loadUserFromStorage.mockResolvedValue(undefined)

    const router = {
      beforeEach: (fn: GuardFn) => {
        guard = fn
      }
    } as unknown as Router
    setupRouterGuards(router)
  })

  it('does not rewrite legacy path and only handles auth flow', async () => {
    const result = await guard({
      path: '/pipeline/task_123',
      fullPath: '/pipeline/task_123',
      meta: { requiresAuth: true },
      query: {}
    })

    expect(result).toEqual({
      name: 'login',
      query: {
        redirect: '/app/apps/hub'
      }
    })
  })

  it('redirects protected route to login when unauthenticated', async () => {
    const result = await guard({
      path: '/app/apps/installed',
      fullPath: '/app/apps/installed',
      meta: { requiresAuth: true },
      query: {}
    })

    expect(result).toEqual({
      name: 'login',
      query: {
        redirect: '/app/apps/installed'
      }
    })
  })

  it('normalizes unsafe redirect target to default route', async () => {
    const result = await guard({
      path: '/app/apps/installed',
      fullPath: 'https://malicious.example/phishing',
      meta: { requiresAuth: true },
      query: {}
    })

    expect(result).toEqual({
      name: 'login',
      query: {
        redirect: '/app/apps/hub'
      }
    })
  })

  it('redirects authenticated login access to safe redirect path', async () => {
    authState.isAuthenticated.value = true
    const result = await guard({
      name: 'login',
      path: '/login',
      fullPath: '/login?redirect=/app/pipeline',
      meta: { requiresAuth: false },
      query: { redirect: '/app/pipeline' }
    })

    expect(result).toBe('/app/pipeline')
  })
})
