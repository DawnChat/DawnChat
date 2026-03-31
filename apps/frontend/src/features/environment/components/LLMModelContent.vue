<template>
  <div class="llm-model-content">
    <!-- 头部 -->
    <div class="content-header">
      <div class="header-info">
        <h2 class="flex items-center gap-2">
          <Bot :size="24" />
          {{ t.models.llm.title }}
        </h2>
        <p class="subtitle">{{ t.models.llm.subtitle }}</p>
      </div>
      <div class="header-status" :class="{ ready: hasInstalledModels }">
        <span v-if="hasInstalledModels" class="flex items-center gap-1">
          <CheckCircle2 :size="14" />
          {{ t.common.installed }} {{ installedModels.length }} {{ t.models.title }}
        </span>
        <span v-else class="flex items-center gap-1">
          <AlertTriangle :size="14" />
          {{ t.common.noModelsInstalled }}
        </span>
      </div>
    </div>
    
    <!-- 搜索栏和过滤选项 -->
    <div class="search-section">
      <div class="search-bar">
        <input 
          v-model="searchInput"
          type="text"
          :placeholder="t.common.searchModels"
          @keyup.enter="handleSearch"
        />
        <button class="search-btn ui-btn ui-btn--emphasis flex items-center gap-2" @click="handleSearch">
          <Search :size="14" />
          {{ t.common.search }}
        </button>
      </div>
      
      <div class="filter-options">
        <label class="checkbox-item downloaded">
          <input 
            type="checkbox" 
            v-model="showDownloaded"
          />
          <span class="checkbox-label flex items-center gap-1">
            <Package :size="14" />
            {{ t.common.downloadedModels }}
          </span>
        </label>
        <span class="filter-divider">|</span>
        <label class="checkbox-item">
          <input 
            type="checkbox" 
            :checked="modelsStore.formatFilter.gguf"
            @change="modelsStore.setFormatFilter('gguf', ($event.target as HTMLInputElement).checked)"
          />
          <span class="checkbox-label">GGUF</span>
        </label>
        <label v-if="modelsStore.isMacOS" class="checkbox-item">
          <input 
            type="checkbox" 
            :checked="modelsStore.formatFilter.mlx"
            @change="modelsStore.setFormatFilter('mlx', ($event.target as HTMLInputElement).checked)"
          />
          <span class="checkbox-label">MLX</span>
        </label>
        <span class="filter-divider">|</span>
        <label class="checkbox-item mirror">
          <input 
            type="checkbox" 
            :checked="modelsStore.useMirror"
            @change="handleMirrorToggle"
          />
          <span class="checkbox-label flex items-center gap-1">
            <Rocket :size="14" />
            {{ t.common.useMirror }}
          </span>
        </label>
      </div>
    </div>
    
    <!-- 已下载模型列表 -->
    <div v-if="showDownloaded" class="installed-section">
      <h3 class="flex items-center gap-2">
        <Package :size="18" />
        {{ t.common.downloadedModels }} ({{ installedModels.length }})
      </h3>
      
      <div v-if="installedModels.length === 0" class="empty-installed">
        <p>{{ t.common.noDownloadedModels }}</p>
      </div>
      
      <div v-else class="installed-grid">
        <div 
          v-for="model in installedModels" 
          :key="model.id"
          class="installed-card"
        >
          <div class="installed-header">
            <span :class="['format-badge', model.format]">{{ model.format.toUpperCase() }}</span>
            <h4>{{ model.filename }}</h4>
          </div>
          <div class="installed-meta">
            <span class="size">{{ model.sizeDisplay }}</span>
            <span v-if="model.author" class="author">by {{ model.author }}</span>
          </div>
          <div v-if="model.huggingfaceId" class="installed-source">
            <span class="hf-id">{{ model.huggingfaceId }}</span>
          </div>
          <div class="installed-actions">
            <button 
              class="delete-btn flex items-center gap-2"
              :disabled="deletingModel === model.id"
              @click="confirmDeleteModel(model)"
            >
              <span v-if="deletingModel === model.id" class="flex items-center gap-1">
                <Loader2 class="animate-spin" :size="14" />
                {{ t.common.deleting }}
              </span>
              <span v-else class="flex items-center gap-1">
                <Trash2 :size="14" />
                {{ t.common.delete }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 模型列表 -->
    <div v-if="marketLoading && marketModels.length === 0" class="loading-state">
      <Loader2 class="animate-spin" :size="32" />
      <p>{{ t.common.loading }}</p>
    </div>
    
    <div v-else-if="marketError" class="error-state">
      <XCircle class="error-icon" :size="48" />
      <h3>{{ t.common.failed }}</h3>
      <p>{{ marketError }}</p>
      <button class="primary-btn ui-btn ui-btn--emphasis flex items-center gap-2" @click="retryLoadMarket">
        <RefreshCw :size="14" />
        {{ t.common.retry }}
      </button>
    </div>
    
    <div v-else-if="marketModels.length === 0" class="empty-state">
      <Search class="empty-icon" :size="48" />
      <h3>{{ t.common.noData }}</h3>
      <p>{{ t.models.market.tryOther }}</p>
    </div>
    
    <div v-else class="models-grid">
      <div 
        v-for="model in marketModels" 
        :key="model.id"
        class="model-card"
        @click="openModelDetail(model)"
      >
        <div class="model-header">
          <h3>{{ getModelDisplayName(model.id) }}</h3>
          <span class="author-badge">{{ model.author }}</span>
        </div>
        <div class="model-meta">
          <span class="meta-item">
            <Download class="icon" :size="12" />
            {{ formatNumber(model.downloads) }}
          </span>
          <span class="meta-item">
            <Heart class="icon" :size="12" />
            {{ formatNumber(model.likes) }}
          </span>
        </div>
        <div v-if="model.tags && model.tags.length > 0" class="model-tags">
          <span v-for="tag in model.tags.slice(0, 3)" :key="tag" class="tag">
            {{ tag }}
          </span>
        </div>
        <button class="detail-btn flex items-center gap-2" @click.stop="openModelDetail(model)">
          <FolderOpen :size="14" />
          {{ t.models.viewFiles }}
        </button>
      </div>
    </div>
    
    <!-- 加载更多 -->
    <div v-if="marketHasMore && marketModels.length > 0" class="load-more">
      <button 
        class="load-more-btn" 
        @click="loadMore"
        :disabled="marketLoading"
      >
        {{ marketLoading ? t.common.loading : t.common.loadMore }}
      </button>
    </div>
    
    <!-- 模型详情弹窗 -->
    <Teleport to="body">
      <div v-if="selectedModel" class="modal-overlay" @click="closeModelDetail">
        <div class="modal-content" @click.stop>
          <div class="modal-header">
            <h2>{{ getModelDisplayName(selectedModel.id) }}</h2>
            <button class="close-btn" @click="closeModelDetail"><X :size="20" /></button>
          </div>
          
          <div class="modal-body">
            <div class="model-detail-info">
              <div class="info-item">
                <span class="label">{{ t.models.author }}</span>
                <span class="value">{{ selectedModel.author }}</span>
              </div>
              <div class="info-item">
                <span class="label">{{ t.models.downloads }}</span>
                <span class="value">{{ formatNumber(selectedModel.downloads) }}</span>
              </div>
            </div>
            
            <h3 class="flex items-center gap-2">
              <FolderOpen :size="18" />
              {{ t.models.files }}
            </h3>
            <div v-if="isMlxSelected" class="repo-download-row">
              <button 
                class="download-btn ui-btn ui-btn--emphasis flex items-center gap-1"
                :disabled="isRepositoryDownloading"
                @click="handleDownloadRepository"
              >
                <span v-if="isRepositoryDownloading" class="flex items-center gap-1">
                  <Loader2 :size="14" class="animate-spin" />
                  {{ t.common.downloading }}
                </span>
                <span v-else class="flex items-center gap-1">
                  <Download :size="14" />
                  {{ t.models.downloadRepository }}
                </span>
              </button>
            </div>
            <div v-if="filesLoading" class="files-loading">
              <div class="spinner small"></div>
              <span>{{ t.models.loadingFiles }}</span>
            </div>
            <div v-else-if="filteredFiles.length === 0" class="no-files">
              <p>{{ t.models.noMatchingFiles }}</p>
            </div>
            <div v-else class="files-list">
              <div 
                v-for="file in filteredFiles" 
                :key="file.rfilename"
                class="file-item"
              >
                <div class="file-info">
                  <span class="file-name">{{ file.rfilename }}</span>
                  <div class="file-meta">
                    <span class="file-size">{{ modelsStore.formatSize(file.lfs?.size || file.size || 0) }}</span>
                    <span :class="['file-format', getFileFormat(file.rfilename)]">
                      {{ getFileFormat(file.rfilename).toUpperCase() }}
                    </span>
                  </div>
                </div>
                <button 
                  class="download-btn ui-btn ui-btn--emphasis flex items-center gap-1"
                  :disabled="isFileDownloading(file.rfilename) || isFileInstalled(file.rfilename)"
                  @click="handleDownloadFile(file)"
                >
                  <span v-if="isFileInstalled(file.rfilename)" class="flex items-center gap-1">
                    <CheckCircle2 :size="14" />
                    {{ t.common.installed }}
                  </span>
                  <span v-else-if="isFileDownloading(file.rfilename)" class="flex items-center gap-1">
                    <Loader2 :size="14" class="animate-spin" />
                    {{ t.common.downloading }}
                  </span>
                  <span v-else class="flex items-center gap-1">
                    <Download :size="14" />
                    {{ t.common.download }}
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, Teleport } from 'vue'
import { useModelHubStore, type HuggingFaceModel, type HuggingFaceFileSibling, REPO_DOWNLOAD_FILENAME } from '@/stores/modelHubStore'
import { useI18n } from '@/composables/useI18n'
import { getProviderMirrorEnabled, setProviderMirrorEnabled } from '@/composables/useResourceAccessMirror'
import { logger } from '@/utils/logger'
import { 
  Loader2, 
  XCircle, 
  RefreshCw, 
  Search, 
  Download, 
  Heart, 
  FolderOpen, 
  CheckCircle2, 
  Package, 
  Bot, 
  AlertTriangle, 
  Rocket, 
  Trash2,
  X
} from 'lucide-vue-next'

