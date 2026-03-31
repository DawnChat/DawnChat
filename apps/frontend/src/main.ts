import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import { initBackendUrl } from './utils/backendUrl'
import { router } from './app/router'
import { normalizeAuthCallbackHash } from './app/router/deepLink'

const startApp = async () => {
  if (normalizeAuthCallbackHash()) {
    return
  }

  await initBackendUrl()
  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)
  app.use(router)
  await router.isReady()
  app.mount('#app')
}

startApp()
