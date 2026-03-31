<template>
  <div class="iwp-editor-panel">
    <div class="editor-toolbar">
      <div class="editor-meta">
        <span class="editor-root">{{ iwpRoot }}</span>
        <span class="editor-path">{{ activeFilePath || emptyPathLabel }}</span>
      </div>
      <div class="editor-actions">
        <button class="ui-btn ui-btn--neutral action-btn" :disabled="!hasActiveFile || fileSaving" @click="emit('save')">
          {{ fileSaving ? savingLabel : saveLabel }}
        </button>
        <button class="ui-btn ui-btn--emphasis action-btn" :disabled="!canBuild" @click="emit('build')">
          {{ buildButtonLabel }}
        </button>
      </div>
    </div>
    <div v-if="fileLoading" class="editor-loading">{{ loadingLabel }}</div>
    <textarea
      v-else
      class="editor-area"
      :value="content"
      :placeholder="editorPlaceholder"
      @input="handleInput"
    />
    <div class="editor-footer">
      <span class="dirty-indicator" :class="{ dirty: isDirty }">{{ isDirty ? unsavedLabel : savedLabel }}</span>
      <span v-if="buildState.message" class="build-message" :class="buildState.status">{{ buildState.message }}</span>
      <span v-if="buildState.sessionId" class="build-session">
        {{ buildSessionLabel.replace('{id}', buildState.sessionId) }}
      </span>
      <button
        v-if="buildState.sessionId"
        class="session-link ui-btn ui-btn--neutral"
        type="button"
        @click="emit('openBuildSession')"
      >
        {{ openSessionLabel }}
      </button>
      <span v-if="buildState.error" class="build-error">{{ buildState.error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  iwpRoot: string
  activeFilePath: string
  hasActiveFile: boolean
  content: string
  fileLoading: boolean
  fileSaving: boolean
  canBuild: boolean
  isDirty: boolean
  buildState: {
    status: 'idle' | 'running' | 'success' | 'failed'
    sessionId: string
    message: string
    error: string
  }
  saveLabel: string
  savingLabel: string
  buildButtonLabel: string
  loadingLabel: string
  editorPlaceholder: string
  emptyPathLabel: string
  savedLabel: string
  unsavedLabel: string
  buildSessionLabel: string
  openSessionLabel: string
}>()

const emit = defineEmits<{
  save: []
  build: []
  updateContent: [value: string]
  openBuildSession: []
}>()

const handleInput = (event: Event) => {
  const target = event.target as HTMLTextAreaElement
  emit('updateContent', target.value)
}
</script>

<style scoped>
.iwp-editor-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--wb-pane-main);
}

.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.65rem 0.85rem;
  border-bottom: 1px solid var(--wb-border-subtle);
  background: var(--wb-pane-side);
  box-shadow: var(--wb-inset-shadow);
}

.editor-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.editor-root {
  font-size: 0.76rem;
  color: var(--color-text-secondary);
}

.editor-path {
  font-size: 0.82rem;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.editor-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.action-btn {
  min-height: 32px;
  border-radius: 8px;
  padding: 0.42rem 0.75rem;
}

.editor-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
}

.editor-area {
  flex: 1;
  min-height: 0;
  resize: none;
  border: none;
  outline: none;
  background: var(--wb-pane-main);
  color: var(--color-text);
  padding: 0.9rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.86rem;
  line-height: 1.55;
}

.editor-footer {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0 0.85rem;
  border-top: 1px solid var(--wb-border-subtle);
  background: var(--wb-pane-side);
  color: var(--color-text-secondary);
  font-size: 0.75rem;
}

.dirty-indicator.dirty {
  color: var(--color-warning);
}

.build-message.running {
  color: var(--color-primary);
}

.build-message.success {
  color: var(--color-success);
}

.build-message.failed,
.build-error {
  color: var(--color-error);
}

.build-session {
  color: var(--color-text-secondary);
}

.session-link {
  min-height: 24px;
  border-radius: 7px;
  padding: 0 0.45rem;
  font-size: 0.72rem;
}
</style>
