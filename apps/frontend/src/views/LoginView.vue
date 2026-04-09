<template>
  <div class="login-view build-hub-view">
    <section class="launcher-stage">
      <section class="launcher-shell">
        <header class="launcher-header">
          <div class="brand-bar">
            <img src="/logo.svg" :alt="t.app.name" class="brand-logo" width="40" height="40" />
            <div class="brand-copy">
              <h1>{{ t.app.name }}</h1>
              <p class="launcher-slogan">{{ t.app.subtitle }}</p>
            </div>
          </div>
        </header>

        <div class="login-card">
          <div v-if="error" class="error-row">
            <AlertCircle :size="18" class="error-icon" aria-hidden="true" />
            <span class="error-copy">{{ error }}</span>
          </div>

          <div class="login-actions">
            <button
              type="button"
              class="login-primary ui-btn ui-btn--emphasis"
              :disabled="isLoading"
              @click="handleLogin"
            >
              <KeyRound :size="18" aria-hidden="true" />
              <span>{{ t.auth.login }}</span>
            </button>

            <button
              v-if="devMode"
              type="button"
              class="login-dev ui-btn ui-btn--neutral"
              :disabled="isLoading"
              @click="handleDevLogin"
            >
              <Terminal :size="18" aria-hidden="true" />
              <span>{{ t.auth.devMode }}</span>
            </button>
          </div>

          <div v-if="isLoading" class="loading-state">
            <div class="loading-card">
              <Loader2 class="loading-spin" :size="28" aria-hidden="true" />
              <p class="loading-title">{{ t.auth.loggingIn }}</p>
              <p class="loading-description">{{ t.auth.desktopLoginFinish }}</p>
            </div>
          </div>

          <div class="login-footer">
            <p class="privacy-note">
              {{ t.auth.agreement }}
            </p>
            <p class="version">v2.0.0</p>
          </div>
        </div>
      </section>
    </section>
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
import { AlertCircle, KeyRound, Loader2, Terminal } from 'lucide-vue-next'

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

const devMode = isDevMode()

const handleLogin = async () => {
  localError.value = null
  try {
    logger.info('开始统一 Web 登录流程')
    const result = await desktopWebAuth.startBridgeLogin(undefined, resolveRedirect())
    if (!result.success) {
      localError.value = result.error || t.value.auth.oauthFailed
    }
  } catch (err: unknown) {
    logger.error('OAuth 登录异常:', err)
    localError.value = err instanceof Error ? err.message : t.value.auth.oauthError
  }
}

const handleDevLogin = async () => {
  try {
    localLoading.value = true
    logger.info('开发模式免登录')

    localStorage.setItem(DEV_MODE_AUTH_KEY, 'true')
    localStorage.setItem(
      DEV_USER_KEY,
      JSON.stringify({
        id: 'dev-user-001',
        email: 'dev@dawnchat.local',
        name: 'Developer',
        created_at: new Date().toISOString(),
      })
    )

    logger.info('开发模式登录成功，刷新页面...')
    await loadUserFromStorage(true)
    await router.replace(resolveRedirect())
  } catch (err: unknown) {
    logger.error('开发模式登录失败:', err)
    localError.value = err instanceof Error ? err.message : t.value.auth.devLoginFailed
  } finally {
    localLoading.value = false
  }
}
</script>

<style scoped>
.login-view {
  width: 100%;
  min-height: 100vh;
  min-height: 100dvh;
  box-sizing: border-box;
  background: var(--color-app-canvas);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: max(1rem, env(safe-area-inset-top)) max(1rem, env(safe-area-inset-right))
    max(1rem, env(safe-area-inset-bottom)) max(1rem, env(safe-area-inset-left));
}

.launcher-stage {
  width: 100%;
  max-width: 520px;
  margin: 0 auto;
  padding: 0.25rem 0;
  flex-shrink: 0;
}

.launcher-shell {
  display: flex;
  flex-direction: column;
  gap: 0.82rem;
}

.launcher-header {
  margin-bottom: 0.1rem;
}

.brand-bar {
  display: flex;
  align-items: center;
  gap: 0.52rem;
}

.brand-logo {
  opacity: 0.9;
  filter: grayscale(0.1);
}

.brand-copy h1 {
  margin: 0;
  font-size: 1.95rem;
  line-height: 1.2;
  letter-spacing: 0.01em;
  font-weight: 620;
}

.launcher-slogan {
  margin: 0.12rem 0 0;
  color: var(--color-text-secondary);
  font-size: 0.8rem;
  line-height: 1.35;
}

.login-card {
  position: relative;
  border: 1px solid color-mix(in srgb, var(--color-border) 70%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-surface-2) 82%, transparent);
  padding: 0.86rem 0.9rem 0.72rem;
}

.error-row {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.62rem 0.72rem;
  margin-bottom: 0.72rem;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--color-danger) 35%, var(--color-border));
  background: color-mix(in srgb, var(--color-danger) 10%, var(--color-surface-2));
  color: color-mix(in srgb, var(--color-danger) 92%, var(--color-text-primary));
  font-size: 0.8rem;
  line-height: 1.4;
}

.error-icon {
  flex-shrink: 0;
  margin-top: 0.06rem;
}

.error-copy {
  text-align: left;
}

.login-actions {
  display: flex;
  flex-direction: column;
  gap: 0.46rem;
}

.login-primary,
.login-dev {
  min-height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-size: 0.88rem;
  font-weight: 600;
  width: 100%;
  padding: 0.48rem 0.85rem;
}

.login-dev {
  border-style: dashed;
}

.loading-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-app-canvas) 72%, transparent);
  backdrop-filter: blur(4px);
  z-index: 2;
}

.loading-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 1.1rem 1.25rem;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
  background: color-mix(in srgb, var(--color-surface-2) 92%, var(--color-app-canvas));
  box-shadow: 0 12px 36px rgba(15, 23, 42, 0.2);
  max-width: 92%;
}

.loading-spin {
  color: var(--color-text-secondary);
  animation: spin 0.9s linear infinite;
}

.loading-title {
  margin: 0;
  font-size: 0.88rem;
  font-weight: 620;
  color: var(--color-text-primary);
  text-align: center;
}

.loading-description {
  margin: 0;
  font-size: 0.74rem;
  color: var(--color-text-secondary);
  text-align: center;
  line-height: 1.35;
}

.login-footer {
  margin-top: 1.1rem;
  padding-top: 1rem;
  border-top: 1px solid color-mix(in srgb, var(--color-border) 84%, transparent);
  text-align: center;
}

.privacy-note {
  font-size: 0.74rem;
  color: var(--color-text-secondary);
  margin: 0 0 0.62rem;
  line-height: 1.45;
}

.version {
  font-size: 0.66rem;
  color: color-mix(in srgb, var(--color-text-secondary) 88%, transparent);
  margin: 0;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 760px) {
  .brand-copy h1 {
    font-size: 1.5rem;
  }
}
</style>
