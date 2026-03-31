<template>
  <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
    <div class="modal-panel">
      <div class="header">
        <div>
          <h3>{{ labels.title }}</h3>
          <p class="subtitle">{{ labels.subtitle }}</p>
        </div>
        <button class="icon-btn" @click="$emit('close')">×</button>
      </div>

      <div class="body">
        <div v-if="progressSummary" class="progress-card">
          <div class="progress-header">
            <span>{{ labels.progressStage }}: {{ progressSummary.stageLabel }}</span>
            <span>{{ progressSummary.progress }}%</span>
          </div>
          <div class="progress-bar-track">
            <div class="progress-bar-fill" :style="{ width: `${progressSummary.progress}%` }"></div>
          </div>
          <div class="progress-message">{{ progressSummary.message }}</div>
        </div>

        <div class="version-summary">
          <span>{{ labels.localVersion }}: {{ localVersionText }}</span>
          <span>{{ labels.remoteLatestVersion }}: {{ remoteVersionText }}</span>
        </div>

        <label class="label">{{ labels.slug }}</label>
        <input v-model.trim="form.slug" class="input" placeholder="my-awesome-site" />

        <label class="label">{{ labels.siteTitle }}</label>
        <input v-model.trim="form.title" class="input" :placeholder="pluginName" />

        <label class="label">{{ labels.visibility }}</label>
        <PluginDevInlineSelect
          :model-value="form.initialVisibility"
          :options="visibilityOptions"
          :label="labels.visibility"
          class="inline-select-input"
          :disabled="visibilityLocked"
          @update:model-value="(value) => { form.initialVisibility = value as 'private' | 'public' | 'unlisted' }"
        />
        <div class="hint">{{ visibilityHint }}</div>

        <label class="label">{{ labels.version }}</label>
        <input v-model.trim="form.version" class="input" :placeholder="localVersionText" />
        <div v-if="versionHint" :class="versionHintClass">{{ versionHint }}</div>

        <label class="label">{{ labels.description }}</label>
        <textarea v-model.trim="form.description" class="textarea" :placeholder="labels.descriptionPlaceholder"></textarea>

        <div v-if="statusSummary" class="status-card">
          <span>{{ labels.currentStatus }}: {{ statusSummary.status }}</span>
          <span>{{ labels.remoteLatestVersion }}: {{ statusSummary.version }}</span>
          <span v-if="statusSummary.url">
            {{ labels.currentUrl }}:
            <a :href="statusSummary.url" target="_blank" rel="noreferrer">{{ statusSummary.url }}</a>
          </span>
        </div>

        <div v-if="successSummary" class="success-card">
          <div class="success-title">{{ labels.successInlineTitle }}</div>
          <div>{{ labels.successVersion }}: {{ successSummary.version }}</div>
          <div v-if="successSummary.url">
            {{ labels.currentUrl }}:
            <a :href="successSummary.url" target="_blank" rel="noreferrer">{{ successSummary.url }}</a>
          </div>
        </div>

        <div v-if="displayError" class="error">{{ displayError }}</div>
      </div>

      <div class="footer">
        <button class="btn-secondary ui-btn ui-btn--neutral" @click="$emit('close')">{{ labels.cancel }}</button>
        <button class="btn-primary ui-btn ui-btn--emphasis" :disabled="disabledConfirm" @click="submit">
          {{ loading ? labels.publishing : labels.confirm }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useI18n } from '@/composables/useI18n'
import type { WebPublishResult, WebPublishStatusResult, WebPublishTask } from '@/services/plugins/webPublishApi'
import PluginDevInlineSelect from '@/features/coding-agent/components/plugin-dev-chat/PluginDevInlineSelect.vue'
import type { PluginDevInlineSelectOption } from '@/features/coding-agent/components/plugin-dev-chat/PluginDevInlineSelect.vue'

const props = defineProps<{
  visible: boolean
  pluginName: string
  pluginVersion: string
  pluginDescription: string
  loading: boolean
  error?: string | null
  status?: WebPublishStatusResult | null
  task?: WebPublishTask | null
  result?: WebPublishResult | null
}>()

const emit = defineEmits<{
  close: []
  submit: [payload: { slug: string; title: string; version: string; description: string; initial_visibility: 'private' | 'public' | 'unlisted' }]
}>()

const { t } = useI18n()

const appsLabels = computed(() => t.value.apps as Record<string, string>)

