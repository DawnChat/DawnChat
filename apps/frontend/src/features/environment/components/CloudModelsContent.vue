<template>
  <div class="cloud-models-content">
    <!-- 头部 -->
    <div class="content-header">
      <div class="header-info">
        <h2 class="flex items-center gap-2">
          <Cloud :size="24" />
          {{ t.models.cloud.title }}
        </h2>
        <p class="subtitle">{{ t.settings.cloudModels.desc }}</p>
      </div>
      <div class="header-status" :class="{ ready: hasConfiguredProviders }">
        <span v-if="hasConfiguredProviders" class="flex items-center gap-1">
          <CheckCircle2 :size="16" />
          {{ t.models.cloud.configuredCount.replace('{count}', String(configuredCount)) }}
        </span>
        <span v-else class="flex items-center gap-1">
          <AlertTriangle :size="16" />
          {{ t.models.cloud.noConfigured }}
        </span>
      </div>
    </div>

    <!-- 厂商列表 -->
    <div class="providers-list">
      <div 
        v-for="provider in providers" 
        :key="provider.id" 
        class="provider-card"
      >
        <div class="provider-header" @click="toggleProvider(provider.id)">
          <div class="provider-info">
            <span class="provider-icon">
              <component :is="getProviderIconComponent(provider.id)" :size="24" />
            </span>
            <div class="provider-text">
              <span class="provider-name">{{ provider.name }}</span>
              <span class="provider-status" :class="{ configured: provider.is_configured }">
                {{ provider.is_configured ? t.common.configured : t.common.notConfigured }}
              </span>
            </div>
          </div>
          <span class="expand-icon">
            <ChevronUp v-if="expandedProviders.includes(provider.id)" :size="16" />
            <ChevronDown v-else :size="16" />
          </span>
        </div>

        <!-- 展开的配置区域 -->
        <div v-if="expandedProviders.includes(provider.id)" class="provider-config">
          <!-- API Key 输入 -->
          <div class="config-group">
            <label class="config-label">API Key</label>
            <div class="api-key-input-wrapper">
              <input 
                :type="showApiKey[provider.id] ? 'text' : 'password'"
                v-model="providerConfigs[provider.id].apiKey"
                :placeholder="provider.is_configured ? t.settings.cloudModels.apiKeyPlaceholderConfigured : t.settings.cloudModels.apiKeyPlaceholder"
                class="config-input"
              />
              <button 
                type="button" 
                class="toggle-visibility-btn"
                @click="toggleApiKeyVisibility(provider.id)"
              >
                <Eye v-if="showApiKey[provider.id]" :size="16" />
                <EyeOff v-else :size="16" />
              </button>
            </div>
          </div>

          <!-- 保存按钮 -->
          <div class="config-actions">
            <button 
              v-if="provider.is_configured"
              type="button" 
              class="delete-btn"
              @click="deleteProviderConfig(provider.id)"
              :disabled="saving[provider.id]"
            >
              <Trash2 :size="16" class="mr-1" />
              {{ t.common.deleteConfig }}
            </button>
            <button 
              type="button" 
              class="save-btn ui-btn ui-btn--emphasis"
              @click="saveProviderConfig(provider.id)"
              :disabled="saving[provider.id]"
            >
              <Save v-if="!saving[provider.id]" :size="16" class="mr-1" />
              {{ saving[provider.id] ? t.common.saving : t.common.save }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 提示信息 -->
    <div class="info-note">
      <span class="note-icon">
        <Lightbulb :size="18" />
      </span>
      <span class="note-text">
        {{ t.settings.cloudModels.securityNote }}
      </span>
    </div>

    <ConfirmDialog
      v-model:visible="dialogVisible"
      icon="🔐"
      :title="dialogTitle"
      :message="dialogMessage"
      :confirm-text="dialogConfirmText"
      :cancel-text="dialogCancelText"
      @confirm="handleDialogConfirm"
      @cancel="handleDialogCancel"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onActivated } from 'vue'
import { logger } from '@/utils/logger'
import { useI18n } from '@/composables/useI18n'
import { useCloudKeychainPrompt } from '@/composables/useCloudKeychainPrompt'
import { buildBackendUrl } from '@/utils/backendUrl'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import { 
  Cloud, 
  CheckCircle2, 
  AlertTriangle,
  Trash2,
  Save,
  Bot, 
  Sparkles, 
  Brain, 
  Search, 
  Moon, 
  Zap, 
  Globe, 
  ChevronUp, 
  ChevronDown, 
  Eye, 
  EyeOff, 
  Lightbulb
} from 'lucide-vue-next'

const { t } = useI18n()


interface Provider {
  id: string
  name: string
  is_configured: boolean
  model_count: number
}

interface ProviderConfig {
  apiKey: string
}

// 状态
const providers = ref<Provider[]>([])
const expandedProviders = ref<string[]>([])
const showApiKey = reactive<Record<string, boolean>>({})
const saving = reactive<Record<string, boolean>>({})
const providerConfigs = reactive<Record<string, ProviderConfig>>({})
const {
  dialogVisible,
  dialogTitle,
  dialogMessage,
  dialogConfirmText,
  dialogCancelText,
  shouldShowMacOsKeychainHint,
  confirmMacOsKeychainHint,
  handleDialogConfirm,
  handleDialogCancel,
} = useCloudKeychainPrompt()

// 计算属性
const hasConfiguredProviders = computed(() => providers.value.some((p: Provider) => p.is_configured))
const configuredCount = computed(() => providers.value.filter((p: Provider) => p.is_configured).length)

