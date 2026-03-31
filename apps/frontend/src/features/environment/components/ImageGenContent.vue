<template>
  <div class="image-gen-content">
    <!-- 头部 -->
    <div class="content-header">
      <div class="header-info">
        <h2 class="flex items-center gap-2">
          <ImageIcon :size="24" />
          {{ t.models.imageGen?.title || '图像生成' }}
        </h2>
        <p class="subtitle">{{ t.models.imageGen?.subtitle || '本地图像生成与编辑' }}</p>
      </div>
      <div class="header-actions">
        <div class="header-status" :class="{ ready: hasInstalledModels }">
          <span v-if="hasInstalledModels" class="flex items-center gap-1">
            <CheckCircle2 :size="16" />
            {{ installedModels.length }} 个模型已安装
          </span>
          <span v-else class="flex items-center gap-1">
            <AlertTriangle :size="16" />
            请先下载模型
          </span>
        </div>
        <!-- 服务控制 -->
        <button 
          v-if="hasInstalledModels && !serviceStatus.running"
          class="service-btn start"
          :disabled="loading.starting || !serviceStatus.canStart"
          @click="handleStartService"
        >
          <Play :size="16" />
          启动服务
        </button>
        <button 
          v-if="serviceStatus.running"
          class="service-btn stop"
          :disabled="loading.stopping"
          @click="handleStopService"
        >
          <Square :size="16" />
          停止服务
        </button>
      </div>
    </div>
    
    <!-- 镜像加速设置 -->
    <div class="mirror-setting">
      <label class="mirror-toggle" title="使用镜像加速下载 (ghproxy.com)">
        <input type="checkbox" :checked="useMirror" @change="handleMirrorToggle" />
        <span>镜像加速下载</span>
      </label>
      <span class="mirror-hint">使用 ghproxy.com 加速 GitHub 下载</span>
    </div>
    
    <!-- 任务类型标签页 -->
    <div class="task-type-tabs">
      <button 
        v-for="tab in taskTypeTabs" 
        :key="tab.id"
        class="tab-btn"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        <component :is="tab.icon" :size="16" />
        {{ tab.label }}
      </button>
    </div>
    
    <!-- 模型列表 -->
    <div class="models-section">
      <h3>{{ currentTabLabel }} 模型</h3>
      
      <div class="model-cards">
        <div 
          v-for="model in filteredModels" 
          :key="model.id"
          class="model-card"
          :class="{ 
            installed: model.installed, 
            downloading: isDownloading(model.id)
          }"
        >
          <div class="model-header">
            <h4>{{ model.name }}</h4>
            <div class="model-tags">
              <span 
                v-for="tag in model.tags" 
                :key="tag" 
                class="tag"
                :class="{ recommended: tag === '推荐' }"
              >
                {{ tag }}
              </span>
            </div>
          </div>
          
          <p class="model-desc">{{ model.description }}</p>
          
          <div class="model-meta">
            <span class="flex items-center gap-1">
              <HardDrive :size="14" />
              {{ model.sizeGb }} GB
            </span>
            <span class="flex items-center gap-1">
              <Cpu :size="14" />
              需要 {{ model.vramRequiredGb }} GB 显存
            </span>
          </div>
          
          <div class="model-workflows">
            <span class="label">推荐工作流:</span>
            <span 
              v-for="wf in getWorkflowsForModel(model)" 
              :key="wf.id"
              class="workflow-badge"
            >
              {{ wf.name }}
            </span>
          </div>
          
          <div class="model-actions">
            <!-- 未安装且未下载：显示下载按钮 -->
            <button 
              v-if="!model.installed && !isDownloading(model.id)"
              class="download-btn ui-btn ui-btn--emphasis flex items-center gap-1"
              @click="handleDownload(model.id)"
            >
              <Download :size="16" />
              下载
            </button>
            
            <!-- 下载中：显示状态 -->
            <span 
              v-else-if="isDownloading(model.id)" 
              class="downloading-badge flex items-center gap-1"
            >
              <Loader2 :size="14" class="animate-spin" />
              下载中...
            </span>
            
            <!-- 已安装 -->
            <div v-else-if="model.installed" class="installed-actions flex items-center gap-2">
              <span class="installed-badge flex items-center gap-1">
                <CheckCircle2 :size="16" />
                已安装
              </span>
              <button 
                class="delete-btn" 
                @click="handleDelete(model.id)"
                title="删除模型"
              >
                <Trash2 :size="14" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 可用工作流 -->
    <div class="workflows-section">
      <h3>可用工作流</h3>
      <p class="hint">下载对应模型后，工作流将自动可用</p>
      
      <div class="workflow-cards">
        <div 
          v-for="wf in filteredWorkflows" 
          :key="wf.id"
          class="workflow-card"
          :class="{ disabled: !wf.available }"
        >
          <div class="workflow-icon">
            <component :is="getTaskTypeIcon(wf.taskType)" :size="24" />
          </div>
          <div class="workflow-info">
            <h4>{{ wf.name }}</h4>
            <p>{{ wf.description }}</p>
          </div>
          <span v-if="!wf.available" class="missing-hint">
            需要: {{ wf.missingModels.join(', ') }}
          </span>
          <span v-else class="available-badge">
            <CheckCircle2 :size="14" />
            可用
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  Image as ImageIcon,
  CheckCircle2,
  AlertTriangle,
  Download,
  Play,
  Square,
  Trash2,
  HardDrive,
  Cpu,
  Type,
  ImagePlus,
  Paintbrush,
  Maximize,
  Video,
  Loader2
} from 'lucide-vue-next'
import { useImageGenStore } from '@/stores/imageGenStore'
import { useI18n } from '@/composables/useI18n'
import { getProviderMirrorEnabled, setProviderMirrorEnabled } from '@/composables/useResourceAccessMirror'
import { logger } from '@/utils/logger'
import type { ImageGenTaskType, ImageGenModel } from '@/types/environment'

