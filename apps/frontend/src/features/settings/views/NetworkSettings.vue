<template>
  <div class="network-settings">
    <div class="settings-section">
      <h3 class="section-title">{{ t.settings.proxy.title }}</h3>
      <div class="settings-group">
        <label class="setting-item checkbox-item">
          <span class="setting-label">{{ t.settings.proxy.enabled }}</span>
          <input type="checkbox" v-model="settings.enabled" class="setting-checkbox" />
        </label>

        <div v-if="settings.enabled" class="proxy-inputs">
          <p class="proxy-hint">
            <Lightbulb :size="16" class="inline-icon mr-1" /> {{ t.settings.proxy.helpText }}
          </p>
          
          <div class="input-group">
            <label>{{ t.settings.proxy.http }}</label>
            <input 
              type="text" 
              v-model="settings.http_proxy" 
              placeholder="http://127.0.0.1:7890"
              class="setting-input"
              @input="syncHttpsProxy"
            />
          </div>

          <div class="input-group">
            <label class="label-with-sync">
              <span>{{ t.settings.proxy.https }}</span>
              <label class="sync-checkbox">
                <input type="checkbox" v-model="syncWithHttp" />
                <span class="sync-label">{{ t.settings.proxy.sameAsHttp }}</span>
              </label>
            </label>
            <input 
              type="text" 
              v-model="settings.https_proxy" 
              placeholder="http://127.0.0.1:7890"
              class="setting-input"
              :disabled="syncWithHttp"
            />
          </div>

          <div class="input-group">
            <label>{{ t.settings.proxy.noProxy }}</label>
            <input 
              type="text" 
              v-model="settings.no_proxy" 
              class="setting-input"
            />
          </div>
        </div>

        <div class="actions">
            <button @click="saveSettings" class="save-btn ui-btn ui-btn--emphasis" :disabled="saving">
                {{ saving ? t.common.loading : t.settings.proxy.save }}
            </button>
        </div>
      </div>
    </div>

    <div class="settings-section">
      <h3 class="section-title">{{ t.settings.networkPolicy.title }}</h3>
      <div class="settings-group">
        <div class="input-group">
          <label>{{ t.settings.networkPolicy.globalMode }}</label>
          <PluginDevInlineSelect
            :model-value="resourceSettings.global_mode"
            :options="modeOptions"
            :label="t.settings.networkPolicy.globalMode"
            class="setting-select"
            @update:model-value="updateGlobalMode"
          />
        </div>

        <div class="input-group">
          <label>{{ t.settings.networkPolicy.huggingface }}</label>
          <PluginDevInlineSelect
            :model-value="resourceSettings.providers.huggingface.mode"
            :options="modeOptions"
            :label="t.settings.networkPolicy.huggingface"
            class="setting-select"
            @update:model-value="(value) => updateProviderMode('huggingface', value)"
          />
        </div>

        <div class="input-group">
          <label>{{ t.settings.networkPolicy.github }}</label>
          <PluginDevInlineSelect
            :model-value="resourceSettings.providers.github.mode"
            :options="modeOptions"
            :label="t.settings.networkPolicy.github"
            class="setting-select"
            @update:model-value="(value) => updateProviderMode('github', value)"
          />
        </div>

        <div class="input-group">
          <label>{{ t.settings.networkPolicy.playwright }}</label>
          <PluginDevInlineSelect
            :model-value="resourceSettings.providers.playwright.mode"
            :options="modeOptions"
            :label="t.settings.networkPolicy.playwright"
            class="setting-select"
            @update:model-value="(value) => updateProviderMode('playwright', value)"
          />
        </div>

        <div class="input-group">
          <label>{{ t.settings.networkPolicy.pypi }}</label>
          <PluginDevInlineSelect
            :model-value="resourceSettings.providers.pypi.mode"
            :options="modeOptions"
            :label="t.settings.networkPolicy.pypi"
            class="setting-select"
            @update:model-value="(value) => updateProviderMode('pypi', value)"
          />
        </div>

        <div class="input-group">
          <label class="setting-item checkbox-item">
            <span class="setting-label">{{ t.settings.networkPolicy.autoProbe }}</span>
            <input
              type="checkbox"
              v-model="resourceSettings.auto_probe.enabled"
              class="setting-checkbox"
            />
          </label>
        </div>

        <div class="actions">
          <button @click="probeResourceAccess" class="save-btn secondary-btn ui-btn ui-btn--neutral" :disabled="probing">
            {{ probing ? t.common.loading : t.settings.networkPolicy.probeNow }}
          </button>
          <button @click="saveResourceSettings" class="save-btn ui-btn ui-btn--emphasis" :disabled="savingPolicy">
            {{ savingPolicy ? t.common.loading : t.settings.networkPolicy.save }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useI18n } from '@/composables/useI18n'