// 获取厂商图标
const getProviderIconComponent = (providerId: string) => {
  const icons: Record<string, any> = {
    openai: Bot,
    gemini: Sparkles,
    anthropic: Brain,
    deepseek: Search,
    qwen: Cloud,
    moonshot: Moon,
    zhipu: Zap,
    siliconflow: Globe,
    openrouter: Globe
  }
  return icons[providerId] || Globe
}

// 切换厂商展开状态
const toggleProvider = (providerId: string) => {
  const index = expandedProviders.value.indexOf(providerId)
  if (index === -1) {
    expandedProviders.value.push(providerId)
    loadProviderConfig(providerId)
  } else {
    expandedProviders.value.splice(index, 1)
  }
}

// 切换 API Key 可见性
const toggleApiKeyVisibility = (providerId: string) => {
  showApiKey[providerId] = !showApiKey[providerId]
}

// 加载厂商列表
const loadProviders = async () => {
  try {
    const res = await fetch(buildBackendUrl('/api/cloud/providers'))
    if (res.ok) {
      const data = await res.json()
      const rawProviders: Provider[] = data.providers || []
      providers.value = rawProviders.sort((a, b) => {
        if (a.id === 'siliconflow') return -1
        if (b.id === 'siliconflow') return 1
        return 0
      })
      
      for (const provider of providers.value) {
        if (!providerConfigs[provider.id]) {
          providerConfigs[provider.id] = {
            apiKey: ''
          }
        }
      }
    }
  } catch (e) {
    logger.error('加载厂商列表失败', e)
  }
}

// 加载单个厂商配置
const loadProviderConfig = async (providerId: string) => {
  try {
    const detailRes = await fetch(buildBackendUrl(`/api/cloud/providers/${providerId}`))
    if (detailRes.ok) {
      await detailRes.json()
    }
  } catch (e) {
    logger.error(`加载厂商配置失败: ${providerId}`, e)
  }
}

// 保存厂商配置
const saveProviderConfig = async (providerId: string) => {
  if (shouldShowMacOsKeychainHint() && !(await confirmMacOsKeychainHint())) {
    return
  }

  saving[providerId] = true
  try {
    const config = providerConfigs[providerId]

    if (config.apiKey) {
      const apiKeyRes = await fetch(buildBackendUrl(`/api/cloud/providers/${providerId}`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: providerId,
          api_key: config.apiKey
        })
      })
      if (!apiKeyRes.ok) {
        throw new Error(t.value.settings.cloudModels.saveApiKeyFailed)
      }
    }

    config.apiKey = ''
    await loadProviders()
    
    logger.info(t.value.settings.cloudModels.saveSuccess.replace('{provider}', providerId))
  } catch (e) {
    logger.error(t.value.settings.cloudModels.saveConfigFailed.replace('{provider}', providerId), e)
  } finally {
    saving[providerId] = false
  }
}

// 删除厂商配置
const deleteProviderConfig = async (providerId: string) => {
  if (!confirm(t.value.settings.cloudModels.confirmDelete.replace('{name}', providerId))) {
    return
  }

  saving[providerId] = true
  try {
    const res = await fetch(buildBackendUrl(`/api/cloud/providers/${providerId}`), {
      method: 'DELETE'
    })
    if (res.ok) {
      providerConfigs[providerId] = {
        apiKey: ''
      }
      await loadProviders()
      logger.info(t.value.settings.cloudModels.deleteSuccess.replace('{provider}', providerId))
    }
  } catch (e) {
    logger.error(t.value.settings.cloudModels.deleteConfigFailed.replace('{provider}', providerId), e)
  } finally {
    saving[providerId] = false
  }
}

onMounted(() => {
  loadProviders()
})

onActivated(() => {
  loadProviders()
})
</script>

<style scoped>
.cloud-models-content {
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

.providers-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.provider-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  overflow: hidden;
}

.provider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  cursor: pointer;
  transition: background 0.2s;
}

.provider-header:hover {
  background: var(--color-hover);
}

.provider-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.provider-icon {
  font-size: 1.5rem;
}

.provider-text {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.provider-name {
  font-weight: 600;
  color: var(--color-text-primary);
}

.provider-status {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
}

.provider-status.configured {
  color: var(--color-success, #22c55e);
}

.expand-icon {
  color: var(--color-text-secondary);
  font-size: 0.75rem;
}

.provider-config {
  padding: 1rem 1.25rem 1.25rem;
  border-top: 1px solid var(--color-border);
  background: var(--color-bg);
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.config-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.config-label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-primary);
}

.api-key-input-wrapper {
  display: flex;
  gap: 0.5rem;
}

.config-input {
  flex: 1;
  padding: 0.625rem 0.875rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text-primary);
  font-size: 0.875rem;
}

.config-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.toggle-visibility-btn {
  padding: 0.5rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  cursor: pointer;
  font-size: 1rem;
}

.toggle-visibility-btn:hover {
  background: var(--color-hover);
}

.config-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding-top: 0.5rem;
}

.save-btn {
  padding: 0.625rem 1.5rem;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.delete-btn {
  padding: 0.625rem 1.5rem;
  background: transparent;
  color: var(--color-danger, #ef4444);
  border: 1px solid var(--color-danger, #ef4444);
  border-radius: 8px;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s;
}

.delete-btn:hover:not(:disabled) {
  background: var(--color-danger, #ef4444);
  color: white;
}

.delete-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.info-note {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--color-bg-secondary);
  border-radius: 8px;
}

.note-icon {
  flex-shrink: 0;
  font-size: 1.1rem;
}

.note-text {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
</style>
