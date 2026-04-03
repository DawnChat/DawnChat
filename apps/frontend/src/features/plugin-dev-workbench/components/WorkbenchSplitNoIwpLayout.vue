<template>
  <WorkbenchCenterPane
    :workbench-mode="workbenchMode"
    :allow-requirements-mode="allowRequirementsMode"
    :center-pane-mode="centerPaneMode"
    :plugin-id="pluginId"
    :chat-input="chatInput"
    :preview-chat-blocked="previewChatBlocked"
    :iwp-root="iwpRoot"
    :active-file-path="activeFilePath"
    :markdown-content="markdownContent"
    :file-loading="fileLoading"
    :file-saving="fileSaving"
    :can-build="canBuild"
    :is-dirty="isDirty"
    :has-active-file="hasActiveFile"
    :build-state="buildState"
    :save-label="saveLabel"
    :saving-label="savingLabel"
    :build-button-label="buildButtonLabel"
    :editor-loading-label="editorLoadingLabel"
    :editor-placeholder="editorPlaceholder"
    :empty-path-label="emptyPathLabel"
    :saved-label="savedLabel"
    :unsaved-label="unsavedLabel"
    :build-session-label="buildSessionLabel"
    :open-build-session-label="openBuildSessionLabel"
    :readonly-title="readonlyTitle"
    :readonly-file-path="readonlyFilePath"
    :readonly-file-line="readonlyFileLine"
    :readonly-file-content="readonlyFileContent"
    :readonly-loading="readonlyLoading"
    :readonly-error="readonlyError"
    :back-to-markdown-label="backToMarkdownLabel"
    :readonly-loading-label="readonlyLoadingLabel"
    :readonly-empty-content-label="readonlyEmptyContentLabel"
    :agent-log-title="agentLogTitle"
    :agent-log-empty-label="agentLogEmptyLabel"
    :agent-log-running-label="agentLogRunningLabel"
    :agent-log-idle-label="agentLogIdleLabel"
    :agent-log-height="agentLogHeight"
    :is-resizing-agent-log="isResizingAgentLog"
    :tts-enabled="ttsEnabled"
    :tts-playback-state="ttsPlaybackState"
    :tts-stream-status="ttsStreamStatus"
    :selected-tts-engine="selectedTtsEngine"
    :tts-engine-options="ttsEngineOptions"
    :enable-file-attachments="enableFileAttachments"
    @update-chat-input="(value) => emit('updateChatInput', value)"
    @composer-selection-change="(payload) => emit('composerSelectionChange', payload)"
    @update-markdown="(value) => emit('updateMarkdown', value)"
    @save-markdown="emit('saveMarkdown')"
    @trigger-build="emit('triggerBuild')"
    @open-build-session="emit('openBuildSession')"
    @back-to-markdown="emit('backToMarkdown')"
    @start-resize-agent-log="(event) => emit('startResizeAgentLog', event)"
    @toggle-tts-enabled="emit('toggleTtsEnabled')"
    @stop-tts="emit('stopTts')"
    @select-tts-engine="(value) => emit('selectTtsEngine', value)"
    @open-azure-tts-settings="emit('openAzureTtsSettings')"
  />
  <div
    class="column-resizer"
    :class="{ active: isResizingPreview }"
    @pointerdown="(event) => emit('startResizePreview', event)"
  >
    <span class="column-resizer-line"></span>
  </div>
</template>

<script setup lang="ts">
import type { TtsPlaybackState } from '@/services/tts/ttsPlaybackQueue'
import WorkbenchCenterPane from '@/features/plugin-dev-workbench/components/WorkbenchCenterPane.vue'

defineProps<{
  workbenchMode: 'requirements' | 'agent'
  allowRequirementsMode: boolean
  centerPaneMode: 'markdown' | 'readonly'
  pluginId: string
  chatInput: string
  previewChatBlocked: boolean
  iwpRoot: string
  activeFilePath: string
  markdownContent: string
  fileLoading: boolean
  fileSaving: boolean
  canBuild: boolean
  isDirty: boolean
  hasActiveFile: boolean
  buildState: {
    status: 'idle' | 'running' | 'success' | 'failed'
    sessionId: string
    message: string
    error: string
  }
  saveLabel: string
  savingLabel: string
  buildButtonLabel: string
  editorLoadingLabel: string
  editorPlaceholder: string
  emptyPathLabel: string
  savedLabel: string
  unsavedLabel: string
  buildSessionLabel: string
  openBuildSessionLabel: string
  readonlyTitle: string
  readonlyFilePath: string
  readonlyFileLine: number
  readonlyFileContent: string
  readonlyLoading: boolean
  readonlyError: string
  backToMarkdownLabel: string
  readonlyLoadingLabel: string
  readonlyEmptyContentLabel: string
  agentLogTitle: string
  agentLogEmptyLabel: string
  agentLogRunningLabel: string
  agentLogIdleLabel: string
  agentLogHeight: number
  isResizingPreview: boolean
  isResizingAgentLog: boolean
  ttsEnabled: boolean
  ttsPlaybackState: TtsPlaybackState
  ttsStreamStatus: 'idle' | 'connecting' | 'reconnecting' | 'streaming' | 'closed'
  selectedTtsEngine: string
  ttsEngineOptions: Array<{ id: string; label: string }>
  enableFileAttachments: boolean
}>()

const emit = defineEmits<{
  updateChatInput: [value: string]
  composerSelectionChange: [payload: { start: number; end: number; focused: boolean }]
  updateMarkdown: [value: string]
  saveMarkdown: []
  triggerBuild: []
  openBuildSession: []
  backToMarkdown: []
  startResizePreview: [event: PointerEvent]
  startResizeAgentLog: [event: PointerEvent]
  toggleTtsEnabled: []
  stopTts: []
  selectTtsEngine: [value: string]
  openAzureTtsSettings: []
}>()
</script>

<style scoped>
.column-resizer {
  min-height: 0;
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--wb-pane-side);
}

.column-resizer-line {
  width: 2px;
  height: 64px;
  border-radius: 999px;
  background: var(--wb-border-subtle);
}

.column-resizer:hover .column-resizer-line,
.column-resizer.active .column-resizer-line {
  background: var(--color-primary);
}
</style>
