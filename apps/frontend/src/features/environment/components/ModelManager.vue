<template>
  <div class="model-manager">
    <h2>
      <Target :size="32" class="icon" />
      {{ t.modelManager.title }}
    </h2>
    
    <!-- 标签页切换 -->
    <div class="tabs">
      <button
        :class="['tab', { active: activeTab === 'registry' }]"
        @click="activeTab = 'registry'"
      >
        <Box :size="18" class="mr-2" />
        {{ t.modelManager.tabs.registry }}
      </button>
      <button
        :class="['tab', { active: activeTab === 'installed' }]"
        @click="activeTab = 'installed'"
      >
        <CheckCircle2 :size="18" class="mr-2" />
        {{ t.modelManager.tabs.installed }}
      </button>
      <button
        :class="['tab', { active: activeTab === 'downloads' }]"
        @click="activeTab = 'downloads'"
      >
        <Download :size="18" class="mr-2" />
        {{ t.modelManager.tabs.downloads.replace('{count}', downloadTasks.length.toString()) }}
      </button>
    </div>

    <!-- 可下载模型 -->
    <div v-if="activeTab === 'registry'" class="tab-content">
      <!-- 筛选器 -->
      <div class="filters">
        <PluginDevInlineSelect
          :model-value="filter.provider"
          :options="providerOptions"
          :label="t.modelManager.filters.provider"
          class="filter-select"
          @update:model-value="(value) => { filter.provider = value }"
          @change="applyFilter"
        />

        <PluginDevInlineSelect
          :model-value="filter.family"
          :options="familyOptions"
          :label="t.modelManager.filters.family"
          class="filter-select"
          @update:model-value="(value) => { filter.family = value }"
          @change="applyFilter"
        />

        <PluginDevInlineSelect
          :model-value="filter.size"
          :options="sizeOptions"
          :label="t.modelManager.filters.size"
          class="filter-select"
          @update:model-value="(value) => { filter.size = value }"
          @change="applyFilter"
        />
        
        <button @click="resetFilter" class="reset-btn">{{ t.modelManager.filters.reset }}</button>
      </div>

      <!-- 模型列表 -->
      <div v-if="loading" class="loading">{{ t.common.loading }}</div>
      
      <div v-else class="models-grid">
        <div
          v-for="model in filteredModels"
          :key="model.id"
          class="model-card"
        >
          <div class="model-header">
            <h3>{{ model.name }}</h3>
            <span class="provider-badge">{{ model.provider }}</span>
          </div>
          
          <div class="model-info">
            <div class="info-row">
              <span class="label">{{ t.modelManager.columns.parameters }}:</span>
              <span class="value">{{ model.parameters }}</span>
            </div>
            <div class="info-row">
              <span class="label">{{ t.modelManager.columns.size }}:</span>
              <span class="value">{{ model.size_display }}</span>
            </div>
            <div class="info-row">
              <span class="label">{{ t.modelManager.columns.context }}:</span>
              <span class="value">{{ formatContext(model.context_window) }}</span>
            </div>
            <div class="info-row">
              <span class="label">{{ t.modelManager.columns.capabilities }}:</span>
              <span class="capabilities">
                <span v-for="cap in model.capabilities" :key="cap" class="cap-badge">
                  <component :is="cap === 'text' ? FileText : Image" :size="14" class="mr-1" />
                  {{ cap }}
                </span>
              </span>
            </div>
          </div>
          
          <p class="description">{{ model.description }}</p>
          
          <div class="tags">
            <span v-for="tag in model.tags.slice(0, 3)" :key="tag" class="tag">
              {{ tag }}
            </span>
          </div>
          
          <div class="recommended">
            <strong>{{ t.modelManager.columns.recommended }}:</strong>
            <ul>
              <li v-for="use in model.recommended_for" :key="use">{{ use }}</li>
            </ul>
          </div>
          
          <div class="actions">
            <button
              @click="downloadModel(model.id)"
              :disabled="isDownloading(model.id) || isInstalled(model.id)"
              class="download-btn ui-btn ui-btn--emphasis"
            >
              <span v-if="isInstalled(model.id)" class="flex items-center">
                <CheckCircle2 :size="16" class="mr-1" /> {{ t.modelManager.actions.installed }}
              </span>
              <span v-else-if="isDownloading(model.id)" class="flex items-center">
                <Loader2 :size="16" class="mr-1 animate-spin" /> {{ t.modelManager.actions.downloading }}
              </span>
              <span v-else class="flex items-center">
                <Download :size="16" class="mr-1" /> {{ t.modelManager.actions.download }}
              </span>
            </button>
            
            <a :href="model.url" target="_blank" class="info-link">
              <BookOpen :size="16" class="mr-1" /> {{ t.modelManager.actions.details }}
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- 已安装模型 -->
    <div v-if="activeTab === 'installed'" class="tab-content">
      <div v-if="loadingInstalled" class="loading">
        <Loader2 :size="24" class="animate-spin mr-2" /> {{ t.common.loading }}
      </div>
      
      <div v-else-if="installedModels.length === 0" class="empty-state">
        <p class="flex items-center justify-center">
          <Smile :size="24" class="mr-2" /> {{ t.modelManager.empty.installedTitle }}
        </p>
        <p>{{ t.modelManager.empty.installedDesc }}</p>
      </div>
      
      <div v-else class="models-grid">
        <div
          v-for="model in installedModels"
          :key="model.id"
          class="model-card installed"
        >
          <div class="model-header">
            <h3>{{ model.display_name || model.name }}</h3>
            <span v-if="model.provider" class="provider-badge">
              {{ model.provider }}
            </span>
          </div>
          
          <div class="model-info">
            <div class="info-row">
              <span class="label">ID:</span>
              <code class="value">{{ model.id }}</code>
            </div>
            <div class="info-row">
              <span class="label">{{ t.modelManager.columns.size }}:</span>
              <span class="value">{{ model.size_display }}</span>
            </div>
            <div class="info-row">
              <span class="label">{{ t.modelManager.columns.updated }}:</span>
              <span class="value">{{ formatDate(model.modified_at) }}</span>
            </div>
          </div>
          
          <p v-if="model.description" class="description">
            {{ model.description }}
          </p>
          
          <div v-if="model.tags" class="tags">
            <span v-for="tag in model.tags.slice(0, 3)" :key="tag" class="tag">
              {{ tag }}
            </span>
          </div>
          
          <div class="actions">
            <button
              @click.stop="showDeleteConfirm(model.id)"
              class="delete-btn"
              :disabled="deletingModels.has(model.id)"
              type="button"
            >
              <span v-if="deletingModels.has(model.id)" class="flex items-center">
                <Loader2 :size="16" class="animate-spin mr-1" /> {{ t.modelManager.actions.deleting }}
              </span>
              <span v-else class="flex items-center">
                <Trash2 :size="16" class="mr-1" /> {{ t.modelManager.actions.delete }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 下载任务 -->
    <div v-if="activeTab === 'downloads'" class="tab-content">
      <div v-if="downloadTasks.length === 0" class="empty-state">
        <p class="flex items-center justify-center"><Inbox :size="24" class="mr-2" /> {{ t.modelManager.empty.downloads }}</p>
      </div>
      
      <div v-else class="tasks-list">
        <div
          v-for="task in downloadTasks"
          :key="task.model_id"
          class="task-card"
        >
          <div class="task-header">
            <h3>{{ task.model_name }}</h3>
            <span :class="['status-badge', task.status]">
              {{ getStatusText(task.status) }}
            </span>
          </div>
          
          <div v-if="task.status === 'downloading'" class="progress-section">
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: task.progress + '%' }"
              ></div>
            </div>
            <div class="progress-info">
              <span>{{ task.progress.toFixed(1) }}%</span>
              <span>{{ task.speed }}</span>
              <span>{{ t.modelManager.task.remaining }}: {{ task.eta }}</span>
            </div>
          </div>
          
          <div class="task-meta">
            <span>{{ t.modelManager.task.startTime }}: {{ formatDateTime(task.started_at) }}</span>
            <span>{{ t.modelManager.task.updateTime }}: {{ formatDateTime(task.updated_at) }}</span>
          </div>
          
          <div v-if="task.error_message" class="error-message">
            <XCircle :size="16" class="mr-1" /> {{ task.error_message }}
          </div>
          
          <div class="task-actions">
            <button
              v-if="task.status === 'downloading' || task.status === 'pending'"
              @click="cancelDownload(task.model_id)"
              class="cancel-btn"
            >
              <Ban :size="16" class="mr-1" /> {{ t.modelManager.actions.cancel }}
            </button>
            
            <button
              v-if="['completed', 'failed', 'cancelled'].includes(task.status)"
              @click="removeTask(task.model_id)"
              class="remove-btn"
            >
              <Trash2 :size="16" class="mr-1" /> {{ t.modelManager.actions.remove }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 删除确认对话框 -->
  <ConfirmDialog
    v-model:visible="confirmDialog.visible"
    type="danger"
    :title="t.modelManager.dialog.delete.title"
    :message="t.modelManager.dialog.delete.message"
    :detail="t.modelManager.dialog.delete.detail.replace('{name}', confirmDialog.modelName).replace('{id}', confirmDialog.modelId)"
    :icon="(AlertTriangle as any)"
    :confirm-text="t.modelManager.dialog.delete.confirm"
    :cancel-text="t.modelManager.dialog.delete.cancel"
    @confirm="deleteModel"
    @cancel="confirmDialog.visible = false"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from '@/composables/useI18n'
import { logger } from '@/utils/logger'
import { buildBackendUrl } from '@/utils/backendUrl'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import PluginDevInlineSelect from '@/features/coding-agent/components/plugin-dev-chat/PluginDevInlineSelect.vue'
import type { PluginDevInlineSelectOption } from '@/features/coding-agent/components/plugin-dev-chat/PluginDevInlineSelect.vue'
import { 
  Target, Box, CheckCircle2, Download, Trash2, BookOpen, 
  FileText, Image, AlertTriangle, XCircle, Ban,
  Loader2, Smile, Inbox
} from 'lucide-vue-next'

const { t, locale } = useI18n()

const currentLocale = computed(() => locale.value === 'zh' ? 'zh-CN' : 'en-US')

// 状态
const activeTab = ref<'registry' | 'installed' | 'downloads'>('registry')
const loading = ref(false)
const loadingInstalled = ref(false)

// 数据
const registry = ref<any>({ models: [], categories: [] })
const installedModels = ref<any[]>([])
const downloadTasks = ref<any[]>([])
const deletingModels = ref<Set<string>>(new Set())

// 确认对话框状态
const confirmDialog = ref({
  visible: false,
  modelId: '',
  modelName: ''
})

// 筛选
const filter = ref({
  provider: '',
  family: '',
  size: ''
})

// 计算属性
const providers = computed<string[]>(() => {
  const set = new Set<string>(registry.value.models.map((m: any) => m.provider))
  return Array.from(set).sort()
})

const families = computed<string[]>(() => {
  const set = new Set<string>(registry.value.models.map((m: any) => m.family))
  return Array.from(set).sort()
})

const providerOptions = computed<PluginDevInlineSelectOption[]>(() => [
  { value: '', label: t.value.modelManager.filters.provider },
  ...providers.value.map((provider) => ({ value: provider, label: provider })),
])

const familyOptions = computed<PluginDevInlineSelectOption[]>(() => [
  { value: '', label: t.value.modelManager.filters.family },
  ...families.value.map((family) => ({ value: family, label: family })),
])

const sizeOptions = computed<PluginDevInlineSelectOption[]>(() => [
  { value: '', label: t.value.modelManager.filters.size },
  { value: '1', label: t.value.modelManager.filters.light },
  { value: '3', label: t.value.modelManager.filters.balanced },
  { value: '10', label: t.value.modelManager.filters.performance },
])

const filteredModels = computed(() => {
  let models = registry.value.models

  if (filter.value.provider) {
    models = models.filter((m: any) => m.provider === filter.value.provider)
  }

  if (filter.value.family) {
    models = models.filter((m: any) => m.family === filter.value.family)
  }

  if (filter.value.size) {
    const maxBytes = parseFloat(filter.value.size) * 1024 * 1024 * 1024
    models = models.filter((m: any) => m.size <= maxBytes)
  }

  return models
})

// 方法
const loadRegistry = async () => {
  loading.value = true
  try {
    const res = await fetch(buildBackendUrl('/api/local-ai/models/registry'))
    const data = await res.json()
    if (data.status === 'success') {
      registry.value = data.data
    }
  } catch (error) {
    logger.error('加载模型注册表失败:', error)
  } finally {
    loading.value = false
  }
}

const loadInstalledModels = async () => {
  loadingInstalled.value = true
  try {
    const res = await fetch(buildBackendUrl('/api/local-ai/models'))
    const data = await res.json()
    if (data.status === 'success') {
      installedModels.value = data.models
    }
  } catch (error) {
    logger.error('加载已安装模型失败:', error)
  } finally {
    loadingInstalled.value = false
  }
}

const loadDownloadTasks = async () => {
  try {
    const res = await fetch(buildBackendUrl('/api/local-ai/models/downloads'))
    const data = await res.json()
    if (data.status === 'success') {
      downloadTasks.value = data.tasks
    }
  } catch (error) {
    logger.error('加载下载任务失败:', error)
  }
}

const downloadModel = async (modelId: string) => {
  try {
    logger.info('开始下载模型:', modelId)
    
    const response = await fetch(buildBackendUrl('/api/local-ai/models/download'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId })
    })

    if (!response.ok) {
      const errorText = await response.text()
      logger.error(`下载请求失败: ${response.status} - ${errorText}`)
      throw new Error(`HTTP ${response.status}: ${errorText}`)
    }

    // 初始化任务
    const newTask = {
      model_id: modelId,
      model_name: modelId,
      status: 'downloading',
      progress: 0,
      speed: '',
      eta: '',
      started_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    }
    
    // 添加到任务列表（如果不存在）
    const existingIndex = downloadTasks.value.findIndex(t => t.model_id === modelId)
    if (existingIndex >= 0) {
      downloadTasks.value[existingIndex] = newTask
    } else {
      downloadTasks.value.push(newTask)
    }
    
    // 切换到下载任务标签页
    activeTab.value = 'downloads'

    // 处理 SSE 流
    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    if (reader) {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // 保留不完整的行

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              logger.info('📥 下载进度:', data)
              
              // 直接从 SSE 数据更新进度
              const taskIndex = downloadTasks.value.findIndex(t => t.model_id === modelId)
              if (taskIndex >= 0) {
                const task = downloadTasks.value[taskIndex]
                
                // Ollama 返回 total 和 completed 字段
                if (data.total && data.completed) {
                  const progress = (data.completed / data.total) * 100
                  const mbTotal = data.total / (1024 * 1024)
                  const mbCompleted = data.completed / (1024 * 1024)
                  
                  task.progress = progress
                  task.downloaded_bytes = data.completed
                  task.total_bytes = data.total
                  task.speed = `${mbCompleted.toFixed(1)}/${mbTotal.toFixed(1)} MB`
                  task.updated_at = new Date().toISOString()
                  
                  logger.info(`✅ 进度更新: ${progress.toFixed(1)}%`)
                }
                
                // 检查状态
                if (data.status === 'success') {
                  task.status = 'completed'
                  task.progress = 100
                  logger.info('✅ 下载完成!')
                  
                  // 刷新已安装列表
                  await loadInstalledModels()
                } else if (data.status === 'error') {
                  task.status = 'failed'
                  task.error_message = data.message || t.value.common.failed
                  logger.error('❌ 下载失败:', data.message)
                }
                
                // 强制更新
                downloadTasks.value = [...downloadTasks.value]
              }
            } catch (e) {
              logger.error(`解析 SSE 数据失败: ${line}`, e)
            }
          }
        }
      }
    }
  } catch (error) {
    logger.error('❌ 下载模型失败:', error)
    alert(t.value.modelManager.alerts.downloadFailed.replace('{error}', String(error)))
    
    // 更新任务状态为失败
    const taskIndex = downloadTasks.value.findIndex(t => t.model_id === modelId)
    if (taskIndex >= 0) {
      downloadTasks.value[taskIndex].status = 'failed'
      downloadTasks.value[taskIndex].error_message = String(error)
    }
  }
}