const { t } = useI18n()
const modelsStore = useModelHubStore()

// Store 状态
const installedModels = computed(() => modelsStore.installedModels)
const hasInstalledModels = computed(() => installedModels.value.length > 0)
const marketModels = computed(() => modelsStore.marketModels)
const marketLoading = computed(() => modelsStore.marketLoading)
const marketError = computed(() => modelsStore.marketError)
const marketHasMore = computed(() => modelsStore.marketHasMore)

// 本地状态
const searchInput = ref('')
const selectedModel = ref<HuggingFaceModel | null>(null)
const modelFiles = ref<HuggingFaceFileSibling[]>([])
const filesLoading = ref(false)
const showDownloaded = ref(false)
const deletingModel = ref<string | null>(null)

// 过滤文件列表
const isMlxSelected = computed(() => {
  if (!selectedModel.value) return false
  return isMlxModel(selectedModel.value)
})

const isRepositoryDownloading = computed(() => {
  if (!selectedModel.value) return false
  const taskId = `${selectedModel.value.id}/${REPO_DOWNLOAD_FILENAME}`
  const task = modelsStore.downloadTasks.get(taskId)
  return task ? ['pending', 'downloading'].includes(task.status) : false
})

const filteredFiles = computed(() => {
  const { gguf, mlx } = modelsStore.formatFilter
  return modelFiles.value.filter(f => {
    const lower = f.rfilename.toLowerCase()
    if (lower.includes('mmproj')) return false
    if (isMlxSelected.value) return true
    const format = getFileFormat(f.rfilename)
    if (format === 'gguf' && gguf) return true
    if (format === 'mlx' && mlx) return true
    return false
  })
})

