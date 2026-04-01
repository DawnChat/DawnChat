<template>
  <section class="center-pane">
    <div v-if="allowRequirementsMode && workbenchMode === 'requirements'" class="requirements-pane">
      <div class="requirements-main">
        <IwpMarkdownEditorPanel
          v-if="centerPaneMode === 'markdown'"
          :iwp-root="iwpRoot"
          :active-file-path="activeFilePath"
          :has-active-file="hasActiveFile"
          :content="markdownContent"
          :file-loading="fileLoading"
          :file-saving="fileSaving"
          :can-build="canBuild"
          :is-dirty="isDirty"
          :build-state="buildState"
          :save-label="saveLabel"
          :saving-label="savingLabel"
          :build-button-label="buildButtonLabel"
          :loading-label="editorLoadingLabel"
          :editor-placeholder="editorPlaceholder"
          :empty-path-label="emptyPathLabel"
          :saved-label="savedLabel"
          :unsaved-label="unsavedLabel"
          :build-session-label="buildSessionLabel"
          :open-session-label="openBuildSessionLabel"
          @save="emit('saveMarkdown')"
          @build="emit('triggerBuild')"
          @update-content="(value) => emit('updateMarkdown', value)"
          @open-build-session="emit('openBuildSession')"
        />
        <ReadonlyCodeViewerPanel
          v-else
          :title="readonlyTitle"
          :file-path="readonlyFilePath"
          :focus-line="readonlyFileLine"
          :loading="readonlyLoading"
          :error="readonlyError"
          :content="readonlyFileContent"
          :back-label="backToMarkdownLabel"
          :loading-label="readonlyLoadingLabel"
          :empty-path-label="emptyPathLabel"
          :empty-content-label="readonlyEmptyContentLabel"
          @back="emit('backToMarkdown')"
        />
      </div>
      <div class="row-resizer" :class="{ active: isResizingAgentLog }" @pointerdown="emit('startResizeAgentLog', $event)">
        <span class="row-resizer-line"></span>
      </div>
      <div class="requirements-log" :style="{ height: `${agentLogHeight}px` }">
        <PluginDevChatPanel
          :key="'requirements-log-chat'"
          :model-value="chatInput"
          :plugin-id="pluginId"
          :externally-blocked="previewChatBlocked"
          :panel-title="agentLogTitle"
          :show-panel-header="false"
          :show-session-tabs="false"
          :show-engine-selector="false"
          :show-agent-selector="false"
          :show-model-selector="false"
          :show-composer="false"
          :show-tts-control="true"
          :tts-enabled="ttsEnabled"
          :tts-playback-state="ttsPlaybackState"
          :tts-stream-status="ttsStreamStatus"
          @update:model-value="(value) => emit('updateChatInput', value)"
          @composer-selection-change="(payload) => emit('composerSelectionChange', payload)"
          @toggle-tts-enabled="emit('toggleTtsEnabled')"
          @stop-tts="emit('stopTts')"
        />
      </div>
    </div>
    <PluginDevChatPanel
      :key="'agent-full-chat'"
      v-else
      :model-value="chatInput"
      :plugin-id="pluginId"
      :externally-blocked="previewChatBlocked"
      :panel-title="''"
      :show-panel-header="false"
      :show-session-tabs="true"
      :show-engine-selector="false"
      :show-agent-selector="false"
      :show-model-selector="true"
      :show-composer="true"
      :show-tts-control="true"
      :tts-enabled="ttsEnabled"
      :tts-playback-state="ttsPlaybackState"
      :tts-stream-status="ttsStreamStatus"
      :selected-tts-engine="selectedTtsEngine"
      :tts-engine-options="ttsEngineOptions"
      @update:model-value="(value) => emit('updateChatInput', value)"
      @composer-selection-change="(payload) => emit('composerSelectionChange', payload)"
      @toggle-tts-enabled="emit('toggleTtsEnabled')"
      @stop-tts="emit('stopTts')"
      @select-tts-engine="(value) => emit('selectTtsEngine', value)"
      @open-azure-tts-settings="emit('openAzureTtsSettings')"
    />
  </section>
</template>

<script setup lang="ts">
import PluginDevChatPanel from '@/features/plugin/components/PluginDevChatPanel.vue'
import IwpMarkdownEditorPanel from '@/features/plugin-dev-workbench/components/IwpMarkdownEditorPanel.vue'
import ReadonlyCodeViewerPanel from '@/features/plugin-dev-workbench/components/ReadonlyCodeViewerPanel.vue'
import type { TtsPlaybackState } from '@/services/tts/ttsPlaybackQueue'

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
  isResizingAgentLog: boolean
  ttsEnabled: boolean
  ttsPlaybackState: TtsPlaybackState
  ttsStreamStatus: 'idle' | 'connecting' | 'reconnecting' | 'streaming' | 'closed'
  selectedTtsEngine: string
  ttsEngineOptions: Array<{ id: string; label: string }>
}>()

const emit = defineEmits<{
  updateChatInput: [value: string]
  composerSelectionChange: [payload: { start: number; end: number; focused: boolean }]
  updateMarkdown: [value: string]
  saveMarkdown: []
  triggerBuild: []
  openBuildSession: []
  backToMarkdown: []
  startResizeAgentLog: [event: PointerEvent]
  toggleTtsEnabled: []
  stopTts: []
  selectTtsEngine: [value: string]
  openAzureTtsSettings: []
}>()
</script>

<style scoped>
.center-pane {
  min-width: 0;
  min-height: 0;
  border-left: 1px solid var(--wb-border-strong);
  border-right: 1px solid var(--wb-border-strong);
  background: var(--wb-pane-main);
  box-shadow: var(--wb-inset-shadow);
}

.requirements-pane {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--wb-pane-main);
}

.requirements-main {
  flex: 1;
  min-height: 0;
}

.requirements-log {
  min-height: 120px;
  border-top: 1px solid var(--wb-border-subtle);
  overflow: hidden;
}

.row-resizer {
  height: 8px;
  cursor: row-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--wb-pane-main);
}

.row-resizer-line {
  width: 52px;
  height: 2px;
  border-radius: 999px;
  background: var(--wb-border-subtle);
}

.row-resizer:hover .row-resizer-line,
.row-resizer.active .row-resizer-line {
  background: var(--color-primary);
}
</style>
