import type { Router } from 'vue-router'
import { logger } from '@/utils/logger'

export const setupRouterAnalytics = (router: Router) => {
  router.afterEach((to, from) => {
    const trackEvent = String(to.meta.trackEvent || 'page_view')
    const entityIdParam = typeof to.meta.entityIdParam === 'string' ? to.meta.entityIdParam : null
    const entityId = entityIdParam ? to.params[entityIdParam] : null

    logger.info('📍 route_changed', {
      event: trackEvent,
      from: from.fullPath,
      to: to.fullPath,
      routeName: to.name,
      feature: String(to.meta.feature || 'app'),
      pageType: String(to.meta.pageType || 'page'),
      entityType: String(to.meta.entityType || 'none'),
      entityId: entityId || null,
      pluginId: to.params.pluginId || null
    })
  })
}
