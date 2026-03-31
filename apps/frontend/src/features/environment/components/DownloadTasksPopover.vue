<template>
  <div class="download-popover-wrapper" ref="popoverRef">
    <!-- 触发按钮 -->
    <button 
      class="download-trigger"
      :class="{ 'has-tasks': activeCount > 0 }"
      @click="togglePopover"
    >
      <Download class="trigger-icon" :size="18" />
      <span class="trigger-text">{{ t.common.downloadTasks }}</span>
      <span v-if="activeCount > 0" class="trigger-badge">{{ activeCount }}</span>
    </button>
    
    <!-- 悬浮窗 -->
    <Transition name="popover">
      <div v-if="isOpen" class="download-popover">
        <div class="popover-header">
          <h3>{{ t.common.downloadTasks }} ({{ allTasks.length }})</h3>
        </div>
        
        <div class="popover-body">
          <div v-if="allTasks.length === 0" class="empty-state">
            <CheckCircle2 :size="32" class="empty-icon" />
            <span class="empty-text">{{ t.common.noDownloadTasks }}</span>
          </div>
          
          <div v-else class="tasks-list">
            <div 
              v-for="task in allTasks" 
              :key="task.id"
              class="task-item"
              :class="task.status"
            >
              <div class="task-header">
                <component :is="getCategoryIcon(task.category)" class="task-icon" :size="16" />
                <span class="task-name">{{ task.name }}</span>
                <span class="task-progress">{{ task.progress.toFixed(1) }}%</span>
              </div>
              
              <div class="progress-bar">
                <div 
                  class="progress-fill" 
                  :class="task.status"
                  :style="{ width: `${task.progress}%` }"
                ></div>
              </div>
              
              <div class="task-info">
                <span class="task-size">
                  <!-- 多文件下载（TTS/ASR/Repo）：显示文件进度 + 当前文件信息 -->
                  <template v-if="task.extra?.totalFiles && task.extra.totalFiles > 1">
                    <span>{{ task.extra.downloadedFiles }}/{{ task.extra.totalFiles }} {{ t.models.files }}</span>
                    <!-- TTS/ASR: 显示当前文件进度 -->
                    <template v-if="task.extra.currentFileSize && task.extra.currentFileSize > 0">
                      <span class="current-file-progress">
                        ({{ formatSize(task.extra.currentFileDownloaded || 0) }} / {{ formatSize(task.extra.currentFileSize) }})
                      </span>
                    </template>
                    <!-- Repo 下载: 显示总字节进度 -->
                    <template v-else-if="task.totalSize > 0">
                      <span class="current-file-progress">
                        ({{ formatSize(task.downloadedSize) }} / {{ formatSize(task.totalSize) }})
                      </span>
                    </template>
                  </template>
                  <!-- 单文件下载（LLM）：显示字节进度 -->
                  <template v-else-if="task.totalSize > 0">
                    {{ formatSize(task.downloadedSize) }} / {{ formatSize(task.totalSize) }}
                  </template>
                  <!-- 无进度信息 -->
                  <template v-else>
                    {{ task.message || getStatusText(task.status) }}
                  </template>
                </span>
                <span v-if="task.speed" class="task-speed">{{ task.speed }}</span>
              </div>
              
              <!-- 错误信息显示 -->
              <div v-if="task.status === 'failed' && task.errorMessage" class="task-error">
                <AlertTriangle :size="14" class="error-icon" />
                <span class="error-text">{{ task.errorMessage }}</span>
              </div>
              
              <div class="task-actions">
                <template v-if="task.status === 'downloading' || task.status === 'pending'">
                  <button class="action-btn pause" @click="handlePause(task)" :title="t.common.pause">
                    <Pause :size="14" />
                  </button>
                </template>
                <template v-else-if="task.status === 'paused'">
                  <button class="action-btn resume" @click="handleResume(task)" :title="t.common.resume">
                    <Play :size="14" />
                  </button>
                </template>
                <template v-else-if="task.status === 'failed'">
                  <button class="action-btn retry" @click="handleRetry(task)" :title="t.common.retry">
                    <RefreshCcw :size="14" />
                  </button>
                </template>
                <button 
                  class="action-btn cancel" 
                  @click="handleCancel(task)" 
                  :title="t.common.cancel"
                  v-if="!['completed', 'cancelled'].includes(task.status)"
                >
                  <X :size="14" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useEnvironmentStore } from '@/features/environment/store'
import type { UnifiedDownloadTask, EnvironmentCategory } from '@/types/environment'
import { useI18n } from '@/composables/useI18n'
import { 
  Download, 
  CheckCircle2, 
  AlertTriangle, 
  Pause, 
  Play, 
  RefreshCcw, 
  X, 
  Bot, 
  Volume2, 
  Mic, 
  Film, 
  Package,
  Image as ImageIcon
} from 'lucide-vue-next'

const { t } = useI18n()
const environmentStore = useEnvironmentStore()

