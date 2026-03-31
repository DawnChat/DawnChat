<template>
  <div class="auth-callback">
    <div class="callback-container">
      <div v-if="isProcessing" class="processing">
        <div class="spinner"></div>
        <h2>{{ t.auth.processing }}</h2>
        <p>{{ t.auth.wait }}</p>
      </div>
      
      <div v-else-if="error" class="error">
        <AlertTriangle :size="64" class="error-icon" />
        <h2>{{ t.auth.failed }}</h2>
        <p>{{ error }}</p>
        <button @click="goToLogin" class="retry-btn">{{ t.auth.backToLogin }}</button>
      </div>
      
      <div v-else class="success">
        <CheckCircle :size="64" class="success-icon" />
        <h2>{{ t.auth.success }}</h2>
        <p>{{ t.auth.redirecting }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertTriangle, CheckCircle } from 'lucide-vue-next'
import { logger } from '@/utils/logger'
import { useI18n } from '@/composables/useI18n'
import { useAuth } from '@/shared/composables/useAuth'
import { resolveSafeRedirectPath } from '@/shared/auth/redirect'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const { handleDeepLinkCallback } = useAuth()
const isProcessing = ref(true)
const error = ref<string | null>(null)

const resolveRedirect = () => {
  return resolveSafeRedirectPath(route.query.redirect)
}

const resolveCallbackUrl = (): string => {
  const fullPath = route.fullPath.startsWith('/') ? route.fullPath : `/${route.fullPath}`
  return new URL(fullPath, window.location.origin).toString()
}

const summarizeCallbackLocation = (): Record<string, unknown> => {
  const url = new URL(window.location.href)
  return {
    origin: window.location.origin,
    pathname: window.location.pathname,
    routeFullPath: route.fullPath,
    hasTicket: url.searchParams.has('ticket'),
    hasState: url.searchParams.has('state'),
    hasCode: url.searchParams.has('code'),
    hasError: url.searchParams.has('error') || url.searchParams.has('error_description')
  }
}

onMounted(async () => {
  logger.info('🔄 AuthCallback 页面加载，处理统一登录回调...')

  try {
    const callbackUrl = resolveCallbackUrl()
    logger.info('📨 准备处理回调 URL', summarizeCallbackLocation())

    const result = await handleDeepLinkCallback(callbackUrl)
    if (!result.success) {
      throw new Error(result.error || t.value.auth.errors.failed)
    }

    isProcessing.value = false
    const redirect = result.redirectPath || resolveRedirect()
    logger.info('✅ 统一登录回调处理成功，准备跳转', { redirect })
    await router.replace(redirect)
  } catch (err: any) {
    logger.error('❌ 统一登录回调处理失败:', err)
    error.value = err.message || t.value.auth.errors.failed
    isProcessing.value = false
  }
})

const goToLogin = () => {
  router.replace('/login')
}
</script>

<style scoped>
.auth-callback {
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.callback-container {
  width: 100%;
  max-width: 420px;
  padding: 3rem;
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  text-align: center;
}

.processing, .error, .success {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

h2 {
  margin: 0;
  font-size: 1.5rem;
  color: #333;
}

p {
  margin: 0;
  color: #666;
}

.error-icon {
  color: #ef4444;
}

.success-icon {
  color: #22c55e;
}

.retry-btn {
  margin-top: 1rem;
  padding: 0.75rem 1.5rem;
  background: #667eea;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.2s;
}

.retry-btn:hover {
  background: #5a6fd6;
  transform: translateY(-2px);
}
</style>
