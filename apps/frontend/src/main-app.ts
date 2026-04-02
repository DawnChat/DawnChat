import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import { initBackendUrl } from './utils/backendUrl'
import { logger } from './utils/logger'
import { router } from './app/router'
import { normalizeAuthCallbackHash } from './app/router/deepLink'

const serializeUnknownError = (error: unknown) => {
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      stack: error.stack
    }
  }

  if (typeof error === 'object' && error !== null) {
    try {
      return JSON.parse(JSON.stringify(error))
    } catch {
      return String(error)
    }
  }

  return error
}

export const startApp = async () => {
  logger.info('main_app_starting')

  if (normalizeAuthCallbackHash()) {
    logger.info('main_app_auth_callback_short_circuit')
    return
  }

  await initBackendUrl()
  logger.info('main_app_backend_url_ready')

  const app = createApp(App)
  const pinia = createPinia()
  app.config.errorHandler = (error, instance, info) => {
    const componentType = (instance as any)?.$?.type
    const componentName =
      componentType && typeof componentType === 'object'
        ? String(componentType.name ?? 'anonymous_component')
        : undefined

    logger.error('vue_runtime_error', {
      info,
      component: componentName,
      error: serializeUnknownError(error)
    })
  }

  app.use(pinia)
  app.use(router)
  await router.isReady()
  logger.info('main_app_router_ready')

  app.mount('#app')
  logger.info('main_app_mounted')
}