const { t } = useI18n()
const imageGenStore = useImageGenStore()

// Active task type tab
const activeTab = ref<ImageGenTaskType | 'all'>('all')

// Mirror acceleration setting (stored in store for persistence)
const useMirror = ref(true)

// Task type tabs configuration
const taskTypeTabs = computed(() => [
  { id: 'all' as const, label: '全部', icon: ImageIcon },
  { id: 'text_to_image' as ImageGenTaskType, label: '文生图', icon: Type },
  { id: 'image_to_image' as ImageGenTaskType, label: '图生图', icon: ImagePlus },
  { id: 'inpaint' as ImageGenTaskType, label: '局部重绘', icon: Paintbrush },
  { id: 'upscale' as ImageGenTaskType, label: '超分辨率', icon: Maximize },
  { id: 'video_gen' as ImageGenTaskType, label: '视频生成', icon: Video }
])

// Get icon component for task type
const getTaskTypeIcon = (taskType: ImageGenTaskType) => {
  const icons: Record<ImageGenTaskType, any> = {
    text_to_image: Type,
    image_to_image: ImagePlus,
    inpaint: Paintbrush,
    upscale: Maximize,
    video_gen: Video
  }
  return icons[taskType] || ImageIcon
}

// Current tab label
const currentTabLabel = computed(() => {
  const tab = taskTypeTabs.value.find(t => t.id === activeTab.value)
  return tab?.label || '全部'
})

// Store state
const models = computed(() => imageGenStore.models)
const workflows = computed(() => imageGenStore.workflows)
const serviceStatus = computed(() => imageGenStore.serviceStatus)
const loading = computed(() => imageGenStore.loading)
const downloadProgress = computed(() => imageGenStore.downloadProgress)

// Computed
const installedModels = computed(() => imageGenStore.installedModels)
const hasInstalledModels = computed(() => imageGenStore.hasModelsInstalled)

const filteredModels = computed(() => {
  if (activeTab.value === 'all') {
    return models.value
  }
  return models.value.filter(m => 
    m.types.includes(activeTab.value as ImageGenTaskType)
  )
})

const filteredWorkflows = computed(() => {
  if (activeTab.value === 'all') {
    return workflows.value
  }
  return workflows.value.filter(w => 
    w.taskType === activeTab.value
  )
})

// Methods
const getWorkflowsForModel = (model: ImageGenModel) => {
  return workflows.value.filter(w => 
    model.recommendedWorkflows.includes(w.id)
  )
}

const isDownloading = (modelId: string): boolean => {
  const progress = downloadProgress.value.get(modelId)
  return progress?.status === 'downloading' || progress?.status === 'pending'
}

