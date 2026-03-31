<template>
  <div class="login-view">
    <div class="login-container">
      <div class="login-header">
        <div class="app-logo">
          <img src="/logo.png" :alt="t.app.name" class="logo-image" />
        </div>
        <h1>{{ t.app.name }}</h1>
        <p class="subtitle">{{ t.app.subtitle }}</p>
      </div>

      <div v-if="error" class="error-message">
        <AlertTriangle :size="20" class="mr-2 inline-icon" />
        {{ error }}
      </div>

      <div class="login-buttons">
        <button
          @click="handleLogin"
          :disabled="isLoading"
          class="login-btn web"
        >
          <LogIn :size="20" />
          <span class="btn-text">{{ t.auth.login }}</span>
        </button>

        <!-- 开发模式免登录选项 -->
        <button
          v-if="devMode"
          @click="handleDevLogin"
          :disabled="isLoading"
          class="login-btn dev"
        >
          <Code :size="20" />
          <span class="btn-text">{{ t.auth.devMode }}</span>
        </button>
      </div>

      <div v-if="isLoading" class="loading-state">
        <div class="loading-card">
          <div class="spinner"></div>
          <p class="loading-title">{{ t.auth.loggingIn }}</p>
          <p class="loading-description">正在完成桌面登录，请稍候…</p>
        </div>
      </div>

      <div class="login-footer">
        <p class="privacy-note">
          {{ t.auth.agreement }}
        </p>
        <p class="version">v2.0.0</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuth } from '@/shared/composables/useAuth'
import { useI18n } from '@/composables/useI18n'
import { logger } from '@/utils/logger'
import { isDevMode } from '@/adapters'
import { useDesktopWebAuth } from '@/auth-bridge/useDesktopWebAuth'
import { DEV_MODE_AUTH_KEY, DEV_USER_KEY } from '@/shared/auth/userStorage'
import { resolveSafeRedirectPath } from '@/shared/auth/redirect'
import { useRoute, useRouter } from 'vue-router'
import { computed, ref } from 'vue'
import { AlertTriangle, Code, LogIn } from 'lucide-vue-next'

const desktopWebAuth = useDesktopWebAuth()
const localLoading = ref(false)
const localError = ref<string | null>(null)
const isLoading = computed(() => desktopWebAuth.isLoading.value || localLoading.value)
const error = computed(() => desktopWebAuth.error.value || localError.value)
const { loadUserFromStorage } = useAuth()
const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const resolveRedirect = () => {
  return resolveSafeRedirectPath(route.query.redirect)
}

// 开发模式检测
const devMode = isDevMode()

const handleLogin = async () => {
  localError.value = null
  try {
    logger.info('🔐 开始统一 Web 登录流程')
    const result = await desktopWebAuth.startBridgeLogin(undefined, resolveRedirect())
    if (!result.success) {
      localError.value = result.error || t.value.auth.oauthFailed
    }
  } catch (err: any) {
    logger.error('❌ OAuth 登录异常:', err)
    localError.value = err.message || t.value.auth.oauthError
  }
}

/**
 * 开发模式免登录
 * 直接跳过认证，使用 mock 用户
 */
const handleDevLogin = async () => {
  try {
    localLoading.value = true
    logger.info('🔧 开发模式免登录')
    
    // 设置一个 mock 标记到 localStorage
    localStorage.setItem(DEV_MODE_AUTH_KEY, 'true')
    localStorage.setItem(DEV_USER_KEY, JSON.stringify({
      id: 'dev-user-001',
      email: 'dev@dawnchat.local',
      name: 'Developer',
      created_at: new Date().toISOString()
    }))
    
    logger.info('✅ 开发模式登录成功，刷新页面...')
    await loadUserFromStorage(true)
    await router.replace(resolveRedirect())
    
  } catch (err: any) {
    logger.error('❌ 开发模式登录失败:', err)
    localError.value = err.message || t.value.auth.devLoginFailed
  } finally {
    localLoading.value = false
  }
}

</script>

<style scoped>
.login-view {
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-container {
  position: relative;
  width: 100%;
  max-width: 420px;
  padding: 3rem;
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.login-header {
  text-align: center;
  margin-bottom: 2.5rem;
}

.app-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;
}

.logo-image {
  width: 64px;
  height: 64px;
  object-fit: contain;
}

.login-header h1 {
  margin: 0 0 0.5rem 0;
  font-size: 2rem;
  font-weight: 700;
  color: #333;
}

.subtitle {
  margin: 0;
  font-size: 1rem;
  color: #666;
}

.error-message {
  padding: 1rem;
  background: #fee;
  border: 1px solid #fcc;
  border-radius: 8px;
  color: #c00;
  margin-bottom: 1.5rem;
  text-align: center;
}

.login-buttons {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  margin-bottom: 2rem;
}

.login-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.login-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-btn.web {
  background: #4285f4;
  color: white;
}

.login-btn.web:hover:not(:disabled) {
  background: #357ae8;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(66, 133, 244, 0.4);
}

.login-btn.dev {
  background: #f59e0b;
  color: white;
  border: 2px dashed #d97706;
}

.login-btn.dev:hover:not(:disabled) {
  background: #d97706;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4);
}

.btn-icon {
  font-size: 1.5rem;
}

.btn-text {
  font-size: 1rem;
}

.loading-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(6px);
  z-index: 2;
}

.loading-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 1.5rem 2rem;
  border-radius: 18px;
  background: rgba(102, 126, 234, 0.08);
  border: 1px solid rgba(102, 126, 234, 0.14);
  box-shadow: 0 16px 40px rgba(99, 102, 241, 0.14);
}

.spinner {
  width: 40px;
  height: 40px;
  margin: 0 auto 1rem;
  border: 4px solid #f3f3f3;
  border-top: 4px solid #667eea;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-title {
  color: #334155;
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
}

.loading-description {
  color: #64748b;
  font-size: 0.9rem;
  margin: 0;
}

.login-footer {
  text-align: center;
  padding-top: 2rem;
  border-top: 1px solid #eee;
}

.privacy-note {
  font-size: 0.85rem;
  color: #999;
  margin: 0 0 1rem 0;
  line-height: 1.5;
}

.version {
  font-size: 0.75rem;
  color: #ccc;
  margin: 0;
}
</style>
