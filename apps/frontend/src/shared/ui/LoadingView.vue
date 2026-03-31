<template>
  <div class="shell-view">
    <div class="shell-panel">
      <div class="shell-header">
        <div class="brand-mark">
          <img src="/logo.png" alt="DawnChat" class="brand-logo" />
        </div>
        <div>
          <h1 class="app-title">DawnChat</h1>
          <p class="app-subtitle">{{ t.loading.subtitle }}</p>
        </div>
      </div>

      <div class="status-card">
        <div class="status-badge">
          <Brain :size="18" />
          <span>{{ statusText }}</span>
        </div>
        <div class="loading-spinner"></div>
        <p class="status-text">{{ statusText }}</p>
        <div v-if="props.status.retryCount > 0" class="retry-info">
          <span>{{ t.loading.retryCount.replace('{current}', String(props.status.retryCount)).replace('{max}', String(props.status.maxRetries || maxRetries)) }}</span>
        </div>
        <div v-if="props.status.error" class="error-section">
          <p class="error-text">{{ props.status.error }}</p>
          <button @click="props.retry" class="retry-button">
            {{ t.loading.retry }}
          </button>
        </div>
      </div>
      
      <div class="progress-section">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${progressPercentage}%` }"></div>
        </div>
        <p class="progress-text">{{ progressText }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Brain } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import type { BackendStatus } from '@/composables/useBackendStatus'

const props = defineProps<{
  status: BackendStatus
  retry: () => void
}>()

const { t } = useI18n()
const maxRetries = 30

const statusText = computed(() => {
  if (props.status.error) {
    return t.value.loading.connectionFailed
  }
  if (props.status.isReady) {
    return t.value.loading.serviceReady
  }
  if (props.status.phase === 'backend_restarting') {
    return t.value.loading.connectingService
  }
  if (props.status.retryCount === 0) {
    return t.value.loading.detectingService
  }
  return t.value.loading.connectingService
})

const progressPercentage = computed(() => {
  if (props.status.isReady) {
    return 100
  }
  if (props.status.error) {
    return 0
  }
  return Math.min((props.status.retryCount / maxRetries) * 100, 95)
})

const progressText = computed(() => {
  if (props.status.isReady) {
    return t.value.loading.loadingApp
  }
  if (props.status.error) {
    return t.value.loading.timeout
  }
  if (props.status.phase === 'backend_restarting') {
    return '正在恢复本地服务，请稍候…'
  }
  return t.value.loading.startingService.replace('{seconds}', props.status.retryCount.toString())
})
</script>

<style scoped>
.shell-view {
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  background:
    radial-gradient(circle at top, rgba(99, 102, 241, 0.16), transparent 42%),
    linear-gradient(135deg, #f8fafc 0%, #eef2ff 45%, #e0f2fe 100%);
  color: #0f172a;
}

.shell-panel {
  width: min(100%, 480px);
  padding: 2rem;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(16px);
}

.shell-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.75rem;
}

.brand-mark {
  width: 64px;
  height: 64px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(79, 70, 229, 0.12), rgba(56, 189, 248, 0.18));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
}

.brand-logo {
  width: 42px;
  height: 42px;
  object-fit: contain;
}

.app-title {
  font-size: 1.8rem;
  font-weight: 700;
  margin: 0 0 0.25rem 0;
  color: #0f172a;
}

.app-subtitle {
  font-size: 0.95rem;
  color: #64748b;
  margin: 0;
}

.status-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1.5rem;
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.9), rgba(241, 245, 249, 0.92));
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0.75rem;
  border-radius: 999px;
  margin-bottom: 1rem;
  background: rgba(79, 70, 229, 0.08);
  color: #4338ca;
  font-size: 0.88rem;
  font-weight: 600;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(79, 70, 229, 0.12);
  border-top: 3px solid #4f46e5;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 1rem auto;
}

.status-text {
  font-size: 1.1rem;
  margin: 0 0 0.5rem 0;
  font-weight: 500;
  color: #0f172a;
}

.retry-info {
  font-size: 0.9rem;
  color: #64748b;
  margin-bottom: 1rem;
}

.error-section {
  margin-top: 1rem;
}

.error-text {
  color: #dc2626;
  font-size: 0.9rem;
  margin-bottom: 1rem;
}

.retry-button {
  background: #4f46e5;
  border: 1px solid #4338ca;
  color: white;
  padding: 0.65rem 1rem;
  border-radius: 12px;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 600;
  transition: all 0.2s ease;
}

.retry-button:hover {
  background: #4338ca;
}

.progress-section {
  margin-top: 1.5rem;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 0.75rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4f46e5 0%, #06b6d4 100%);
  border-radius: 999px;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 0.85rem;
  color: #64748b;
  margin: 0;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@media (prefers-color-scheme: dark) {
  .shell-view {
    background:
      radial-gradient(circle at top, rgba(99, 102, 241, 0.2), transparent 42%),
      linear-gradient(135deg, #0f172a 0%, #111827 45%, #172554 100%);
    color: #e2e8f0;
  }

  .shell-panel {
    background: rgba(15, 23, 42, 0.86);
    border-color: rgba(148, 163, 184, 0.12);
    box-shadow: 0 24px 60px rgba(2, 6, 23, 0.5);
  }

  .app-title,
  .status-text {
    color: #f8fafc;
  }

  .app-subtitle,
  .retry-info,
  .progress-text {
    color: #94a3b8;
  }

  .status-card {
    background: linear-gradient(180deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.92));
    border-color: rgba(148, 163, 184, 0.1);
  }

  .status-badge {
    background: rgba(99, 102, 241, 0.14);
    color: #c7d2fe;
  }

  .progress-bar {
    background: rgba(148, 163, 184, 0.14);
  }

  .error-text {
    color: #fca5a5;
  }
}
</style>