const handleDownload = async (modelId: string) => {
  try {
    await imageGenStore.downloadModel(modelId, useMirror.value)
  } catch (error: any) {
    logger.error('Download failed:', error)
  }
}

async function handleMirrorToggle(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  useMirror.value = checked
  await setProviderMirrorEnabled('github', checked)
}

const handleDelete = async (modelId: string) => {
  if (!confirm('确定要删除这个模型吗？')) return
  
  try {
    await imageGenStore.deleteModel(modelId)
  } catch (error: any) {
    logger.error('Delete failed:', error)
  }
}

const handleStartService = async () => {
  try {
    await imageGenStore.startService()
  } catch (error: any) {
    logger.error('Start service failed:', error)
  }
}

const handleStopService = async () => {
  try {
    await imageGenStore.stopService()
  } catch (error: any) {
    logger.error('Stop service failed:', error)
  }
}

// Lifecycle
onMounted(async () => {
  useMirror.value = await getProviderMirrorEnabled('github')
  await imageGenStore.initialize()
})
</script>

<style scoped>
.image-gen-content {
  padding: 1.5rem;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
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

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
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

.service-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 8px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.service-btn.start {
  background: var(--color-success, #22c55e);
  color: white;
}

.service-btn.stop {
  background: var(--color-error, #ef4444);
  color: white;
}

.service-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Mirror Setting */
.mirror-setting {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.mirror-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--color-text-primary);
  cursor: pointer;
  user-select: none;
}

.mirror-toggle input {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
}

.mirror-hint {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

/* Task Type Tabs */
.task-type-tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
  overflow-x: auto;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.tab-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.tab-btn.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: white;
}

/* Models Section */
.models-section h3,
.workflows-section h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: var(--color-text-primary);
}

.model-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.model-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 1.25rem;
  transition: all 0.2s;
}

.model-card:hover {
  border-color: var(--color-primary);
}

.model-card.installed {
  border-color: var(--color-success, #22c55e);
}

.model-card.downloading {
  border-color: var(--color-primary);
}

.model-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.75rem;
}

.model-header h4 {
  margin: 0;
  font-size: 1rem;
  color: var(--color-text-primary);
}

.model-tags {
  display: flex;
  gap: 0.25rem;
}

.tag {
  padding: 0.2rem 0.5rem;
  background: var(--color-bg);
  border-radius: 4px;
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}

.tag.recommended {
  background: rgba(99, 102, 241, 0.1);
  color: var(--color-primary);
}

.model-desc {
  margin: 0 0 0.75rem 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.model-meta {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.75rem;
  font-size: 0.8rem;
  color: var(--color-text-disabled);
}

.model-workflows {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.model-workflows .label {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.workflow-badge {
  padding: 0.2rem 0.5rem;
  background: rgba(99, 102, 241, 0.1);
  border-radius: 4px;
  font-size: 0.7rem;
  color: var(--color-primary);
}

.model-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.download-btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 6px;
  font-weight: 500;
}

.downloading-badge {
  padding: 0.5rem 1rem;
  background: rgba(99, 102, 241, 0.1);
  border-radius: 6px;
  font-size: 0.875rem;
  color: var(--color-primary);
}

.downloading-badge .animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.installed-badge {
  color: var(--color-success, #22c55e);
  font-size: 0.875rem;
}

.delete-btn {
  padding: 0.4rem;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.delete-btn:hover {
  border-color: var(--color-error, #ef4444);
  color: var(--color-error, #ef4444);
}

/* Workflows Section */
.workflows-section {
  margin-top: 1.5rem;
}

.workflows-section .hint {
  margin: 0 0 1rem 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.workflow-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.75rem;
}

.workflow-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  transition: all 0.2s;
}

.workflow-card.disabled {
  opacity: 0.5;
}

.workflow-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  background: var(--color-bg);
  border-radius: 8px;
  color: var(--color-text-secondary);
}

.workflow-info {
  flex: 1;
}

.workflow-info h4 {
  margin: 0 0 0.25rem 0;
  font-size: 0.9rem;
  color: var(--color-text-primary);
}

.workflow-info p {
  margin: 0;
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}

.missing-hint {
  font-size: 0.7rem;
  color: var(--color-warning, #f59e0b);
  white-space: nowrap;
}

.available-badge {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: var(--color-success, #22c55e);
}
</style>