const labels = computed(() => ({
  title: appsLabels.value.publishDialogTitle,
  subtitle: appsLabels.value.publishDialogSubtitle,
  slug: appsLabels.value.publishSlug,
  siteTitle: appsLabels.value.publishSiteTitle,
  visibility: appsLabels.value.publishVisibility,
  visibilityPrivate: appsLabels.value.publishVisibilityPrivate,
  visibilityPublic: appsLabels.value.publishVisibilityPublic,
  visibilityUnlisted: appsLabels.value.publishVisibilityUnlisted,
  visibilityLocked: appsLabels.value.publishVisibilityLocked,
  visibilityEditable: appsLabels.value.publishVisibilityEditable,
  version: appsLabels.value.publishVersion,
  description: appsLabels.value.publishDescription,
  descriptionPlaceholder: appsLabels.value.publishDescriptionPlaceholder,
  currentStatus: appsLabels.value.publishCurrentStatus,
  currentUrl: appsLabels.value.publishCurrentUrl,
  cancel: t.value.common.cancel,
  confirm: appsLabels.value.publishStart,
  publishing: appsLabels.value.publishingWeb,
  localVersion: appsLabels.value.publishLocalVersion,
  remoteLatestVersion: appsLabels.value.publishRemoteLatestVersion,
  progressStage: appsLabels.value.publishProgressStage,
  versionInvalid: appsLabels.value.publishVersionInvalid,
  versionRequired: appsLabels.value.publishVersionRequired,
  versionReady: appsLabels.value.publishVersionReady,
  successInlineTitle: appsLabels.value.publishSuccessInlineTitle,
  successVersion: appsLabels.value.publishSuccessVersion,
  stageQueued: appsLabels.value.publishStageQueued,
  stageValidating: appsLabels.value.publishStageValidating,
  stageSyncingVersion: appsLabels.value.publishStageSyncingVersion,
  stageBuilding: appsLabels.value.publishStageBuilding,
  stagePreparingUpload: appsLabels.value.publishStagePreparingUpload,
  stageUploading: appsLabels.value.publishStageUploading,
  stageFinalizing: appsLabels.value.publishStageFinalizing,
  stageCompleted: appsLabels.value.publishStageCompleted,
  stageFailed: appsLabels.value.publishStageFailed,
}))

const toSlug = (value: string) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)

const parseSemver = (value: string): [number, number, number] | null => {
  const match = String(value || '').trim().match(/^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$/)
  if (!match) return null
  return [Number(match[1]), Number(match[2]), Number(match[3])]
}

const compareSemver = (left: string, right: string): number | null => {
  const leftValue = parseSemver(left)
  const rightValue = parseSemver(right)
  if (!leftValue || !rightValue) return null
  for (let index = 0; index < 3; index += 1) {
    if (leftValue[index] !== rightValue[index]) {
      return leftValue[index] > rightValue[index] ? 1 : -1
    }
  }
  return 0
}

const form = reactive({
  slug: '',
  title: '',
  initialVisibility: 'private' as 'private' | 'public' | 'unlisted',
  version: '',
  description: '',
})

const visibilityOptions = computed<PluginDevInlineSelectOption[]>(() => [
  { value: 'private', label: labels.value.visibilityPrivate },
  { value: 'public', label: labels.value.visibilityPublic },
  { value: 'unlisted', label: labels.value.visibilityUnlisted },
])

const localVersionText = computed(() => String(props.status?.local_version || props.pluginVersion || '').trim() || '0.1.0')
const remoteVersionText = computed(() => String(props.status?.remote_latest_version || '').trim() || t.value.common.noData)

const resetForm = () => {
  form.slug = toSlug(props.pluginName)
  form.title = props.pluginName
  form.initialVisibility = (props.status?.visibility || 'private') as 'private' | 'public' | 'unlisted'
  form.version = localVersionText.value
  form.description = props.pluginDescription || ''
}

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      resetForm()
      if (props.status?.current_slug) {
        form.slug = String(props.status.current_slug)
      }
    }
  },
  { immediate: true },
)

const versionValidation = computed(() => {
  const version = String(form.version || '').trim()
  if (!version) {
    return { valid: false, message: labels.value.versionRequired }
  }
  if (!parseSemver(version)) {
    return { valid: false, message: labels.value.versionInvalid }
  }
  const remoteVersion = String(props.status?.remote_latest_version || '').trim()
  if (!remoteVersion) {
    return { valid: true, message: labels.value.versionReady }
  }
  const comparison = compareSemver(version, remoteVersion)
  if (comparison === null) {
    return { valid: false, message: labels.value.versionInvalid }
  }
  if (comparison <= 0) {
    return {
      valid: false,
      message: appsLabels.value.publishVersionMustBeGreater.replace('{version}', remoteVersion),
    }
  }
  return {
    valid: true,
    message: appsLabels.value.publishVersionReadyWithRemote.replace('{version}', remoteVersion),
  }
})

