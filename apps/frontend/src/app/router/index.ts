import { createRouter, createWebHashHistory } from 'vue-router'
import { routes } from './routes'
import { setupRouterGuards } from './guards'
import { setupRouterAnalytics } from './analytics'

export const router = createRouter({
  history: createWebHashHistory(),
  routes
})

setupRouterGuards(router)
setupRouterAnalytics(router)
