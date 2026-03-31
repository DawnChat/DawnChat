<template>
  <div class="asr-content">
    <!-- 头部 -->
    <div class="content-header">
      <div class="header-info">
        <h2 class="flex items-center gap-2">
          <Mic :size="24" />
          {{ t.models.asr.title }}
        </h2>
        <p class="subtitle">{{ t.models.asr.subtitle }}</p>
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
      
      <!-- Whisper -->
      <div class="engine-card">
        <div class="engine-header">
          <div class="engine-info">
            <span class="engine-icon">
              <Headphones :size="24" />
            </span>
            <div class="engine-text">
              <span class="engine-name">Whisper</span>
              <span class="engine-desc">{{ t.models.asr.whisperDesc }}</span>
            </div>
          </div>
        </div>
        
        <!-- 已安装的模型 -->
        <div v-if="installedModels.length > 0" class="installed-models">
          <h4>{{ t.common.installed }} {{ t.models.title }}</h4>
          <div class="model-chips">
            <span v-for="modelId in installedModels" :key="modelId" class="model-chip installed flex items-center gap-1">
              <CheckCircle2 :size="12" />
              {{ modelId }}
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
              v-for="option in modelOptions" 
              :key="option.id"
              class="model-option"
              :class="{ 
                selected: selectedModel === option.id, 
                installed: installedModels.includes(option.id) 
              }"
              @click="selectedModel = option.id"
            >
              <div class="option-header">
                <span class="option-name">{{ option.name }}</span>
                <span v-if="installedModels.includes(option.id)" class="installed-badge flex items-center gap-1">
                  <CheckCircle2 :size="12" />
                  {{ t.common.installed }}
                </span>
              </div>
              <p class="option-desc">{{ option.description }}</p>
              <span class="option-repo">{{ option.hfRepoId }}</span>
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
              :disabled="!selectedModel || installedModels.includes(selectedModel) || isDownloading"
              @click="handleDownload"
            >
              <template v-if="installedModels.includes(selectedModel)">{{ t.common.installed }}</template>
              <template v-else>
                <Download :size="16" />
                {{ t.common.download }}
              </template>
            </button>
          </div>
        </div>
      </div>
      
      <!-- 更多引擎提示 -->
      <div class="more-engines flex flex-col items-center gap-2">
        <Construction :size="24" />
        <p>{{ t.models.asr.moreEnginesComing }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  Mic,
  CheckCircle2,
  AlertTriangle,
  Headphones,
  Download,
  Rocket,
  Construction
} from 'lucide-vue-next'
import { useToolsStore } from '@/stores/toolsStore'
import type { ModelOption } from '@/stores/toolsStore'
import { useI18n } from '@/composables/useI18n'
import { getProviderMirrorEnabled, setProviderMirrorEnabled } from '@/composables/useResourceAccessMirror'

const { t } = useI18n()
const toolsStore = useToolsStore()

const selectedModel = ref('')
const useMirror = ref(true)

// Store 状态
const installedModels = computed(() => toolsStore.whisperStatus.installedModels)
const hasInstalledModels = computed(() => installedModels.value.length > 0)
const isDownloading = computed(() => toolsStore.activeWhisperDownloads.length > 0)

// 模型选项
const modelOptions = computed<ModelOption[]>(() => {
  const tool = toolsStore.marketTools.find(t => t.id === 'whisper-asr')
  return tool?.modelOptions || [
    { id: 'tiny', name: 'Tiny', description: t.value.models.asr.options.tiny, hfRepoId: 'openai/whisper-tiny' },
    { id: 'base', name: 'Base', description: t.value.models.asr.options.base, hfRepoId: 'openai/whisper-base' },
    { id: 'small', name: 'Small', description: t.value.models.asr.options.small, hfRepoId: 'openai/whisper-small' },
    { id: 'medium', name: 'Medium', description: t.value.models.asr.options.medium, hfRepoId: 'openai/whisper-medium' },
    { id: 'large', name: 'Large', description: t.value.models.asr.options.large, hfRepoId: 'openai/whisper-large-v3' }
  ]
})

// 方法
const handleDownload = async () => {
  if (!selectedModel.value) return
  toolsStore.setUseMirror(useMirror.value)
  await toolsStore.downloadWhisperModel(selectedModel.value, false)
}

async function handleMirrorToggle(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  useMirror.value = checked
  toolsStore.setUseMirror(checked)
  await setProviderMirrorEnabled('huggingface', checked)
}

onMounted(async () => {
  const mirrorEnabled = await getProviderMirrorEnabled('huggingface')
  useMirror.value = mirrorEnabled
  toolsStore.setUseMirror(mirrorEnabled)
  await toolsStore.loadWhisperStatus()
  await toolsStore.loadMarketTools()
})
</script>

<style scoped>
.asr-content {
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
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
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
}

.more-engines {
  text-align: center;
  padding: 2rem;
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
  border-radius: 12px;
  border: 1px dashed var(--color-border);
}
</style>