// 方法
function getModelDisplayName(modelId: string): string {
  const parts = modelId.split('/')
  return parts[parts.length - 1]
}

function formatNumber(num: number): string {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return String(num)
}

function isMlxModel(model: HuggingFaceModel): boolean {
  if (model.format === 'mlx') return true
  const id = model.id.toLowerCase()
  if (id.includes('mlx')) return true
  const tags = model.tags?.map(t => t.toLowerCase()) || []
  if (tags.includes('mlx')) return true
  const libraryName = model.library_name?.toLowerCase() || ''
  if (libraryName.includes('mlx')) return true
  return false
}

function getFileFormat(filename: string): 'gguf' | 'mlx' {
  const lower = filename.toLowerCase()
  if (lower.endsWith('.gguf')) return 'gguf'
  if (lower.includes('mlx') || lower.endsWith('.safetensors')) return 'mlx'
  return 'gguf'
}

async function handleSearch() {
  await modelsStore.searchMarketModels(searchInput.value)
}

async function loadMore() {
  await modelsStore.loadMoreMarketModels()
}

async function retryLoadMarket() {
  await modelsStore.loadMarketModels(true)
}

async function openModelDetail(model: HuggingFaceModel) {
  selectedModel.value = model
  filesLoading.value = true
  modelFiles.value = []

  try {
    const files = await modelsStore.getModelFiles(model.id)
    modelFiles.value = files
  } catch (error) {
    logger.error('获取文件列表失败:', error)
  } finally {
    filesLoading.value = false
  }
}

