<template>
  <div class="shell-view">
    <div class="shell-panel">
      <div class="shell-header">
        <div class="brand-mark">
          <img src="/logo.png" alt="DawnChat" class="brand-logo" />
        </div>
        <div>
          <p class="eyebrow">DawnChat</p>
          <h1 class="shell-title">{{ t.loading.connectionFailed }}</h1>
        </div>
      </div>

      <div class="status-card">
        <div class="status-icon">
          <AlertTriangle :size="28" />
        </div>
        <p class="status-description">{{ status.error || t.backend.checkTimeout }}</p>
        <p class="status-hint">应用仍会继续等待本地服务恢复，你也可以立即手动重试。</p>
        <button class="retry-button" @click="retry">
          {{ t.loading.retry }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { AlertTriangle } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'
import type { BackendStatus } from '@/composables/useBackendStatus'

defineProps<{
  status: BackendStatus
  retry: () => void
}>()

const { t } = useI18n()
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
    radial-gradient(circle at top, rgba(248, 113, 113, 0.14), transparent 40%),
    linear-gradient(135deg, #f8fafc 0%, #eef2ff 42%, #fee2e2 100%);
  color: #0f172a;
}

.shell-panel {
  width: min(100%, 480px);
  padding: 2rem;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(248, 113, 113, 0.18);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(16px);
}

.shell-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.brand-mark {
  width: 64px;
  height: 64px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(248, 113, 113, 0.12), rgba(251, 191, 36, 0.16));
}

.brand-logo {
  width: 42px;
  height: 42px;
  object-fit: contain;
}

.eyebrow {
  margin: 0 0 0.35rem;
  font-size: 0.85rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #b91c1c;
}

.shell-title {
  margin: 0;
  font-size: 1.8rem;
  font-weight: 700;
  color: #0f172a;
}

.status-card {
  padding: 1.75rem;
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.92), rgba(255, 255, 255, 0.96));
  border: 1px solid rgba(248, 113, 113, 0.16);
  text-align: center;
}

.status-icon {
  width: 56px;
  height: 56px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1rem;
  color: #ef4444;
  background: rgba(254, 226, 226, 0.9);
}

.status-description {
  margin: 0 0 1.5rem;
  color: #475569;
  line-height: 1.65;
}

.status-hint {
  margin: -0.5rem 0 1.25rem;
  color: #64748b;
  font-size: 0.9rem;
  line-height: 1.6;
}

.retry-button {
  min-width: 136px;
  border: 1px solid #4338ca;
  border-radius: 12px;
  padding: 0.8rem 1.4rem;
  background: #4f46e5;
  color: white;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.retry-button:hover {
  background: #4338ca;
}

@media (prefers-color-scheme: dark) {
  .shell-view {
    background:
      radial-gradient(circle at top, rgba(248, 113, 113, 0.18), transparent 40%),
      linear-gradient(135deg, #0f172a 0%, #111827 42%, #3f1d1d 100%);
    color: #e2e8f0;
  }

  .shell-panel {
    background: rgba(15, 23, 42, 0.9);
    border-color: rgba(248, 113, 113, 0.16);
    box-shadow: 0 24px 60px rgba(2, 6, 23, 0.5);
  }

  .shell-title {
    color: #f8fafc;
  }

  .eyebrow {
    color: #fca5a5;
  }

  .status-card {
    background: linear-gradient(180deg, rgba(69, 10, 10, 0.34), rgba(30, 41, 59, 0.9));
    border-color: rgba(248, 113, 113, 0.14);
  }

  .status-icon {
    background: rgba(127, 29, 29, 0.55);
    color: #fca5a5;
  }

  .status-description {
    color: #cbd5e1;
  }

  .status-hint {
    color: #94a3b8;
  }
}
</style>
