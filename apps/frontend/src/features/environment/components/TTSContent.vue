<template>
  <div class="tts-content">
    <!-- 头部 -->
    <div class="content-header">
      <div class="header-info">
        <h2 class="flex items-center gap-2"><Mic :size="24" /> {{ t.models.tts.title }}</h2>
        <p class="subtitle">{{ t.models.tts.subtitle }}</p>
      </div>
      <div class="header-status" :class="{ ready: hasInstalledModels }">
        <span v-if="hasInstalledModels" class="flex items-center gap-1"><CheckCircle2 :size="16" /> {{ t.common.installed }} {{ installedModels.length }} {{ t.models.title }}</span>
        <span v-else class="flex items-center gap-1"><AlertTriangle :size="16" /> {{ t.models.tts.noInstalled }}</span>
      </div>
    </div>
    
    <!-- 引擎列表 -->
    <div class="engines-section">
      <h3>{{ t.common.availableEngines }}</h3>
      
      <!-- VibeVoice -->
      <div class="engine-card">
        <div class="engine-header">
          <div class="engine-info">
            <span class="engine-icon"><Music :size="24" /></span>
            <div class="engine-text">
              <span class="engine-name">VibeVoice</span>
              <span class="engine-desc">{{ t.models.tts.vibevoiceDesc }}</span>
            </div>
          </div>
        </div>
        
        <!-- 已安装的模型 -->
        <div v-if="vibevoiceInstalledModels.length > 0" class="installed-models">
          <h4>{{ t.common.installed }} {{ t.models.title }}</h4>
          <div class="model-chips">
            <span v-for="modelId in vibevoiceInstalledModels" :key="modelId" class="model-chip installed flex items-center gap-1">
              <CheckCircle2 :size="12" /> {{ modelId }}
            </span>
          </div>
        </div>
        
        <!-- 下载提示（如果正在下载） -->
        <div v-if="isVibevoiceDownloading" class="download-hint">
          <span class="hint-icon"><Download :size="20" /></span>
          <span>{{ t.common.downloadingInTask }}</span>
        </div>
        
        <!-- 模型选择 -->
        <div v-else class="model-options">
          <h4>{{ t.common.modelSize }}</h4>
          <div class="options-grid">
            <div 
              v-for="option in vibevoiceModelOptions" 
              :key="option.id"
              class="model-option"
              :class="{ 
                selected: selectedVibevoiceModel === option.id, 
                installed: vibevoiceInstalledModels.includes(option.id) 
              }"
              @click="selectedVibevoiceModel = option.id"
            >
              <div class="option-header">
                <span class="option-name">{{ option.name }}</span>
                <span v-if="vibevoiceInstalledModels.includes(option.id)" class="installed-badge flex items-center gap-1"><CheckCircle2 :size="12" /> {{ t.common.installed }}</span>
              </div>
              <p class="option-desc">{{ option.description }}</p>
              <span class="option-repo">{{ option.hfRepoId }}</span>
            </div>
          </div>
          
          <div class="action-bar">
            <label class="checkbox-item">
              <input type="checkbox" :checked="useMirror" @change="handleMirrorToggle" />
              <span class="checkbox-label flex items-center gap-1"><Rocket :size="16" /> {{ t.common.useMirror }}</span>
            </label>
            <button 
              class="primary-btn ui-btn ui-btn--emphasis flex items-center gap-1"
              :disabled="!selectedVibevoiceModel || vibevoiceInstalledModels.includes(selectedVibevoiceModel) || isVibevoiceDownloading"
              @click="handleVibevoiceDownload"
            >
              <template v-if="vibevoiceInstalledModels.includes(selectedVibevoiceModel)">{{ t.common.installed }}</template>
              <template v-else><Download :size="16" /> {{ t.common.download }}</template>
            </button>
          </div>
        </div>
      </div>
      
      <!-- CosyVoice -->
      <div class="engine-card">
        <div class="engine-header">
          <div class="engine-info">
            <span class="engine-icon"><Headphones :size="24" /></span>
            <div class="engine-text">
              <span class="engine-name">CosyVoice3</span>
              <span class="engine-desc">{{ t.models.tts.cosyvoiceDesc }}</span>
            </div>
          </div>
        </div>
        
        <!-- 已安装的模型 -->
        <div v-if="cosyvoiceInstalledModels.length > 0" class="installed-models">
          <h4>{{ t.common.installed }} {{ t.models.title }}</h4>
          <div class="model-chips">
            <span v-for="modelId in cosyvoiceInstalledModels" :key="modelId" class="model-chip installed flex items-center gap-1">
              <CheckCircle2 :size="12" /> {{ cosyvoiceModelName(modelId) }}
            </span>
          </div>
        </div>
        
        <!-- 下载提示（如果正在下载） -->
        <div v-if="isCosyvoiceDownloading" class="download-hint">
          <span class="hint-icon"><Download :size="20" /></span>
          <span>{{ t.common.downloadingInTask }}</span>
        </div>
        
        <!-- 模型选择 -->
        <div v-else class="model-options">
          <h4>{{ t.common.modelSize }}</h4>
          <div class="options-grid">
            <div 
              v-for="option in cosyvoiceModelOptions" 
              :key="option.id"
              class="model-option"
              :class="{ 
                selected: selectedCosyvoiceModel === option.id, 
                installed: cosyvoiceInstalledModels.includes(option.id) 
              }"
              @click="selectedCosyvoiceModel = option.id"
            >
              <div class="option-header">
                <span class="option-name">{{ option.name }}</span>
                <span v-if="cosyvoiceInstalledModels.includes(option.id)" class="installed-badge flex items-center gap-1"><CheckCircle2 :size="12" /> {{ t.common.installed }}</span>
              </div>
              <p class="option-desc">{{ option.description }}</p>
              <span class="option-repo">{{ option.hfRepoId }}</span>
            </div>
          </div>
          
          <div class="action-bar">
            <label class="checkbox-item">
              <input type="checkbox" :checked="useMirror" @change="handleMirrorToggle" />
              <span class="checkbox-label flex items-center gap-1"><Rocket :size="16" /> {{ t.common.useMirror }}</span>
            </label>
            <button 
              class="primary-btn ui-btn ui-btn--emphasis flex items-center gap-1"
              :disabled="!selectedCosyvoiceModel || cosyvoiceInstalledModels.includes(selectedCosyvoiceModel) || isCosyvoiceDownloading"
              @click="handleCosyvoiceDownload"
            >
              <template v-if="cosyvoiceInstalledModels.includes(selectedCosyvoiceModel)">{{ t.common.installed }}</template>
              <template v-else><Download :size="16" /> {{ t.common.download }}</template>
            </button>
          </div>
        </div>
      </div>

      <!-- 更多引擎提示 -->
      <div class="more-engines">
        <p class="flex items-center justify-center gap-2"><Hammer :size="16" /> {{ t.models.tts.moreEnginesComing }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { 
  Music, 
  Headphones,
  Mic, 
  CheckCircle2, 
  AlertTriangle, 
  Download, 
  Rocket, 
  Hammer 
} from 'lucide-vue-next'
import { useToolsStore } from '@/stores/toolsStore'
import type { ModelOption } from '@/stores/toolsStore'
import { useI18n } from '@/composables/useI18n'
import { getProviderMirrorEnabled, setProviderMirrorEnabled } from '@/composables/useResourceAccessMirror'

const { t } = useI18n()
const toolsStore = useToolsStore()

const useMirror = ref(true)
const selectedVibevoiceModel = ref('')
const selectedCosyvoiceModel = ref('')

// Store 状态
const vibevoiceInstalledModels = computed(() => toolsStore.vibevoiceStatus.installedModels)
const cosyvoiceInstalledModels = computed(() => toolsStore.cosyvoiceStatus.installedModels)
const installedModels = computed(() => Array.from(new Set([...vibevoiceInstalledModels.value, ...cosyvoiceInstalledModels.value])))
const hasInstalledModels = computed(() => installedModels.value.length > 0)
const isVibevoiceDownloading = computed(() => toolsStore.activeVibevoiceDownloads.length > 0)
const isCosyvoiceDownloading = computed(() => toolsStore.activeCosyvoiceDownloads.length > 0)

// 模型选项（从市场工具获取）
const vibevoiceModelOptions = computed<ModelOption[]>(() => {
  const tool = toolsStore.marketTools.find(t => t.id === 'vibevoice-tts')
  return tool?.modelOptions || [
    { id: '0.5B', name: '0.5B', description: t.value.models.tts.options.small, hfRepoId: 'vibevoice/VibeVoice-Realtime-0.5B' },
    { id: '1.5B', name: '1.5B', description: t.value.models.tts.options.medium, hfRepoId: 'vibevoice/VibeVoice-1.5B' },
    { id: '7B', name: '7B', description: t.value.models.tts.options.large, hfRepoId: 'vibevoice/VibeVoice-7B' }
  ]
})

const cosyvoiceModelOptions = computed<ModelOption[]>(() => {
  const tool = toolsStore.marketTools.find(t => t.id === 'cosyvoice-tts')
  return tool?.modelOptions || []
})

const cosyvoiceModelName = (modelId: string) => {
  const option = cosyvoiceModelOptions.value.find(o => o.id === modelId)
  return option?.name || modelId
}

// 方法
const handleVibevoiceDownload = async () => {
  if (!selectedVibevoiceModel.value) return
  toolsStore.setUseMirror(useMirror.value)
  await toolsStore.downloadVibevoiceModel(selectedVibevoiceModel.value, false)
}

const handleCosyvoiceDownload = async () => {
  if (!selectedCosyvoiceModel.value) return
  toolsStore.setUseMirror(useMirror.value)
  await toolsStore.downloadCosyvoiceModel(selectedCosyvoiceModel.value, false)
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
  await toolsStore.loadVibevoiceStatus()
  await toolsStore.loadCosyvoiceStatus()
  await toolsStore.loadMarketTools()
})
</script>

<style scoped>
.tts-content {
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

.inline-icon {
  display: inline-block;
  vertical-align: middle;
  margin-right: 0.5rem;
  color: var(--color-primary);
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
  flex-shrink: 0;
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
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
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
