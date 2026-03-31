<template>
  <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
    <div class="modal-panel">
      <div class="header">
        <h3>{{ t.apps.createApp }}</h3>
        <button class="icon-btn" @click="$emit('close')">×</button>
      </div>

      <div class="body">
        <label class="label">{{ t.apps.appType }}</label>
        <div class="type-row">
          <button
            class="type-btn"
            :class="{ active: form.appType === 'desktop', 'ui-selected': form.appType === 'desktop' }"
            @click="setAppType('desktop')"
          >
            {{ t.apps.desktopApp }}
          </button>
          <button
            class="type-btn"
            :class="{ active: form.appType === 'web', 'ui-selected': form.appType === 'web' }"
            @click="setAppType('web')"
          >
            {{ t.apps.webApp }}
          </button>
          <button
            class="type-btn"
            :class="{ active: form.appType === 'mobile', 'ui-selected': form.appType === 'mobile' }"
            @click="setAppType('mobile')"
          >
            {{ t.apps.mobileApp }}
          </button>
        </div>

        <label class="label">{{ t.apps.appName }}</label>
        <input v-model.trim="form.name" class="input" :placeholder="t.apps.appNamePlaceholder" @input="handleNameInput" />

        <label class="label">ID</label>
        <input
          v-model="form.pluginId"
          class="input"
          placeholder="com.gmail.username.uid.hello-world"
          @input="handleIdInput"
        />
        <p class="hint">最终 ID：{{ fullId }}</p>
        <p v-if="idError" class="error">{{ idError }}</p>

        <label class="label">{{ t.apps.appDescription }}</label>
        <textarea v-model.trim="form.description" class="textarea" :placeholder="t.apps.appDescriptionPlaceholder"></textarea>

        <div class="template-meta">
          <span>{{ t.apps.template }}: {{ currentTemplate.templateName }}</span>
          <span v-if="templateInfo?.version">v{{ templateInfo.version }}</span>
          <span v-else>{{ t.common.loading }}</span>
        </div>
        <div class="template-extra">
          <span>{{ t.apps.templateStack }}: {{ currentTemplate.stack }}</span>
          <span>{{ t.apps[currentTemplate.descriptionKey] }}</span>
        </div>
      </div>

      <div class="footer">
        <button class="btn-secondary ui-btn ui-btn--neutral" @click="$emit('close')">{{ t.common.cancel }}</button>
        <button class="btn-primary ui-btn ui-btn--emphasis" :disabled="disabledConfirm" @click="handleConfirm">
          {{ creating ? t.apps.creating : t.common.confirm }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from '@/composables/useI18n'
import { getAppTemplateCatalog, type CreateAppType } from '@/config/appTemplates'
import type { TemplateCacheInfo } from '@/features/plugin/store'

interface UserLike {
  id: string
  email: string
}

const props = defineProps<{
  visible: boolean
  creating: boolean
  templateInfo?: TemplateCacheInfo | null
  user?: UserLike | null
}>()

const emit = defineEmits<{
  close: []
  confirm: [payload: { appType: CreateAppType; name: string; pluginId: string; description: string }]
  appTypeChange: [appType: CreateAppType]
}>()

const { t } = useI18n()

const form = reactive({
  appType: 'desktop' as CreateAppType,
  name: '',
  pluginId: '',
  description: ''
})
const manualIdEdited = ref(false)
const currentTemplate = computed(() => getAppTemplateCatalog(form.appType))

const toSlug = (value: string) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[._-]+|[._-]+$/g, '')

const buildOwnerPrefix = (user?: UserLike | null): string => {
  if (!user?.email) return 'com.local.user.uid'
  const email = user.email.toLowerCase()
  const [localRaw, domainRaw] = email.includes('@') ? email.split('@') : [email, 'local']
  const local = toSlug(localRaw) || 'user'
  const domainParts = domainRaw
    .split('.')
    .map((part) => toSlug(part))
    .filter(Boolean)
    .reverse()
  const uid = toSlug(user.id).slice(0, 12) || 'uid'
  return ['com', ...domainParts, local, uid].join('.')
}

