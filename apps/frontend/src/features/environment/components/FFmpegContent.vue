<template>
  <div class="ffmpeg-content">
    <!-- 头部 -->
    <div class="content-header">
      <div class="header-info">
        <h2 class="flex items-center gap-2">
          <Film :size="24" />
          {{ t.models.ffmpeg.title }}
        </h2>
        <p class="subtitle">{{ t.models.ffmpeg.subtitle }}</p>
      </div>
      <div class="header-status" :class="{ ready: isInstalled }">
        <span v-if="isInstalled" class="flex items-center gap-1">
          <CheckCircle2 :size="14" />
          {{ t.models.ffmpeg.installed }}
        </span>
        <span v-else class="flex items-center gap-1">
          <AlertTriangle :size="14" />
          {{ t.models.ffmpeg.notInstalled }}
        </span>
      </div>
    </div>
    
    <!-- 安装状态 -->
    <div class="install-section">
      <div class="install-card" :class="{ installed: isInstalled }">
        <div class="card-icon">
          <CheckCircle2 v-if="isInstalled" :size="32" />
          <Loader2 v-else-if="isInstalling" :size="32" class="animate-spin" />
          <Film v-else :size="32" />
        </div>
        
        <div class="card-content">
          <h3>FFmpeg</h3>
          <p class="card-desc">
            {{ t.models.ffmpeg.features.title }}
          </p>
          <ul class="feature-list">
            <li>
              <Video :size="14" class="inline-icon" />
              {{ t.models.ffmpeg.features.video }}
            </li>
            <li>
              <Music :size="14" class="inline-icon" />
              {{ t.models.ffmpeg.features.audio }}
            </li>
            <li>
              <Image :size="14" class="inline-icon" />
              {{ t.models.ffmpeg.features.image }}
            </li>
            <li>
              <Volume2 :size="14" class="inline-icon" />
              {{ t.models.ffmpeg.features.format }}
            </li>
          </ul>
          
          <div v-if="isInstalled" class="installed-info">
            <CheckCircle2 :size="20" class="check-icon" />
            <span>{{ t.models.ffmpeg.status.ready }}</span>
          </div>
          
          <div v-else-if="isInstalling" class="installing-info">
            <div class="progress-bar">
              <div class="progress-fill indeterminate"></div>
            </div>
            <span>{{ t.models.ffmpeg.status.installing }}</span>
          </div>
          
          <div v-else class="install-action">
            <p class="install-note">
              {{ t.models.ffmpeg.status.note }}
            </p>
            <button class="primary-btn ui-btn ui-btn--emphasis flex items-center gap-2" @click="handleInstall">
              <Download :size="16" />
              {{ t.models.ffmpeg.installNow }}
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 说明信息 -->
    <div class="info-section">
      <div class="info-card">
        <h4 class="flex items-center gap-2">
          <Lightbulb :size="16" />
          {{ t.models.ffmpeg.about.title }}
        </h4>
        <p>
          {{ t.models.ffmpeg.about.content }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useToolsStore } from '@/stores/toolsStore'
import { useI18n } from '@/composables/useI18n'

const { t } = useI18n()
import {
  Film,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Video,
  Music,
  Image,
  Volume2,
  Download,
  Lightbulb
} from 'lucide-vue-next'

const toolsStore = useToolsStore()

const isInstalled = computed(() => toolsStore.ffmpegInstalled)
const isInstalling = computed(() => toolsStore.ffmpegInstalling)

const handleInstall = async () => {
  await toolsStore.installFFmpeg()
}

onMounted(async () => {
  await toolsStore.checkFFmpegStatus()
})
</script>

<style scoped>
.ffmpeg-content {
  padding: 1.5rem;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.header-info h2 {
  margin: 0 0 0.25rem 0;
  font-size: 1.25rem;
  color: var(--color-text-primary);
}

.header-info .subtitle {
  margin: 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.header-status {
  padding: 0.5rem 1rem;
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.1));
  border-radius: 8px;
  font-size: 0.875rem;
  color: var(--color-warning, #f59e0b);
}

.header-status.ready {
  background: var(--color-success-bg, rgba(34, 197, 94, 0.1));
  color: var(--color-success, #22c55e);
}

.install-section {
  margin-bottom: 1.5rem;
}

.install-card {
  display: flex;
  gap: 1.5rem;
  padding: 1.5rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 12px;
}

.install-card.installed {
  border-color: var(--color-success, #22c55e);
  background: linear-gradient(135deg, var(--color-bg-secondary) 0%, rgba(34, 197, 94, 0.05) 100%);
}

.card-icon {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  padding-top: 0.5rem;
  color: var(--color-text-secondary);
}

.install-card.installed .card-icon {
  color: var(--color-success);
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.card-content {
  flex: 1;
}

.card-content h3 {
  margin: 0 0 0.5rem 0;
  font-size: 1.25rem;
  color: var(--color-text-primary);
}

.card-desc {
  margin: 0 0 1rem 0;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
}

.feature-list {
  margin: 0 0 1.5rem 0;
  padding-left: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.5rem;
}

.inline-icon {
  display: inline-block;
  vertical-align: middle;
  margin-right: 0.25rem;
  color: var(--color-text-secondary);
}

.feature-list li {
  display: flex;
  align-items: center;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  padding: 0.5rem 0.75rem;
  background: var(--color-bg);
  border-radius: 6px;
}

.installed-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem;
  background: var(--color-success-bg, rgba(34, 197, 94, 0.1));
  border-radius: 8px;
  color: var(--color-success, #22c55e);
  font-weight: 500;
}

.check-icon {
  font-size: 1.25rem;
}

.installing-info {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--color-bg);
  border-radius: 8px;
}

.progress-bar {
  height: 6px;
  background: var(--color-border);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: 3px;
}

.progress-fill.indeterminate {
  width: 30%;
  animation: indeterminate 1.5s infinite ease-in-out;
}

@keyframes indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}

.install-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem;
  background: var(--color-bg);
  border-radius: 8px;
}

.install-note {
  margin: 0;
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}

.primary-btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  font-weight: 500;
  white-space: nowrap;
}

.info-section {
  margin-top: 1rem;
}

.info-card {
  padding: 1.25rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 12px;
}

.info-card h4 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  color: var(--color-text-primary);
}

.info-card p {
  margin: 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  line-height: 1.6;
}
</style>