function closeModelDetail() {
  selectedModel.value = null
  modelFiles.value = []
}

function isFileDownloading(filename: string): boolean {
  if (!selectedModel.value) return false
  const taskId = `${selectedModel.value.id}/${filename}`
  const task = modelsStore.downloadTasks.get(taskId)
  return task ? ['pending', 'downloading'].includes(task.status) : false
}

function isFileInstalled(filename: string): boolean {
  return installedModels.value.some(m => m.filename === filename)
}

async function handleDownloadFile(file: HuggingFaceFileSibling) {
  if (!selectedModel.value) return
  
  const model = selectedModel.value
  const paramTag = model.tags?.find(t => /^\d+(\.\d+)?[bB]$/.test(t))
  const parameters = paramTag ? paramTag.toUpperCase() : undefined
  
  const capabilities: string[] = []
  if (model.pipeline_tag) {
    capabilities.push(model.pipeline_tag)
  }
  if (model.tags?.some(t => ['vision', 'image-text-to-text', 'image-to-text'].includes(t))) {
    if (!capabilities.includes('vision')) {
      capabilities.push('vision')
    }
  }
  if (capabilities.length === 0) {
    capabilities.push('text-generation')
  }
  
  modelsStore.downloadModel(model.id, file.rfilename, false, parameters, capabilities)
  closeModelDetail()
}

async function handleDownloadRepository() {
  if (!selectedModel.value) return
  
  const model = selectedModel.value
  const paramTag = model.tags?.find(t => /^\d+(\.\d+)?[bB]$/.test(t))
  const parameters = paramTag ? paramTag.toUpperCase() : undefined
  
  const capabilities: string[] = []
  if (model.pipeline_tag) {
    capabilities.push(model.pipeline_tag)
  }
  if (model.tags?.some(t => ['vision', 'image-text-to-text', 'image-to-text'].includes(t))) {
    if (!capabilities.includes('vision')) {
      capabilities.push('vision')
    }
  }
  if (capabilities.length === 0) {
    capabilities.push('text-generation')
  }
  
  modelsStore.downloadRepository(model.id, parameters, capabilities)
  closeModelDetail()
}

async function confirmDeleteModel(model: { id: string; filename: string }) {
  const confirmed = window.confirm(t.value.models.deleteModelConfirm.replace('{filename}', model.filename))
  
  if (!confirmed) return
  
  deletingModel.value = model.id
  
  try {
    const success = await modelsStore.deleteInstalledModel(model.id)
    if (success) {
      logger.info(`模型 ${model.filename} 已删除`)
    } else {
      logger.error(`删除模型 ${model.filename} 失败`)
    }
  } catch (error) {
    logger.error('删除模型失败:', error)
  } finally {
    deletingModel.value = null
  }
}

async function handleMirrorToggle(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  modelsStore.setUseMirror(checked)
  await setProviderMirrorEnabled('huggingface', checked)
}

onMounted(async () => {
  const useMirror = await getProviderMirrorEnabled('huggingface')
  modelsStore.setUseMirror(useMirror)
  await modelsStore.loadInstalledModels()
  if (marketModels.value.length === 0) {
    await modelsStore.loadMarketModels(true)
  }
})
</script>

<style scoped>
.llm-model-content {
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

.search-section {
  margin-bottom: 1.5rem;
}

.search-bar {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.search-bar input {
  flex: 1;
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  font-size: 0.9rem;
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.search-bar input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.search-btn {
  padding: 0.75rem 1.25rem;
  font-weight: 500;
}

.filter-options {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
}

.checkbox-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
}

.checkbox-label {
  font-size: 0.875rem;
  color: var(--color-text-primary);
}

.checkbox-item.mirror .checkbox-label {
  color: var(--color-success, #22c55e);
}

.filter-divider {
  color: var(--color-border);
}

.loading-state,
.empty-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 3rem;
  text-align: center;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.empty-icon,
.error-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}

.model-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 1.25rem;
  cursor: pointer;
  transition: all 0.2s;
}

.model-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.model-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.model-header h3 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--color-text-primary);
  word-break: break-word;
  flex: 1;
}