const cancelDownload = async (modelId: string) => {
  try {
    const res = await fetch(buildBackendUrl(`/api/local-ai/models/cancel/${modelId}`), {
      method: 'POST'
    })
    const data = await res.json()
    
    if (data.status === 'success') {
      await loadDownloadTasks()
    }
  } catch (error) {
    logger.error('取消下载失败:', error)
  }
}

const showDeleteConfirm = (modelId: string) => {
  logger.info('🗑️ [DELETE] 点击删除按钮, modelId:', modelId)
  
  // 查找模型信息
  const model = installedModels.value.find(m => m.id === modelId)
  
  // 显示确认对话框
  confirmDialog.value = {
    visible: true,
    modelId: modelId,
    modelName: model?.display_name || model?.name || modelId
  }
}

const deleteModel = async () => {
  const modelId = confirmDialog.value.modelId
  logger.info('🗑️ [DELETE] 用户已确认，开始删除模型:', modelId)
  
  // 关闭对话框
  confirmDialog.value.visible = false
  
  deletingModels.value.add(modelId)
  
  try {
    const url = buildBackendUrl(`/api/local-ai/models/${modelId}`)
    logger.info('DELETE 请求:', url)
    
    const res = await fetch(url, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json'
      }
    })
    
    logger.info('删除响应状态:', res.status)
    
    if (!res.ok) {
      const errorText = await res.text()
      logger.error(`删除请求失败: ${res.status} - ${errorText}`)
      throw new Error(`HTTP ${res.status}: ${errorText}`)
    }
    
    const data = await res.json()
    logger.info('删除响应数据:', data)
    
    if (data.status === 'success') {
        logger.info('✅ 删除成功:', modelId)
        alert(t.value.modelManager.alerts.deleteSuccess.replace('{id}', modelId))
        
        // 刷新已安装列表
        await loadInstalledModels()
      } else {
        logger.error('删除失败:', data)
        alert(t.value.modelManager.alerts.deleteFailed.replace('{error}', data.message || t.value.common.unknown))
      }
  } catch (error) {
    logger.error('❌ 删除模型异常:', error)
    alert(t.value.modelManager.alerts.deleteFailed.replace('{error}', String(error)))
  } finally {
    deletingModels.value.delete(modelId)
    logger.info('删除操作结束')
  }
}

