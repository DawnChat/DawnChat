<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="showEnvironmentManager" class="environment-manager-overlay" @click.self="handleClose">
        <div class="environment-manager">
          <!-- 头部 -->
          <div class="manager-header">
            <h1>
              <Package :size="24" class="inline-icon" />
              {{ t.common.manager }}
            </h1>
            <div class="header-actions">
              <DownloadTasksPopover />
              <button class="close-btn" @click="handleClose">
                <X :size="20" />
              </button>
            </div>
          </div>
          
          <!-- 主体 -->
          <div class="manager-body">
            <!-- 左侧导航 -->
            <EnvironmentNavigator />
            
            <!-- 右侧内容区 -->
            <div class="manager-content">
              <KeepAlive>
                <component :is="currentContentComponent" />
              </KeepAlive>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, watch, Teleport, KeepAlive } from 'vue'
import { useEnvironmentStore } from '@/features/environment/store'
import { Package, X } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'
import EnvironmentNavigator from './EnvironmentNavigator.vue'
import DownloadTasksPopover from './DownloadTasksPopover.vue'
import LLMModelContent from './LLMModelContent.vue'
import TTSContent from './TTSContent.vue'
import FFmpegContent from './FFmpegContent.vue'
import CloudModelsContent from './CloudModelsContent.vue'
import ImageGenContent from './ImageGenContent.vue'
import ScoringContent from './ScoringContent.vue'

const { t } = useI18n()
const environmentStore = useEnvironmentStore()

const showEnvironmentManager = computed(() => environmentStore.showEnvironmentManager)
const currentCategory = computed(() => environmentStore.currentCategory)

// 当环境管理页面打开时，自动刷新所有环境状态
watch(showEnvironmentManager, async (isVisible) => {
  if (isVisible) {
    await environmentStore.refreshAllStatus()
  }
})

const currentContentComponent = computed(() => {
  switch (currentCategory.value) {
    case 'llm':
      return LLMModelContent
    case 'tts':
      return TTSContent
    case 'ffmpeg':
      return FFmpegContent
    case 'cloud':
      return CloudModelsContent
    case 'image_gen':
      return ImageGenContent
    case 'scoring':
      return ScoringContent
    default:
      return LLMModelContent
  }
})

const handleClose = () => {
  environmentStore.closeEnvironmentManager()
}
</script>

<style scoped>
.environment-manager-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9000;
  padding: 2rem;
  backdrop-filter: blur(4px);
}

.environment-manager {
  width: 100%;
  max-width: 1200px;
  height: calc(100vh - 6rem);
  max-height: 800px;
  background: var(--color-bg);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border);
}

.manager-header h1 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.inline-icon {
  color: var(--color-primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.close-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: var(--color-bg);
  border-radius: 8px;
  cursor: pointer;
  font-size: 1.1rem;
  color: var(--color-text-secondary);
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--color-hover);
  color: var(--color-text-primary);
}

.manager-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.manager-content {
  flex: 1;
  overflow-y: auto;
  background: var(--color-bg);
}

/* Transition */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.25s ease;
}

.modal-enter-active .environment-manager,
.modal-leave-active .environment-manager {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .environment-manager,
.modal-leave-to .environment-manager {
  opacity: 0;
  transform: scale(0.95) translateY(20px);
}

/* 滚动条样式 */
.manager-content::-webkit-scrollbar {
  width: 8px;
}

.manager-content::-webkit-scrollbar-track {
  background: transparent;
}

.manager-content::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: 4px;
}

.manager-content::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-disabled);
}
</style>
