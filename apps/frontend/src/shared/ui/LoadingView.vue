<template>
  <div class="loading-view build-hub-view">
    <section class="launcher-stage">
      <section class="launcher-shell">
        <header class="launcher-header">
          <div class="brand-bar">
            <img src="/logo.svg" alt="DawnChat" class="brand-logo" width="40" height="40" />
            <div class="brand-copy">
              <h1>{{ t.app.name }}</h1>
              <p class="launcher-slogan">{{ t.loading.subtitle }}</p>
            </div>
          </div>
        </header>

        <div class="startup-card">
          <div class="startup-card-body">
            <div class="startup-visual">
              <div class="card-icon">
                <Sparkles :size="20" />
              </div>
              <Loader2
                v-if="!props.status.isReady && !props.status.error"
                class="status-loader"
                :size="20"
                aria-hidden="true"
              />
            </div>
            <p class="status-headline">{{ headline }}</p>
            <p class="status-meta">{{ metaLine }}</p>
            <p v-if="devRetryHint" class="dev-retry-hint">{{ devRetryHint }}</p>

            <div v-if="props.status.error" class="error-block">
              <p class="error-text">{{ props.status.error }}</p>
              <button type="button" class="retry-btn ui-btn ui-btn--emphasis" @click="props.retry">
                {{ t.loading.retry }}
              </button>
            </div>
          </div>

          <div v-if="!props.status.error" class="progress-block">
            <div class="progress-header">
              <span class="progress-pill">{{ progressLabel }}</span>
            </div>
            <div class="progress-outer">
              <div class="progress-inner" :style="{ width: `${progressPercent}%` }" />
            </div>
          </div>
        </div>
      </section>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { Loader2, Sparkles } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import type { BackendStatus } from '@/composables/useBackendStatus'
import { useBackendStartupProgress } from '@/shared/composables/useBackendStartupProgress'

const props = defineProps<{
  status: BackendStatus
  retry: () => void
}>()

const { t } = useI18n()
const statusRef = toRef(props, 'status')
const { progressPercent, progressLabel } = useBackendStartupProgress(statusRef)

const headline = computed(() => {
  if (props.status.error) {
    return t.value.loading.connectionFailed
  }
  if (props.status.isReady) {
    return t.value.loading.serviceReady
  }
  if (props.status.phase === 'backend_restarting') {
    return t.value.loading.startupRestarting
  }
  return t.value.loading.startupHeadline
})

const metaLine = computed(() => {
  if (props.status.error) {
    return t.value.loading.timeout
  }
  if (props.status.isReady) {
    return t.value.loading.loadingApp
  }
  return t.value.loading.startupProgressHint
})

const devRetryHint = computed(() => {
  if (!import.meta.env.DEV || props.status.retryCount <= 0 || props.status.error) {
    return ''
  }
  return t.value.loading.retryCount
    .replace('{current}', String(props.status.retryCount))
    .replace('{max}', String(props.status.maxRetries))
})
</script>

<style scoped>
.loading-view {
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

.startup-card {
  border: 1px solid color-mix(in srgb, var(--color-border) 70%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-surface-2) 82%, transparent);
  overflow: hidden;
}

.startup-card-body {
  padding: 0.86rem 0.9rem 0.72rem;
}

.startup-visual {
  display: flex;
  align-items: center;
  gap: 0.62rem;
  margin-bottom: 0.62rem;
}

.card-icon {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--color-border) 85%, transparent);
  background: color-mix(in srgb, var(--color-surface-1) 54%, transparent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
}

.status-loader {
  color: var(--color-text-secondary);
  animation: spin 0.9s linear infinite;
}

.status-headline {
  margin: 0;
  font-size: 0.92rem;
  font-weight: 620;
  line-height: 1.35;
  color: var(--color-text-primary);
}

.status-meta {
  margin: 0.28rem 0 0;
  font-size: 0.74rem;
  line-height: 1.35;
  color: var(--color-text-secondary);
}

.dev-retry-hint {
  margin: 0.5rem 0 0;
  font-size: 0.66rem;
  color: color-mix(in srgb, var(--color-text-secondary) 88%, transparent);
}

.error-block {
  margin-top: 0.75rem;
}

.error-text {
  margin: 0 0 0.62rem;
  font-size: 0.74rem;
  line-height: 1.4;
  color: var(--color-danger);
}

.retry-btn {
  width: 100%;
  padding: 0.48rem 0.85rem;
  font-size: 0.82rem;
}

.progress-block {
  padding: 0.72rem 0.9rem 0.86rem;
  border-top: 1px solid color-mix(in srgb, var(--color-border) 84%, transparent);
  background: color-mix(in srgb, var(--color-surface-1) 28%, transparent);
}

.progress-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 0.42rem;
}

.progress-pill {
  border: 1px solid color-mix(in srgb, var(--color-primary) 34%, var(--color-border));
  border-radius: 999px;
  padding: 0.12rem 0.46rem;
  color: color-mix(in srgb, var(--color-primary) 80%, white 12%);
  font-size: 0.64rem;
  line-height: 1.2;
  font-weight: 600;
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
}

.progress-outer {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-surface-2) 80%, transparent);
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
}

.progress-inner {
  height: 100%;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-primary) 65%, transparent),
    var(--color-primary)
  );
  box-shadow: 0 0 12px color-mix(in srgb, var(--color-primary) 36%, transparent);
  border-radius: 999px;
  transition: width 0.12s ease-out;
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