.author-badge {
  padding: 0.2rem 0.5rem;
  background: var(--color-button-emphasis-bg);
  color: var(--color-button-emphasis-fg);
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 500;
  white-space: nowrap;
}

.model-meta {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}

.model-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-bottom: 0.75rem;
}

.tag {
  padding: 0.15rem 0.4rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 0.65rem;
  color: var(--color-text-secondary);
}

.detail-btn {
  width: 100%;
  padding: 0.6rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--color-text-primary);
  transition: all 0.2s;
}

.detail-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.load-more {
  display: flex;
  justify-content: center;
  margin-top: 1.5rem;
}

.load-more-btn {
  padding: 0.75rem 2rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text-primary);
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.load-more-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.load-more-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.primary-btn {
  padding: 0.75rem 1.5rem;
  font-weight: 500;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  padding: 2rem;
}

.modal-content {
  background: var(--color-bg);
  border-radius: 16px;
  width: 100%;
  max-width: 550px;
  max-height: 70vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.modal-header h2 {
  margin: 0;
  font-size: 1.1rem;
  color: var(--color-text-primary);
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: var(--color-bg);
  border-radius: 8px;
  cursor: pointer;
  font-size: 1rem;
  color: var(--color-text-secondary);
}

.close-btn:hover {
  background: var(--color-hover);
}

.modal-body {
  padding: 1.25rem;
  overflow-y: auto;
}

.model-detail-info {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin-bottom: 1.25rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.info-item .label {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.info-item .value {
  font-weight: 500;
  color: var(--color-text-primary);
}

.modal-body h3 {
  margin: 0 0 0.75rem 0;
  font-size: 0.95rem;
}

.files-loading {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: var(--color-text-secondary);
  padding: 1rem 0;
}

.no-files {
  padding: 1.5rem;
  text-align: center;
  color: var(--color-text-secondary);
}

.files-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  background: var(--color-bg-secondary);
  border-radius: 8px;
  gap: 1rem;
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  display: block;
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--color-text-primary);
  word-break: break-all;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.2rem;
}

.file-size {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.file-format {
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  font-size: 0.6rem;
  font-weight: 600;
}

.file-format.gguf {
  background: #3b82f6;
  color: white;
}

.file-format.mlx {
  background: #f59e0b;
  color: white;
}

.download-btn {
  padding: 0.5rem 0.75rem;
  font-weight: 500;
  font-size: 0.8rem;
  white-space: nowrap;
}

.download-btn:disabled {
  background: var(--color-bg);
  color: var(--color-text-secondary);
  cursor: not-allowed;
}

/* 已下载模型样式 */
.checkbox-item.downloaded .checkbox-label {
  color: var(--color-primary);
  font-weight: 500;
}

.installed-section {
  margin-bottom: 2rem;
}

.installed-section h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: var(--color-text-primary);
}

.empty-installed {
  padding: 2rem;
  text-align: center;
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
  border-radius: 12px;
  border: 1px dashed var(--color-border);
}

.installed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.installed-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 1.25rem;
  transition: all 0.2s;
}

.installed-card:hover {
  border-color: var(--color-primary);
}

.installed-header {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.installed-header h4 {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--color-text-primary);
  word-break: break-all;
  flex: 1;
}

.format-badge {
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  color: white;
  flex-shrink: 0;
}

.format-badge.gguf {
  background: #3b82f6;
}

.format-badge.mlx {
  background: #f59e0b;
}

.installed-meta {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.installed-meta .size {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--color-text-primary);
}

.installed-meta .author {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}

.installed-source {
  margin-bottom: 0.75rem;
}

.hf-id {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  font-family: monospace;
  background: var(--color-bg);
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
}

.installed-actions {
  display: flex;
  gap: 0.5rem;
}

.delete-btn {
  flex: 1;
  padding: 0.6rem;
  background: transparent;
  border: 1px solid var(--color-danger, #ef4444);
  color: var(--color-danger, #ef4444);
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: all 0.2s;
}

.delete-btn:hover:not(:disabled) {
  background: var(--color-danger, #ef4444);
  color: white;
}

.delete-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