const versionHint = computed(() => versionValidation.value.message)
const versionHintClass = computed(() => (versionValidation.value.valid ? 'hint success' : 'hint error-text'))
const visibilityLocked = computed(() => Boolean(props.status?.current_slug))
const visibilityHint = computed(() => (visibilityLocked.value ? labels.value.visibilityLocked : labels.value.visibilityEditable))

const disabledConfirm = computed(() => {
  return !form.slug || !form.title || !form.version || props.loading || !versionValidation.value.valid
})

const statusSummary = computed(() => {
  const status = props.status
  if (!status) return null
  return {
    status: String(status.current_status || 'unknown'),
    version: String(status.remote_latest_version || t.value.common.noData),
    url: String(status.runtime_url || ''),
  }
})

const stageLabelMap = computed(() => ({
  queued: labels.value.stageQueued,
  validating: labels.value.stageValidating,
  syncing_version: labels.value.stageSyncingVersion,
  building: labels.value.stageBuilding,
  preparing_upload: labels.value.stagePreparingUpload,
  uploading: labels.value.stageUploading,
  finalizing: labels.value.stageFinalizing,
  completed: labels.value.stageCompleted,
  failed: labels.value.stageFailed,
}))

const progressSummary = computed(() => {
  const task = props.task
  if (!task || !['pending', 'running'].includes(task.status)) return null
  return {
    progress: Math.max(0, Math.min(100, Number(task.progress || 0))),
    message: String(task.message || ''),
    stageLabel: stageLabelMap.value[task.stage as keyof typeof stageLabelMap.value] || task.stage,
  }
})

const successSummary = computed(() => {
  const result = props.result || props.task?.result
  if (!result) return null
  return {
    version: String(result.release?.version || ''),
    url: String(result.runtime_url || ''),
  }
})

const displayError = computed(() => {
  if (props.task?.status === 'failed') {
    return props.task.error?.message || props.task.message || props.error || ''
  }
  return props.error || ''
})

const submit = () => {
  emit('submit', {
    slug: toSlug(form.slug),
    title: form.title.trim(),
    initial_visibility: form.initialVisibility,
    version: form.version.trim(),
    description: form.description.trim(),
  })
}
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.modal-panel {
  width: min(560px, 100%);
  background: var(--color-surface-1);
  border: 1px solid var(--color-border);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}

.header,
.footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem;
}

.body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0 1.25rem 1.25rem;
}

.subtitle {
  margin-top: 0.25rem;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
}

.label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.input,
.textarea {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-surface-2);
  color: var(--color-text);
  padding: 0.75rem 0.9rem;
}

.inline-select-input {
  width: 100%;
}

.textarea {
  min-height: 88px;
  resize: vertical;
}

.version-summary,
.status-card,
.success-card,
.progress-card {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  padding: 0.85rem 0.95rem;
  border-radius: 10px;
  background: var(--color-surface-2);
  color: var(--color-text-secondary);
  font-size: 0.85rem;
}

.progress-card {
  background: rgba(59, 130, 246, 0.08);
  color: var(--color-text);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  font-weight: 600;
}

.progress-bar-track {
  height: 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.22);
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: 999px;
  transition: width 0.2s ease;
}

.progress-message {
  color: var(--color-text-secondary);
}

.success-card {
  background: rgba(16, 185, 129, 0.08);
}

.success-title {
  font-weight: 600;
  color: var(--color-text);
}

.hint {
  font-size: 0.83rem;
}

.success {
  color: #059669;
}

.error-text,
.error {
  color: #ef4444;
}

.status-card a,
.success-card a {
  color: var(--color-primary);
}

.error {
  font-size: 0.85rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.btn-primary,
.btn-secondary,
.icon-btn {
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 0.65rem 0.95rem;
  cursor: pointer;
}

.btn-primary {
  background: var(--color-button-emphasis-bg);
  color: var(--color-button-emphasis-fg);
  border-color: var(--color-primary);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary,
.icon-btn {
  background: var(--color-button-neutral-bg);
  color: var(--color-button-neutral-fg);
}

.icon-btn {
  font-size: 1.15rem;
  line-height: 1;
  width: 36px;
  height: 36px;
  padding: 0;
}
</style>