const removeTask = (modelId: string) => {
  downloadTasks.value = downloadTasks.value.filter(t => t.model_id !== modelId)
}

const applyFilter = () => {
  // 筛选器改变时触发
}

const resetFilter = () => {
  filter.value = {
    provider: '',
    family: '',
    size: ''
  }
}

const isDownloading = (modelId: string) => {
  return downloadTasks.value.some(
    t => t.model_id === modelId && ['pending', 'downloading'].includes(t.status)
  )
}

const isInstalled = (modelId: string) => {
  return installedModels.value.some(m => m.id === modelId)
}

const formatContext = (num: number) => {
  if (num >= 1024) {
    return `${(num / 1024).toFixed(0)}K`
  }
  return num.toString()
}

const formatDate = (dateStr: string) => {
  try {
    return new Date(dateStr).toLocaleString(currentLocale.value)
  } catch {
    return dateStr
  }
}

const formatDateTime = (dateStr: string) => {
  try {
    return new Date(dateStr).toLocaleString(currentLocale.value, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return dateStr
  }
}

const getStatusText = (status: string) => {
  const map: Record<string, string> = {
    pending: t.value.modelManager.status.pending,
    downloading: t.value.modelManager.status.downloading,
    completed: t.value.modelManager.status.completed,
    failed: t.value.modelManager.status.failed,
    cancelled: t.value.modelManager.status.cancelled
  }
  return map[status] || status
}

// 生命周期
let pollInterval: number | null = null

onMounted(async () => {
  logger.info('🚀 ModelManager 组件已挂载')
  await loadRegistry()
  await loadInstalledModels()
  await loadDownloadTasks()
  
  // 轻量级轮询（仅用于同步后台任务状态，不影响 SSE 实时更新）
  pollInterval = window.setInterval(async () => {
    // 只在没有活跃下载任务时轮询
    const hasActiveDownloads = downloadTasks.value.some(
      t => ['pending', 'downloading'].includes(t.status)
    )
    if (!hasActiveDownloads) {
      await loadDownloadTasks()
    }
  }, 5000) // 改为5秒，减少不必要的请求
})

onUnmounted(() => {
  logger.info('🛑 ModelManager 组件卸载')
  if (pollInterval) {
    clearInterval(pollInterval)
  }
})
</script>

<style scoped>
.model-manager {
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

h2 {
  color: #333;
  margin-bottom: 2rem;
  font-size: 2rem;
}

/* 标签页 */
.tabs {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 2rem;
  border-bottom: 2px solid #e0e0e0;
}

.tab {
  padding: 1rem 2rem;
  background: none;
  border: none;
  border-bottom: 3px solid transparent;
  font-size: 1.1rem;
  font-weight: 600;
  color: #666;
  cursor: pointer;
  transition: all 0.3s;
}

.tab:hover {
  color: #667eea;
  background: rgba(102, 126, 234, 0.05);
}

.tab.active {
  color: #667eea;
  border-bottom-color: #667eea;
}

/* 筛选器 */
.filters {
  display: flex;
  gap: 1rem;
  margin-bottom: 2rem;
  flex-wrap: wrap;
}

.filter-select {
  width: 220px;
  min-width: 180px;
}

.reset-btn {
  padding: 0.75rem 1.5rem;
  background: #f5f5f5;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.reset-btn:hover {
  background: #e0e0e0;
}

/* 模型卡片 */
.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.5rem;
}

.model-card {
  background: white;
  border: 2px solid #e0e0e0;
  border-radius: 12px;
  padding: 1.5rem;
  transition: all 0.3s;
}

.model-card:hover {
  border-color: #667eea;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
  transform: translateY(-2px);
}

.model-card.installed {
  border-color: #28a745;
  background: linear-gradient(135deg, #ffffff 0%, #f0fff4 100%);
}

.model-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.model-header h3 {
  font-size: 1.2rem;
  color: #333;
  margin: 0;
  flex: 1;
}

.provider-badge {
  padding: 0.25rem 0.75rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 12px;
  font-size: 0.85rem;
  font-weight: 600;
}

.model-info {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.95rem;
}

.label {
  color: #666;
  font-weight: 600;
}

.value {
  color: #333;
}

.capabilities {
  display: flex;
  gap: 0.5rem;
}

.cap-badge {
  padding: 0.25rem 0.5rem;
  background: #f0f0f0;
  border-radius: 6px;
  font-size: 0.85rem;
}

.description {
  color: #555;
  font-size: 0.95rem;
  line-height: 1.5;
  margin: 1rem 0;
}

.tags {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.tag {
  padding: 0.25rem 0.75rem;
  background: linear-gradient(135deg, #ffeaa7 0%, #fdcb6e 100%);
  border-radius: 12px;
  font-size: 0.85rem;
  font-weight: 600;
  color: #2d3436;
}

.recommended {
  background: #f8f9fa;
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
}

.recommended strong {
  color: #333;
  display: block;
  margin-bottom: 0.5rem;
}

.recommended ul {
  margin: 0;
  padding-left: 1.5rem;
  color: #555;
}

.recommended li {
  font-size: 0.9rem;
  line-height: 1.6;
}

.actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 1rem;
}

.download-btn, .delete-btn, .cancel-btn, .remove-btn {
  flex: 1;
  padding: 0.75rem;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.download-btn {
  border: none;
}

.download-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--color-button-emphasis-bg) 28%, transparent);
}

.download-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.delete-btn {
  background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
  color: white;
}

.delete-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(255, 107, 107, 0.3);
}

