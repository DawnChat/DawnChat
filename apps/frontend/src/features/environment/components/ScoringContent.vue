<template>
  <div class="scoring-content">
    <!-- 头部 -->
    <div class="content-header">
      <div class="header-info">
        <h2 class="flex items-center gap-2">
          <AudioWaveform :size="24" />
          {{ t.models.scoring.title }}
        </h2>
        <p class="subtitle">{{ t.models.scoring.subtitle }}</p>
      </div>
      <div class="header-status" :class="{ ready: hasInstalledModels }">
        <span v-if="hasInstalledModels" class="flex items-center gap-1">
          <CheckCircle2 :size="16" />
          {{ t.common.installed }} {{ installedModels.length }} {{ t.models.title }}
        </span>
        <span v-else class="flex items-center gap-1">
          <AlertTriangle :size="16" />
          {{ t.common.noModelsInstalled }}
        </span>
      </div>
    </div>
    
    <!-- 引擎列表 -->
    <div class="engines-section">
      <h3>{{ t.common.availableEngines }}</h3>
      
      <!-- Wav2Vec2 -->
      <div class="engine-card">
        <div class="engine-header">
          <div class="engine-info">
            <span class="engine-icon">
              <AudioWaveform :size="24" />
            </span>
            <div class="engine-text">
              <span class="engine-name">Wav2Vec2</span>
              <span class="engine-desc">{{ t.models.scoring.wav2vec2Desc }}</span>
            </div>
          </div>
        </div>
        
        <!-- 已安装的模型 -->
        <div v-if="installedModels.length > 0" class="installed-models">
          <h4>{{ t.common.installed }} {{ t.models.title }}</h4>
          <div class="model-chips">
            <span v-for="modelId in installedModels" :key="modelId" class="model-chip installed flex items-center gap-1">
              <CheckCircle2 :size="12" />
              {{ getModelName(modelId) }}
            </span>
          </div>
        </div>
        
        <!-- 下载提示（如果正在下载） -->
        <div v-if="isDownloading" class="download-hint">
          <span class="hint-icon">
            <Download :size="20" />
          </span>
          <span>{{ t.common.downloadingInTask }}</span>
        </div>
        
        <!-- 模型选择 -->
        <div v-else class="model-options">
          <h4>{{ t.common.modelSize }}</h4>
          <div class="options-grid">
            <div 
              v-for="model in models" 
              :key="model.id"
              class="model-option"
              :class="{ 
                selected: selectedModel === model.id, 
                installed: model.installed 
              }"
              @click="selectedModel = model.id"
            >
              <div class="option-header">
                <span class="option-name">{{ model.name }}</span>
                <span v-if="model.installed" class="installed-badge flex items-center gap-1">
                  <CheckCircle2 :size="12" />
                  {{ t.common.installed }}
                </span>
              </div>
              <p class="option-desc">{{ model.description }}</p>
              <div class="option-meta">
                <span class="option-size">{{ model.sizeMb }} MB</span>
                <span class="option-repo">{{ model.hfRepoId }}</span>
              </div>
            </div>
          </div>
          
          <div class="action-bar">
            <label class="checkbox-item">
              <input type="checkbox" :checked="useMirror" @change="handleMirrorToggle" />
              <span class="checkbox-label flex items-center gap-1">
                <Rocket :size="14" />
                {{ t.common.useMirror }}
              </span>
            </label>
            <button 
              class="primary-btn ui-btn ui-btn--emphasis flex items-center gap-2"
              :disabled="!selectedModel || isModelInstalled(selectedModel) || isDownloading"
              @click="handleDownload"
            >
              <template v-if="isModelInstalled(selectedModel)">{{ t.common.installed }}</template>
              <template v-else>
                <Download :size="16" />
                {{ t.common.download }}
              </template>
            </button>
          </div>
        </div>
      </div>
      
      <!-- 使用说明 -->
      <div class="usage-note">
        <Info :size="20" />
        <p>{{ t.models.scoring.usageNote }}</p>
      </div>
    </div>

    <!-- NLTK 资源列表 -->
    <div class="resources-section">
      <h3>{{ t.models.scoring.nltkResources?.title || 'NLTK Resources' }}</h3>
      
      <div class="resources-grid">
        <div 
          v-for="resource in nltkResources" 
          :key="resource.id"
          class="resource-card"
        >
          <div class="resource-header">
            <div class="resource-info">
              <span class="resource-icon">
                <Database :size="20" />
              </span>
              <div class="resource-text">
                <span class="resource-name">{{ resource.name }}</span>
                <span class="resource-desc">{{ resource.description }}</span>
              </div>
            </div>
            
            <div class="resource-status">
              <span v-if="resource.installed" class="status-badge installed">
                <CheckCircle2 :size="14" />
                {{ t.common.installed }}
              </span>
              <button 
                v-else 
                class="download-btn ui-btn ui-btn--emphasis"
                :disabled="resource.downloading"
                @click="handleNltkDownload(resource.id)"
              >
                <span v-if="resource.downloading" class="flex items-center gap-1">
                  <span class="spinner"></span>
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
      
      <!-- NLTK 数据目录提示 -->
      <div class="nltk-path-hint" v-if="nltkDataDir">
        <HardDrive :size="14" />
        <span>{{ t.models.scoring.nltkResources?.path || 'Data Path' }}: {{ nltkDataDir }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useScoringStore } from '@/stores/scoringStore'
import { useNLTKStore } from '@/stores/nltkStore'
import { AudioWaveform, CheckCircle2, AlertTriangle, Download, Rocket, Info, Database, HardDrive } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'
import { getProviderMirrorEnabled, setProviderMirrorEnabled } from '@/composables/useResourceAccessMirror'

