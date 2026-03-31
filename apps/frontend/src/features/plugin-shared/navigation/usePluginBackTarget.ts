import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'
import { resolveFullscreenBackTarget } from '@/app/router/deepLink'

export const usePluginBackTarget = (route: RouteLocationNormalizedLoaded, router: Router) => {
  const redirectToAppsInstalled = () => {
    const target = resolveFullscreenBackTarget(route.query.from)
    router.replace(target)
  }

  return {
    redirectToAppsInstalled,
  }
}