.info-link {
  flex: 1;
  padding: 0.75rem;
  background: #f8f9fa;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  text-align: center;
  text-decoration: none;
  color: #333;
  font-weight: 600;
  transition: all 0.2s;
}

.info-link:hover {
  background: #e0e0e0;
}

/* 下载任务 */
.tasks-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.task-card {
  background: white;
  border: 2px solid #e0e0e0;
  border-radius: 12px;
  padding: 1.5rem;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.status-badge {
  padding: 0.5rem 1rem;
  border-radius: 12px;
  font-size: 0.9rem;
  font-weight: 600;
}

.status-badge.pending {
  background: #ffeaa7;
  color: #2d3436;
}

.status-badge.downloading {
  background: linear-gradient(135deg, #74b9ff 0%, #0984e3 100%);
  color: white;
}

.status-badge.completed {
  background: linear-gradient(135deg, #00b894 0%, #00cec9 100%);
  color: white;
}

.status-badge.failed {
  background: linear-gradient(135deg, #ff7675 0%, #d63031 100%);
  color: white;
}

.status-badge.cancelled {
  background: #dfe6e9;
  color: #2d3436;
}

.progress-section {
  margin-bottom: 1rem;
}

.progress-bar {
  width: 100%;
  height: 24px;
  background: #f0f0f0;
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
  transition: width 0.3s;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: 0.9rem;
  color: #666;
}

.task-meta {
  display: flex;
  gap: 2rem;
  font-size: 0.85rem;
  color: #999;
  margin-bottom: 1rem;
}

.error-message {
  background: #fee;
  border: 1px solid #fcc;
  padding: 0.75rem;
  border-radius: 6px;
  color: #c00;
  margin-bottom: 1rem;
}

.task-actions {
  display: flex;
  gap: 0.75rem;
}

.cancel-btn {
  background: linear-gradient(135deg, #ff7675 0%, #d63031 100%);
  color: white;
}

.remove-btn {
  background: #dfe6e9;
  color: #2d3436;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  color: #999;
  font-size: 1.1rem;
}

.empty-state p:first-child {
  font-size: 1.5rem;
  margin-bottom: 1rem;
}

.loading {
  text-align: center;
  padding: 4rem 2rem;
  font-size: 1.2rem;
  color: #667eea;
}
</style>
