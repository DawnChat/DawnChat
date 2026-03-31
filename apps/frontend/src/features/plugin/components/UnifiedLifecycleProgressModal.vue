<template>
  <div v-if="visible" class="modal-mask" @click.self="onClose">
    <div class="modal-panel">
      <div class="header">
        <div class="header-copy">
          <h3>{{ title }}</h3>
          <p class="sub">{{ progress.message || '-' }}</p>
        </div>
        <div class="header-right">
          <span class="progress-pill">{{ progressLabel }}</span>
          <button class="icon-btn" @click="onClose">×</button>
        </div>
      </div>

      <div class="body">
        <div class="progress-outer">
          <div class="progress-inner" :style="{ width: `${progressPercent}%` }" />
        </div>
        <div class="meta">
          <span>{{ progress.stage_label || '处理中' }}</span>
          <span v-if="progress.eta_seconds && taskStatus === 'running'">约 {{ progress.eta_seconds }}s</span>
        </div>

        <div v-if="(progress.details || []).length > 0" class="timeline">
          <div v-for="item in (progress.details || []).slice(-5)" :key="item" class="detail-row">{{ item }}</div>
        </div>

        <div v-if="taskErrorMessage" class="error">
          {{ taskErrorMessage }}
        </div>
      </div>

      <div class="footer">
        <button class="btn-secondary ui-btn ui-btn--neutral" @click="onClose">后台运行</button>
        <button v-if="taskStatus === 'running' || taskStatus === 'pending'" class="btn-danger ui-btn ui-btn--danger" @click="$emit('cancel')">取消</button>
        <button v-if="taskStatus === 'failed' && progress.retryable" class="btn-primary ui-btn ui-btn--emphasis" @click="$emit('retry')">重试</button>
        <button v-if="taskStatus === 'completed'" class="btn-primary ui-btn ui-btn--emphasis" @click="$emit('done')">完成</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { LifecycleTask } from '@/features/plugin/store'
import { useLifecycleProgressSmoothing } from '@/features/plugin/composables/useLifecycleProgressSmoothing'

const props = defineProps<{
  visible: boolean
  task: LifecycleTask | null
}>()

const emit = defineEmits<{
  close: []
  cancel: []
  retry: []
  done: []
}>()

const task = computed(() => props.task || null)
const progress = computed(() => task.value?.progress || {
  stage: '',
  stage_label: '',
  progress: 0,
  message: '',
  eta_seconds: null,
  retryable: false,
  details: []
})
const taskStatus = computed(() => task.value?.status || 'pending')
const taskErrorMessage = computed(() => task.value?.error?.message || '')
const taskId = computed(() => task.value?.task_id || '')
const rawProgress = computed(() => progress.value.progress || 0)
const { progressPercent, progressLabel } = useLifecycleProgressSmoothing({
  visible: computed(() => props.visible),
  taskId,
  rawProgress,
  taskStatus,
})

const title = computed(() => {
  const kind = task.value?.operation_type || ''
  if (kind === 'create_dev_session') return '创建并启动开发模式'
  if (kind === 'start_dev_session') return '启动开发模式'
  if (kind === 'restart_dev_session') return '重启开发预览'
  if (kind === 'start_runtime') return '启动应用'
  return '任务执行中'
})

const onClose = () => emit('close')
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--color-app-canvas) 36%, rgba(5, 10, 20, 0.72));
  backdrop-filter: blur(5px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1400;
  padding: 1rem;
}

.modal-panel {
  width: min(640px, calc(100vw - 1.4rem));
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  border-radius: 14px;
  background: color-mix(in srgb, var(--color-surface-2) 90%, var(--color-app-canvas));
  box-shadow: 0 24px 62px rgba(15, 23, 42, 0.42);
  overflow: hidden;
}

.header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.8rem;
  padding: 0.92rem 1.05rem 0.86rem;
  border-bottom: 1px solid color-mix(in srgb, var(--color-border) 84%, transparent);
}

.header-copy h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 620;
  line-height: 1.3;
  color: var(--color-text-primary);
}

.sub {
  margin: 0.2rem 0 0;
  font-size: 0.78rem;
  color: var(--color-text-secondary);
  line-height: 1.35;
  max-width: 420px;
}

.header-right {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.progress-pill {
  border: 1px solid color-mix(in srgb, var(--color-primary) 34%, var(--color-border));
  border-radius: 999px;
  padding: 0.14rem 0.5rem;
  color: color-mix(in srgb, var(--color-primary) 80%, white 12%);
  font-size: 0.68rem;
  line-height: 1.2;
  font-weight: 600;
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
}

.icon-btn {
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: color 0.18s ease, background 0.18s ease;
}

.icon-btn:hover {
  color: var(--color-text-primary);
  background: color-mix(in srgb, var(--color-surface-2) 26%, transparent);
}

.body {
  padding: 0.92rem 1.05rem 0.98rem;
}

.progress-outer {
  width: 100%;
  height: 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-surface-2) 80%, transparent);
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
}

.progress-inner {
  height: 100%;
  background: linear-gradient(90deg, color-mix(in srgb, var(--color-primary) 65%, transparent), var(--color-primary));
  box-shadow: 0 0 12px color-mix(in srgb, var(--color-primary) 36%, transparent);
}

.meta {
  margin-top: 0.52rem;
  display: flex;
  justify-content: space-between;
  gap: 0.7rem;
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}

.timeline {
  margin-top: 0.82rem;
  padding: 0.6rem 0.64rem;
  border: 1px solid color-mix(in srgb, var(--color-border) 82%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-surface-2) 32%, transparent);
}

.detail-row {
  font-size: 0.76rem;
  color: var(--color-text-secondary);
  margin-top: 0.16rem;
}

.detail-row:first-child {
  margin-top: 0;
}

.error {
  margin-top: 0.78rem;
  padding: 0.55rem 0.7rem;
  border-radius: 8px;
  border: 1px solid rgba(239, 68, 68, 0.35);
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  font-size: 0.82rem;
}

.footer {
  padding: 0.82rem 1.05rem 0.95rem;
  border-top: 1px solid color-mix(in srgb, var(--color-border) 84%, transparent);
  display: flex;
  justify-content: flex-end;
  gap: 0.44rem;
}

.btn-primary,
.btn-secondary,
.btn-danger {
  padding: 0.5rem 0.88rem;
  font-weight: 600;
}

@media (max-width: 700px) {
  .modal-mask {
    padding: 0.7rem;
    align-items: flex-end;
  }

  .modal-panel {
    width: 100%;
  }

  .header {
    padding: 0.86rem 0.9rem 0.82rem;
  }

  .body {
    padding: 0.86rem 0.9rem 0.92rem;
  }

  .footer {
    padding: 0.74rem 0.9rem 0.9rem;
  }

  .sub {
    max-width: 100%;
  }
}
</style>