const { t } = useI18n()
const scoringStore = useScoringStore()
const nltkStore = useNLTKStore()

const selectedModel = ref('')
const useMirror = ref(true)

const hasInstalledModels = computed(() => scoringStore.status.installedModels.length > 0)
const installedModels = computed(() => scoringStore.status.installedModels)
const isDownloading = computed(() => scoringStore.isDownloading)
const models = computed(() => scoringStore.models)
const nltkResources = computed(() => nltkStore.status.resources)
const nltkDataDir = computed(() => nltkStore.status.data_dir)

const isModelInstalled = (modelId: string) => {
  return scoringStore.status.installedModels.includes(modelId)
}

const getModelName = (modelId: string) => {
  return scoringStore.models.find(m => m.id === modelId)?.name || modelId
}

const handleDownload = async () => {
  if (!selectedModel.value) return
  scoringStore.setUseMirror(useMirror.value)
  await scoringStore.downloadModel(selectedModel.value, useMirror.value)
}

const handleNltkDownload = async (resourceId: string) => {
  await nltkStore.downloadResource(resourceId)
}

async function handleMirrorToggle(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  useMirror.value = checked
  scoringStore.setUseMirror(checked)
  await setProviderMirrorEnabled('huggingface', checked)
}

onMounted(async () => {
  const mirrorEnabled = await getProviderMirrorEnabled('huggingface')
  useMirror.value = mirrorEnabled
  scoringStore.setUseMirror(mirrorEnabled)
  await Promise.all([
    scoringStore.loadStatus(),
    scoringStore.loadModels(),
    nltkStore.checkStatus()
  ])
})
</script>

<style scoped>
.scoring-content {
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

.engines-section h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: var(--color-text-primary);
}

.engine-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 1.25rem;
  margin-bottom: 1rem;
}

.engine-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.engine-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.engine-icon {
  font-size: 1.5rem;
  color: var(--color-primary);
}

.engine-text {
  display: flex;
  flex-direction: column;
}

.engine-name {
  font-weight: 600;
  font-size: 1rem;
  color: var(--color-text-primary);
}

.engine-desc {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}

.installed-models {
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.installed-models h4 {
  margin: 0 0 0.75rem 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.model-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.model-chip {
  padding: 0.4rem 0.75rem;
  background: var(--color-bg);
  border-radius: 20px;
  font-size: 0.8rem;
  color: var(--color-text-primary);
}

.model-chip.installed {
  background: var(--color-success-bg, rgba(34, 197, 94, 0.1));
  color: var(--color-success, #22c55e);
}

.model-options h4 {
  margin: 0 0 0.75rem 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.options-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.model-option {
  padding: 1rem;
  border: 2px solid var(--color-border);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.model-option:hover {
  border-color: var(--color-primary);
}

.model-option.selected {
  border-color: var(--color-primary);
  background: rgba(var(--color-primary-rgb, 99, 102, 241), 0.05);
}

.model-option.installed {
  opacity: 0.7;
}

.option-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.option-name {
  font-weight: 600;
  color: var(--color-text-primary);
}

.installed-badge {
  font-size: 0.7rem;
  color: var(--color-success, #22c55e);
}

.option-desc {
  margin: 0 0 0.5rem 0;
  font-size: 0.8rem;
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.option-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.option-size {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-primary);
}

.option-repo {
  font-size: 0.7rem;
  color: var(--color-text-disabled);
  font-family: monospace;
}

.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
}

.checkbox-label {
  font-size: 0.875rem;
  color: var(--color-success, #22c55e);
}

.primary-btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  font-weight: 500;
}

.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 下载提示 */
.download-hint {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 10px;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.download-hint .hint-icon {
  font-size: 1.25rem;
  color: var(--color-primary);
}

/* 使用说明 */
.usage-note {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--color-bg-secondary);
  border-radius: 12px;
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  font-size: 0.875rem;
  line-height: 1.5;
}

.usage-note svg {
  flex-shrink: 0;
  color: var(--color-primary);
}

.usage-note p {
  margin: 0;
}
  /* ... existing styles ... */
  
  /* Resources Section */
  .resources-section {
    margin-top: 24px;
    padding-top: 24px;
    border-top: 1px solid var(--border-color);
  }
  
  .resources-section h3 {
    margin-bottom: 16px;
    font-size: 16px;
    font-weight: 600;
  }
  
  .resources-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }
  
  .resource-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 16px;
  }
  
  .resource-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
  }
  
  .resource-info {
    display: flex;
    gap: 12px;
  }
  
  .resource-icon {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-tertiary);
    border-radius: 6px;
    color: var(--text-secondary);
  }
  
  .resource-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  
  .resource-name {
    font-weight: 500;
    color: var(--text-primary);
  }
  
  .resource-desc {
    font-size: 12px;
    color: var(--text-secondary);
  }
  
  .download-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 6px;
    border: none;
    font-size: 12px;
  }
  
  .download-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  
  .status-badge {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 4px;
    background: var(--bg-tertiary);
    color: var(--text-secondary);
  }
  
  .status-badge.installed {
    background: var(--success-bg);
    color: var(--success-text);
  }
  
  .nltk-path-hint {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px;
    background: var(--bg-secondary);
    border-radius: 6px;
    font-size: 12px;
    color: var(--text-secondary);
    font-family: monospace;
  }
  
  .spinner {
    width: 14px;
    height: 14px;
    border: 2px solid currentColor;
    border-right-color: transparent;
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }
  
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
</style>