import { buildBackendUrl } from '@/utils/backendUrl'
import { logger } from '@/utils/logger'
import { Lightbulb } from 'lucide-vue-next'
import PluginDevInlineSelect from '@/features/coding-agent/components/plugin-dev-chat/PluginDevInlineSelect.vue'
import type { PluginDevInlineSelectOption } from '@/features/coding-agent/components/plugin-dev-chat/PluginDevInlineSelect.vue'

const { t } = useI18n()
const saving = ref(false)
const savingPolicy = ref(false)
const probing = ref(false)
const syncWithHttp = ref(true)

interface ProxySettings {
  enabled: boolean
  http_proxy: string
  https_proxy: string
  no_proxy: string
}

type AccessMode = 'auto' | 'direct_only' | 'mirror_only' | 'prefer_direct' | 'prefer_mirror'

interface ProviderPolicy {
  mode: AccessMode
  mirror_url?: string
  direct_url?: string
  mirror_prefix?: string
  mirror_host?: string
  direct_host?: string
}

interface ResourceAccessSettings {
  global_mode: AccessMode
  providers: {
    huggingface: ProviderPolicy
    github: ProviderPolicy
    playwright: ProviderPolicy
    pypi: ProviderPolicy
  }
  auto_probe: {
    enabled: boolean
    timeout_ms: number
  }
}

const settings = ref<ProxySettings>({
  enabled: false,
  http_proxy: '',
  https_proxy: '',
  no_proxy: 'localhost,127.0.0.1'
})

const resourceSettings = ref<ResourceAccessSettings>({
  global_mode: 'auto',
  providers: {
    huggingface: {
      mode: 'auto',
      mirror_url: 'https://hf-mirror.com',
      direct_url: 'https://huggingface.co'
    },
    github: {
      mode: 'auto',
      mirror_prefix: 'https://ghproxy.com/'
    },
    playwright: {
      mode: 'auto',
      mirror_host: 'https://npmmirror.com/mirrors/playwright',
      direct_host: ''
    },
    pypi: {
      mode: 'auto',
      mirror_url: 'https://pypi.tuna.tsinghua.edu.cn/simple',
      direct_url: 'https://pypi.org/simple'
    }
  },
  auto_probe: {
    enabled: true,
    timeout_ms: 2500
  }
})

const modeOptions: PluginDevInlineSelectOption[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'prefer_direct', label: 'Prefer Direct' },
  { value: 'prefer_mirror', label: 'Prefer Mirror' },
  { value: 'direct_only', label: 'Direct Only' },
  { value: 'mirror_only', label: 'Mirror Only' }
]

const updateGlobalMode = (value: string) => {
  resourceSettings.value.global_mode = value as AccessMode
}

const updateProviderMode = (provider: keyof ResourceAccessSettings['providers'], value: string) => {
  resourceSettings.value.providers[provider].mode = value as AccessMode
}

// 当勾选"与 HTTP 相同"时，自动同步
const syncHttpsProxy = () => {
  if (syncWithHttp.value) {
    settings.value.https_proxy = settings.value.http_proxy
  }
}

// 监听 syncWithHttp 变化
watch(syncWithHttp, (newVal: boolean) => {
  if (newVal) {
    settings.value.https_proxy = settings.value.http_proxy
  }
})

const fetchSettings = async () => {
  try {
    const res = await fetch(buildBackendUrl('/api/network/proxy'))
    if (res.ok) {
      const data = await res.json()
      settings.value = {
        enabled: data.enabled ?? false,
        http_proxy: data.http_proxy ?? '',
        https_proxy: data.https_proxy ?? '',
        no_proxy: data.no_proxy ?? 'localhost,127.0.0.1'
      }
      // 判断是否应该勾选"与 HTTP 相同"
      syncWithHttp.value = !settings.value.https_proxy || 
        settings.value.https_proxy === settings.value.http_proxy
    }
  } catch (e) {
    logger.error('Failed to fetch proxy settings', e)
  }
}

