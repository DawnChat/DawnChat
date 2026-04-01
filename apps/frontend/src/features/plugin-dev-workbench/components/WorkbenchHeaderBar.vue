<template>
  <div class="workbench-header">
    <div class="workbench-left">
      <div class="workbench-meta">
        <template v-if="!isEditingName">
          <span class="workbench-title">{{ activeAppName || pluginId }}</span>
          <button
            class="edit-name-btn ui-btn ui-btn--neutral"
            type="button"
            :title="editNameLabel"
            :aria-label="editNameLabel"
            :disabled="renaming"
            @click="startNameEditing"
          >
            <Pencil :size="14" />
          </button>
        </template>
        <div v-else class="name-editor">
          <input
            ref="nameInputRef"
            v-model="editingName"
            class="name-editor-input"
            type="text"
            :placeholder="nameInputPlaceholder"
            :disabled="renaming"
            @keydown="handleNameInputKeydown"
          >
          <button
            class="name-editor-btn ui-btn ui-btn--neutral"
            type="button"
            :title="saveNameLabel"
            :aria-label="saveNameLabel"
            :disabled="renaming"
            @click="submitNameEdit"
          >
            <Check :size="14" />
          </button>
          <button
            class="name-editor-btn ui-btn ui-btn--neutral"
            type="button"
            :title="cancelNameLabel"
            :aria-label="cancelNameLabel"
            :disabled="renaming"
            @click="cancelNameEditing"
          >
            <X :size="14" />
          </button>
        </div>
        <span v-if="appTypeLabel" class="workbench-badge">{{ appTypeLabel }}</span>
      </div>
      <div v-if="showModeSwitch" class="mode-switch">
        <button
          class="mode-btn"
          :class="{ active: workbenchMode === 'requirements' }"
          @click="emit('switchMode', 'requirements')"
        >
          {{ requirementsModeLabel }}
        </button>
        <button class="mode-btn" :class="{ active: workbenchMode === 'agent' }" @click="emit('switchMode', 'agent')">
          {{ agentModeLabel }}
        </button>
      </div>
    </div>
    <div class="workbench-actions">
      <span v-if="isBuildRunning" class="build-status">{{ buildRunningLabel }}</span>
      <button
        v-if="hasBuildSession"
        class="secondary-btn ui-btn ui-btn--neutral"
        @click="emit('openBuildSession')"
      >
        {{ openBuildSessionLabel }}
      </button>
      <button
        v-if="isMobileApp"
        class="secondary-btn ui-btn ui-btn--neutral"
        @click="emit('openMobileOffline')"
      >
        {{ mobileOfflineUploadLabel }}
      </button>
      <button v-if="isMobileApp" class="publish-btn ui-btn ui-btn--emphasis" @click="emit('openMobileQr')">
        {{ mobilePreviewQrLabel }}
      </button>
      <button v-if="isWebApp" class="publish-btn ui-btn ui-btn--emphasis" @click="emit('openWebPublish')">
        {{ publishWebLabel }}
      </button>
      <button class="secondary-btn ui-btn ui-btn--danger close-btn" @click="emit('close')">
        {{ closeLabel }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { Check, Pencil, X } from 'lucide-vue-next'

const props = defineProps<{
  activeAppName: string
  pluginId: string
  appTypeLabel: string
  isWebApp: boolean
  isMobileApp: boolean
  showModeSwitch: boolean
  workbenchMode: 'requirements' | 'agent'
  requirementsModeLabel: string
  agentModeLabel: string
  buildRunningLabel: string
  openBuildSessionLabel: string
  isBuildRunning: boolean
  hasBuildSession: boolean
  publishWebLabel: string
  mobilePreviewQrLabel: string
  mobileOfflineUploadLabel: string
  closeLabel: string
  editNameLabel: string
  saveNameLabel: string
  cancelNameLabel: string
  nameInputPlaceholder: string
  renaming: boolean
}>()

const emit = defineEmits<{
  openWebPublish: []
  openMobileQr: []
  openMobileOffline: []
  switchMode: [mode: 'requirements' | 'agent']
  openBuildSession: []
  close: []
  renameApp: [name: string]
}>()

const isEditingName = ref(false)
const editingName = ref('')
const nameInputRef = ref<HTMLInputElement | null>(null)

const startNameEditing = async () => {
  editingName.value = String(props.activeAppName || props.pluginId || '').trim()
  isEditingName.value = true
  await nextTick()
  nameInputRef.value?.focus()
  nameInputRef.value?.select()
}

const cancelNameEditing = () => {
  isEditingName.value = false
  editingName.value = ''
}

const submitNameEdit = () => {
  const normalized = String(editingName.value || '').trim()
  if (!normalized) return
  emit('renameApp', normalized)
  isEditingName.value = false
}

const handleNameInputKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter') {
    event.preventDefault()
    submitNameEdit()
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    cancelNameEditing()
  }
}

watch(
  () => props.activeAppName,
  (next) => {
    if (isEditingName.value) return
    editingName.value = String(next || '')
  },
  { immediate: true }
)
</script>

<style scoped>
.workbench-header {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.72rem;
  min-height: 46px;
  padding: 0.48rem 0.8rem;
  border-bottom: 1px solid var(--wb-border-strong);
  background: var(--wb-pane-side);
  box-shadow: var(--wb-inset-shadow);
}

.workbench-left {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 0.62rem;
}

.workbench-meta {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  min-width: 0;
}

.workbench-title {
  font-weight: 600;
  font-size: 0.88rem;
  line-height: 1.2;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.edit-name-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  min-height: 1.5rem;
  border-radius: 6px;
  padding: 0;
}

.name-editor {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-width: min(380px, 48vw);
}

.name-editor-input {
  min-width: 140px;
  width: min(300px, 42vw);
  height: 1.7rem;
  border: 1px solid var(--wb-border-subtle);
  border-radius: 6px;
  background: var(--wb-pane-main);
  color: var(--color-text);
  font-size: 0.78rem;
  line-height: 1.2;
  padding: 0 0.45rem;
}

.name-editor-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  min-height: 1.5rem;
  border-radius: 6px;
  padding: 0;
}

.workbench-badge {
  border: 1px solid var(--color-primary);
  color: var(--color-primary);
  border-radius: 999px;
  padding: 0.12rem 0.45rem;
  font-size: 0.68rem;
  line-height: 1.1;
  white-space: nowrap;
}

.mode-switch {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--wb-border-subtle);
  border-radius: 8px;
  padding: 2px;
  background: var(--wb-pane-chrome);
}

.mode-btn {
  min-height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.78rem;
  line-height: 1;
  padding: 0 0.6rem;
  cursor: pointer;
}

.mode-btn.active {
  color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
}

.workbench-actions {
  display: flex;
  align-items: center;
  gap: 0.38rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.publish-btn {
  border-radius: 8px;
  padding: 0.35rem 0.72rem;
  min-height: 28px;
  font-size: 0.76rem;
  line-height: 1.1;
  font-weight: 600;
}

.secondary-btn {
  border-radius: 8px;
  padding: 0.35rem 0.72rem;
  min-height: 28px;
  font-size: 0.76rem;
  line-height: 1.1;
  font-weight: 600;
}

.close-btn {
  margin-left: 0.18rem;
}

.build-status {
  font-size: 0.7rem;
  line-height: 1.1;
  color: var(--color-primary);
  white-space: nowrap;
}
</style>
