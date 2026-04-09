<template>
  <div class="auth-callback build-hub-view">
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

        <div class="callback-card">
          <div v-if="isProcessing" class="state-block">
            <Loader2 class="state-loader" :size="32" aria-hidden="true" />
            <h2 class="state-title">{{ t.auth.processing }}</h2>
            <p class="state-desc">{{ t.auth.wait }}</p>
          </div>

          <div v-else-if="error" class="state-block">
            <div class="state-icon-wrap state-icon-wrap--error" aria-hidden="true">
              <AlertCircle :size="28" />
            </div>
            <h2 class="state-title">{{ t.auth.failed }}</h2>
            <p class="state-desc state-desc--error">{{ error }}</p>
            <button type="button" class="action-btn ui-btn ui-btn--emphasis" @click="goToLogin">
              {{ t.auth.backToLogin }}
            </button>
          </div>

          <div v-else class="state-block">
            <div class="state-icon-wrap state-icon-wrap--success" aria-hidden="true">
              <CheckCircle :size="28" />
            </div>
            <h2 class="state-title">{{ t.auth.success }}</h2>
            <p class="state-desc">{{ t.auth.redirecting }}</p>
          </div>
        </div>
      </section>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertCircle, CheckCircle, Loader2 } from 'lucide-vue-next'
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
  logger.info('AuthCallback: handling unified login callback')

  try {
    const callbackUrl = resolveCallbackUrl()
    logger.info('AuthCallback: processing callback URL', summarizeCallbackLocation())

    const result = await handleDeepLinkCallback(callbackUrl)
    if (!result.success) {
      throw new Error(result.error || t.value.auth.errors.failed)
    }

    isProcessing.value = false
    const redirect = result.redirectPath || resolveRedirect()
    logger.info('AuthCallback: success, navigating', { redirect })
    await router.replace(redirect)
  } catch (err: unknown) {
    logger.error('AuthCallback: handler failed', err)
    error.value = err instanceof Error ? err.message : t.value.auth.errors.failed
    isProcessing.value = false
  }
})

const goToLogin = () => {
  router.replace('/login')
}
</script>

<style scoped>
.auth-callback {
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

.callback-card {
  border: 1px solid color-mix(in srgb, var(--color-border) 70%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-surface-2) 82%, transparent);
  padding: 1.25rem 0.9rem 1.1rem;
}

.state-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.62rem;
  text-align: center;
}

.state-loader {
  color: var(--color-text-secondary);
  animation: spin 0.9s linear infinite;
}

.state-icon-wrap {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--color-border) 85%, transparent);
}

.state-icon-wrap--error {
  background: color-mix(in srgb, var(--color-danger) 12%, var(--color-surface-1));
  color: color-mix(in srgb, var(--color-danger) 92%, var(--color-text-primary));
}

.state-icon-wrap--success {
  background: color-mix(in srgb, var(--color-success) 14%, var(--color-surface-1));
  color: var(--color-success);
}

.state-title {
  margin: 0;
  font-size: 0.98rem;
  font-weight: 620;
  line-height: 1.3;
  color: var(--color-text-primary);
}

.state-desc {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.45;
  color: var(--color-text-secondary);
  max-width: 28rem;
}

.state-desc--error {
  color: color-mix(in srgb, var(--color-danger) 88%, var(--color-text-secondary));
}

.action-btn {
  margin-top: 0.35rem;
  width: 100%;
  max-width: 280px;
  min-height: 40px;
  padding: 0.48rem 0.85rem;
  font-size: 0.88rem;
  font-weight: 600;
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