const fullId = computed(() => {
  const ownerPrefix = buildOwnerPrefix(props.user)
  const rawInput = String(form.pluginId || '').toLowerCase()
  const nameSlug = toSlug(form.name)
  const effectiveInput = rawInput || nameSlug
  if (!effectiveInput) return ownerPrefix

  if (effectiveInput.startsWith('com.') && effectiveInput.includes('.')) {
    return effectiveInput.replace(/[^a-z0-9._-]+/g, '-').replace(/-+/g, '-').replace(/^[._-]+|[._-]+$/g, '')
  }
  const slug = toSlug(effectiveInput)
  return slug ? `${ownerPrefix}.${slug}` : ownerPrefix
})

const idError = computed(() => {
  const value = fullId.value
  if (!value) return 'ID 不能为空'
  if (!/^[a-z][a-z0-9._-]{2,127}$/.test(value)) {
    return 'ID 仅支持小写字母/数字/.-_，且长度需在 3-128 之间'
  }
  return ''
})

const disabledConfirm = computed(() => {
  return props.creating || !form.name || !!idError.value
})

const setAppType = (appType: CreateAppType) => {
  if (form.appType === appType) return
  form.appType = appType
  emit('appTypeChange', appType)
}

const handleNameInput = () => {
  if (!manualIdEdited.value) {
    form.pluginId = toSlug(form.name)
  }
}

const handleIdInput = () => {
  manualIdEdited.value = true
  form.pluginId = String(form.pluginId || '')
    .toLowerCase()
    .replace(/\s+/g, '-')
}

const handleConfirm = () => {
  emit('confirm', {
    appType: form.appType,
    name: form.name,
    pluginId: fullId.value,
    description: form.description
  })
}

watch(
  () => props.visible,
  (show) => {
    if (!show) return
    form.appType = 'desktop'
    form.name = ''
    form.pluginId = ''
    form.description = ''
    manualIdEdited.value = false
    emit('appTypeChange', form.appType)
  }
)
</script>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 1200; }
.modal-panel { width: 560px; max-width: calc(100vw - 2rem); background: var(--color-surface-1); border: 1px solid var(--color-border); border-radius: 12px; }
.header { display: flex; align-items: center; justify-content: space-between; padding: 1rem 1.25rem; border-bottom: 1px solid var(--color-border); }
.icon-btn { border: none; background: transparent; color: var(--color-text-secondary); font-size: 1.25rem; cursor: pointer; }
.body { padding: 1rem 1.25rem; display: flex; flex-direction: column; gap: .5rem; }
.label { font-size: .85rem; color: var(--color-text-secondary); margin-top: .25rem; }
.type-row { display: flex; gap: .5rem; margin-bottom: .25rem; }
.type-btn { flex: 1; border: 1px solid var(--color-button-neutral-border); background: var(--color-button-neutral-bg); color: var(--color-button-neutral-fg); border-radius: 8px; padding: .6rem .75rem; cursor: pointer; }
.type-btn.active { border-color: var(--color-interactive-selected-border); }
.type-btn:disabled { opacity: .6; cursor: not-allowed; }
.input,.textarea { width: 100%; border: 1px solid var(--color-border); background: var(--color-surface-2); color: var(--color-text); border-radius: 8px; padding: .65rem .75rem; }
.textarea { min-height: 88px; resize: vertical; }
.template-meta { margin-top: .5rem; display: flex; justify-content: space-between; font-size: .8rem; color: var(--color-text-secondary); }
.template-extra { display: flex; justify-content: space-between; gap: 1rem; font-size: .78rem; color: var(--color-text-secondary); }
.hint { color: var(--color-text-secondary); font-size: .8rem; margin-top: 0.1rem; }
.error { color: #ef4444; font-size: .8rem; }
.footer { display: flex; justify-content: flex-end; gap: .5rem; padding: .9rem 1.25rem 1.1rem; border-top: 1px solid var(--color-border); }
.btn-primary,.btn-secondary { padding: .55rem 1rem; }
</style>
