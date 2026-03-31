import type { Router } from 'vue-router'
import { useAuth } from '@/shared/composables/useAuth'
import { resolveSafeRedirectPath } from '@/shared/auth/redirect'

export const setupRouterGuards = (router: Router) => {
  const auth = useAuth()

  router.beforeEach(async (to) => {
    await auth.loadUserFromStorage()

    const requiresAuth = Boolean(to.meta.requiresAuth)
    if (!requiresAuth) {
      if (to.name === 'login' && auth.isAuthenticated.value) {
        return resolveSafeRedirectPath(to.query.redirect)
      }
      return true
    }

    if (!auth.isAuthenticated.value) {
      return {
        name: 'login',
        query: {
          redirect: resolveSafeRedirectPath(to.fullPath)
        }
      }
    }

    return true
  })
}
