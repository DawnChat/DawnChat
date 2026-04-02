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

window.addEventListener('error', (event) => {
  logger.error('window_error', {
    message: event.message,
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
    error: serializeUnknownError(event.error)
  })
})

window.addEventListener('unhandledrejection', (event) => {
  logger.error('window_unhandledrejection', {
    reason: serializeUnknownError(event.reason)
  })
})

const startApp = async () => {
  if (normalizeAuthCallbackHash()) {
    return
  }

  await initBackendUrl()
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
  app.mount('#app')
}

void startApp().catch((error) => {
  logger.error('start_app_failed', {
    error: serializeUnknownError(error)
  })
})
