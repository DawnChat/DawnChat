<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="visible" class="dialog-overlay">
        <div class="dialog-container" @click.stop>
          <div class="dialog-header">
            <h3 class="dialog-title">{{ title }}</h3>
          </div>
          <div class="dialog-content">
            <template v-if="configMode === 'azure'">
              <label class="field">
                <span class="field-label">API Key</span>
                <input
                  class="field-input"
                  type="password"
                  :value="apiKey"
                  :placeholder="apiKeyConfigured ? '留空表示继续使用已保存 Key' : '请输入 Azure API Key'"
                  @input="emit('update:apiKey', ($event.target as HTMLInputElement).value)"
                >
              </label>
              <label class="field">
                <span class="field-label">Region</span>
                <input
                  class="field-input"
                  type="text"
                  :value="region"
                  placeholder="例如 eastasia / japaneast"
                  @input="emit('update:region', ($event.target as HTMLInputElement).value)"
                >
              </label>
            </template>
            <label class="field">
              <span class="field-label">中文默认音色</span>
              <select
                class="field-input"
                :value="defaultVoiceZh"
                @change="emit('update:defaultVoiceZh', ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="item in zhVoiceOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">英文默认音色</span>
              <select
                class="field-input"
                :value="defaultVoiceEn"
                @change="emit('update:defaultVoiceEn', ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="item in enVoiceOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
          </div>
          <div class="dialog-footer">
            <button class="dialog-btn dialog-btn-cancel" :disabled="busy" @click="emit('cancel')">取消</button>
            <button class="dialog-btn dialog-btn-confirm" :disabled="busy" @click="emit('submit')">
              {{ busy ? (configMode === 'dawn' ? '保存中...' : '校验中...') : (configMode === 'dawn' ? '保存' : '校验并保存') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    visible: boolean
    busy: boolean
    title: string
    configMode?: 'azure' | 'dawn'
    apiKey: string
    region: string
    defaultVoiceZh: string
    defaultVoiceEn: string
    zhVoiceOptions: Array<{ value: string; label: string }>
    enVoiceOptions: Array<{ value: string; label: string }>
    apiKeyConfigured: boolean
    errorMessage: string
  }>(),
  { configMode: 'azure' },
)

const emit = defineEmits<{
  'update:apiKey': [value: string]
  'update:region': [value: string]
  'update:defaultVoiceZh': [value: string]
  'update:defaultVoiceEn': [value: string]
  submit: []
  cancel: []
}>()
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.58);
  backdrop-filter: blur(3px);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10000;
}

.dialog-container {
  width: min(520px, calc(100% - 2rem));
  border-radius: 14px;
  background: var(--color-surface-1);
  border: 1px solid var(--color-border);
  box-shadow: 0 22px 48px rgba(0, 0, 0, 0.24);
}

.dialog-header {
  padding: 1rem 1rem 0.5rem 1rem;
}

.dialog-title {
  margin: 0;
  font-size: 1rem;
  color: var(--color-text);
}

.dialog-content {
  padding: 0 1rem 1rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.field-label {
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}

.field-input {
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  color: var(--color-text);
  border-radius: 8px;
  min-height: 34px;
  padding: 0.35rem 0.55rem;
}

.error-text {
  margin: 0;
  font-size: 0.78rem;
  color: var(--color-error);
}

.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.6rem;
  padding: 0 1rem 1rem 1rem;
}

.dialog-btn {
  min-height: 34px;
  border-radius: 10px;
  padding: 0.45rem 0.85rem;
  border: 1px solid var(--color-border);
  background: var(--color-surface-3);
  color: var(--color-text);
  cursor: pointer;
}

.dialog-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.dialog-btn-confirm {
  border-color: color-mix(in srgb, var(--color-primary) 35%, var(--color-border));
  background: color-mix(in srgb, var(--color-primary) 14%, var(--color-surface-3));
  color: var(--color-primary);
}

.dialog-enter-active,
.dialog-leave-active {
  transition: opacity 0.16s ease;
}

.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}
</style>