const popoverRef = ref<HTMLElement | null>(null)
const isOpen = ref(false)

const allTasks = computed(() => {
  // 只显示进行中、暂停和失败的任务
  return environmentStore.allDownloadTasks.filter(t => 
    ['pending', 'downloading', 'paused', 'failed'].includes(t.status)
  )
})

const activeCount = computed(() => environmentStore.activeDownloadCount)

const togglePopover = () => {
  isOpen.value = !isOpen.value
}

const closePopover = () => {
  isOpen.value = false
}

const getCategoryIcon = (category: EnvironmentCategory | 'ffmpeg') => {
  const icons: Record<string, any> = {
    llm: Bot,
    tts: Volume2,
    asr: Mic,
    ffmpeg: Film,
    image_gen: ImageIcon
  }
  return icons[category] || Package
}

const getStatusText = (status: string): string => {
  const texts: Record<string, string> = {
    pending: t.value.common.pending,
    downloading: t.value.common.downloading,
    paused: t.value.common.paused,
    completed: t.value.common.completed,
    failed: t.value.common.failed,
    cancelled: t.value.common.cancelled
  }
  return texts[status] || status
}

const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}


const handlePause = async (task: UnifiedDownloadTask) => {
  await environmentStore.pauseTask(task)
}

const handleResume = async (task: UnifiedDownloadTask) => {
  await environmentStore.resumeTask(task)
}

const handleCancel = async (task: UnifiedDownloadTask) => {
  await environmentStore.cancelTask(task)
}

const handleRetry = async (task: UnifiedDownloadTask) => {
  await environmentStore.retryTask(task)
}

// 点击外部关闭
const handleClickOutside = (event: MouseEvent) => {
  if (popoverRef.value && !popoverRef.value.contains(event.target as Node)) {
    closePopover()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.download-popover-wrapper {
  position: relative;
}

.download-trigger {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  transition: all 0.2s;
}

.download-trigger:hover {
  background: var(--color-hover);
  color: var(--color-text-primary);
}

.download-trigger.has-tasks {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.trigger-icon {
  font-size: 1rem;
}

.trigger-text {
  font-weight: 500;
}

.trigger-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: var(--color-danger, #ef4444);
  color: white;
  border-radius: 9px;
  font-size: 0.7rem;
  font-weight: 600;
}

.download-popover {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 360px;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
  z-index: 100;
  overflow: hidden;
}

.popover-header {
  padding: 1rem;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.popover-header h3 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.popover-body {
  max-height: 400px;
  overflow-y: auto;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 2rem;
  color: var(--color-text-secondary);
}

.empty-icon {
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.empty-text {
  font-size: 0.875rem;
}

.tasks-list {
  padding: 0.5rem;
}

.task-item {
  padding: 0.75rem;
  border-radius: 8px;
  background: var(--color-bg-secondary);
  margin-bottom: 0.5rem;
}

.task-item:last-child {
  margin-bottom: 0;
}

.task-item.paused {
  opacity: 0.8;
  border-left: 3px solid var(--color-warning, #f59e0b);
}

.task-item.failed {
  border-left: 3px solid var(--color-danger, #ef4444);
}

.task-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.task-icon {
  font-size: 1rem;
}

.task-name {
  flex: 1;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-progress {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-primary);
}

.progress-bar {
  height: 6px;
  background: var(--color-border);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), #667eea);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress-fill.paused {
  background: linear-gradient(90deg, var(--color-warning, #f59e0b), #fbbf24);
}

.progress-fill.failed {
  background: var(--color-danger, #ef4444);
}

.task-info {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.5rem;
}

.task-speed {
  color: var(--color-success, #22c55e);
}

.current-file-progress {
  color: var(--color-text-tertiary, #888);
  font-size: 0.7rem;
  margin-left: 0.25rem;
}

.task-actions {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

.action-btn {
  padding: 0.25rem 0.5rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.2s;
  background: var(--color-bg);
}

.action-btn:hover {
  transform: scale(1.1);
}

.action-btn.pause {
  color: var(--color-warning, #f59e0b);
}

.action-btn.resume {
  color: var(--color-success, #22c55e);
}

.action-btn.cancel {
  color: var(--color-danger, #ef4444);
}

.action-btn.retry {
  color: var(--color-primary);
}

/* 错误信息样式 */
.task-error {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  padding: 0.5rem;
  margin-bottom: 0.5rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
}

.task-error .error-icon {
  font-size: 0.9rem;
  flex-shrink: 0;
}

.task-error .error-text {
  font-size: 0.75rem;
  color: var(--color-danger, #ef4444);
  line-height: 1.4;
  word-break: break-word;
}

/* Transition */
.popover-enter-active,
.popover-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}

.popover-enter-from,
.popover-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* 滚动条样式 */
.popover-body::-webkit-scrollbar {
  width: 6px;
}

.popover-body::-webkit-scrollbar-track {
  background: transparent;
}

.popover-body::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 3px;
}
</style>