const saveSettings = async () => {
  saving.value = true
  try {
    const res = await fetch(buildBackendUrl('/api/network/proxy'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(settings.value)
    })
    if (res.ok) {
      window.alert((t.value?.settings?.networkPolicy?.restartNotice as string) || '配置已保存，重启后生效')
    } else {
      throw new Error('Save failed')
    }
  } catch (e) {
    logger.error('Failed to save proxy settings', e)
  } finally {
    saving.value = false
  }
}

const fetchResourceSettings = async () => {
  try {
    const res = await fetch(buildBackendUrl('/api/network/resource-access'))
    if (!res.ok) {
      throw new Error(`fetch_failed_${res.status}`)
    }
    const data = await res.json()
    resourceSettings.value = {
      ...resourceSettings.value,
      ...data,
      providers: {
        ...resourceSettings.value.providers,
        ...(data.providers || {})
      },
      auto_probe: {
        ...resourceSettings.value.auto_probe,
        ...(data.auto_probe || {})
      }
    }
  } catch (e) {
    logger.error('Failed to fetch resource access settings', e)
  }
}

const saveResourceSettings = async () => {
  savingPolicy.value = true
  try {
    const res = await fetch(buildBackendUrl('/api/network/resource-access'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(resourceSettings.value)
    })
    if (!res.ok) {
      throw new Error(`save_failed_${res.status}`)
    }
    window.alert((t.value?.settings?.networkPolicy?.restartNotice as string) || '配置已保存，重启后生效')
  } catch (e) {
    logger.error('Failed to save resource access settings', e)
  } finally {
    savingPolicy.value = false
  }
}

const probeResourceAccess = async () => {
  probing.value = true
  try {
    const res = await fetch(buildBackendUrl('/api/network/probe'), {
      method: 'POST'
    })
    if (!res.ok) {
      throw new Error(`probe_failed_${res.status}`)
    }
    await fetchResourceSettings()
  } catch (e) {
    logger.error('Failed to probe network resources', e)
  } finally {
    probing.value = false
  }
}

onMounted(() => {
  fetchSettings()
  fetchResourceSettings()
})
</script>

<style scoped>
.network-settings {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  padding: 1.5rem;
}

.settings-section {
  padding-bottom: 2rem;
  border-bottom: 1px solid var(--color-border);
}

.section-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 1rem 0;
}

.settings-group {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.checkbox-item {
  cursor: pointer;
}

.setting-label {
  font-size: 1rem;
  color: var(--color-text-primary);
}

.setting-checkbox {
  width: 1.2rem;
  height: 1.2rem;
  cursor: pointer;
}

.proxy-inputs {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-left: 1rem;
  border-left: 2px solid var(--color-border);
}

.proxy-hint {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary, #f5f5f5);
  padding: 0.75rem 1rem;
  border-radius: 0.5rem;
  margin: 0;
  line-height: 1.6;
}

.proxy-hint code {
  background: var(--color-bg-tertiary, #e0e0e0);
  padding: 0.15rem 0.4rem;
  border-radius: 0.25rem;
  font-family: monospace;
  font-size: 0.85em;
}

.label-with-sync {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sync-checkbox {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
}

.sync-checkbox input {
  width: 1rem;
  height: 1rem;
  cursor: pointer;
}

.sync-label {
  font-size: 0.8rem;
  color: var(--color-text-tertiary, #888);
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.input-group label {
  font-size: 0.9rem;
  color: var(--color-text-secondary);
}

.setting-input {
  padding: 0.5rem 1rem;
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 0.5rem;
  color: var(--color-text-primary);
  font-size: 1rem;
  width: 100%;
  max-width: 400px;
  transition: all 0.15s ease-in-out;
}

.setting-input:focus {
  border-color: var(--color-primary);
  outline: none;
}

.setting-input:disabled {
  background: var(--color-bg-secondary, #f5f5f5);
  color: var(--color-text-tertiary, #888);
  cursor: not-allowed;
}

.setting-select {
  width: 100%;
  max-width: 400px;
  cursor: pointer;
}

.actions {
  margin-top: 1rem;
  display: flex;
  gap: 0.75rem;
}

.save-btn {
  padding: 0.5rem 1.5rem;
  border: none;
  border-radius: 0.5rem;
  font-size: 1rem;
}

.save-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.secondary-btn {
  border: 1px solid var(--color-button-neutral-border);
}
</style>
