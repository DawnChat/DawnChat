<template>
  <div
    class="plugin-dev-workbench"
    :class="{
      'agent-preview-layout': workbenchLayoutVariant === 'agent_preview',
      'split-with-iwp-layout': workbenchLayoutVariant === 'split_with_iwp',
      'split-no-iwp-layout': workbenchLayoutVariant === 'split_no_iwp',
      'assistant-compact-layout': workbenchLayoutVariant === 'compact'
    }"
    :style="isAssistantCompactSurface
      ? undefined
      : {
          '--agent-pane-width': `${previewWidthPx}px`,
          '--preview-pane-width': `${previewWidthPx}px`
        }"
  >
    <WorkbenchHeaderBar
      :active-app-name="activeApp?.name || ''"
      :plugin-id="pluginId"
      :app-type-label="appTypeLabel"
      :is-web-app="isWebApp"
      :is-mobile-app="isMobileApp"
      :show-mode-switch="hasIwpRequirements && !isAssistantCompactSurface"
      :workbench-mode="workbenchMode"
      :requirements-mode-label="t.apps.workbenchRequirementsMode"
      :agent-mode-label="t.apps.workbenchAgentMode"
      :build-running-label="t.apps.iwpBuilding"
      :open-build-session-label="t.apps.iwpOpenBuildSession"
      :is-build-running="isBuildRunning"
      :has-build-session="hasBuildSession"
      :publish-web-label="t.apps.publishWeb"
      :mobile-preview-qr-label="t.apps.mobilePreviewQr"
      :mobile-offline-upload-label="t.apps.mobileOfflineUpload"
      :close-label="t.apps.workbenchClose"
      @switch-mode="setWorkbenchMode"
      @open-build-session="openBuildSession"
      @open-web-publish="openPublishDialog"
      @open-mobile-qr="openMobilePreviewQr"
      @open-mobile-offline="openMobileOfflinePlaceholder"
      @close="handleCloseWorkbench"
    />
    <template v-if="workbenchLayoutVariant !== 'compact'">
      <IwpFileDrawer
        v-if="workbenchLayoutVariant === 'split_with_iwp'"
        :collapsed="fileTreeCollapsed"
        :loading="filesLoading"
        :files="fileList"
        :active-file-path="activeFilePath"
        :title="t.apps.iwpFilesTitle"
        :loading-label="t.apps.iwpLoadingFiles"
        :empty-label="t.apps.iwpNoFiles"
        @toggle="toggleFileTree"
        @open-file="openFile"
      />
      <WorkbenchCenterPane
        :workbench-mode="workbenchMode"
        :allow-requirements-mode="hasIwpRequirements"
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
        :save-label="t.apps.iwpSave"
        :saving-label="t.apps.iwpSaving"
        :build-button-label="t.apps.iwpBuild"
        :editor-loading-label="t.apps.iwpLoadingFile"
        :editor-placeholder="t.apps.iwpEditorPlaceholder"
        :empty-path-label="t.apps.iwpEmptyFile"
        :saved-label="t.apps.iwpSaved"
        :unsaved-label="t.apps.iwpUnsaved"
        :build-session-label="t.apps.iwpBuildSessionLabel"
        :open-build-session-label="t.apps.iwpOpenBuildSession"
        :readonly-title="t.apps.iwpReadonlyTitle"
        :readonly-file-path="readonlyFilePath"
        :readonly-file-line="readonlyFileLine"
        :readonly-file-content="readonlyFileContent"
        :readonly-loading="readonlyLoading"
        :readonly-error="readonlyError"
        :back-to-markdown-label="t.apps.iwpBackToMarkdown"
        :readonly-loading-label="t.apps.iwpReadonlyLoading"
        :readonly-empty-content-label="t.apps.iwpReadonlyEmpty"
        :agent-log-title="t.apps.workbenchAgentLogTitle"
        :agent-log-empty-label="t.apps.workbenchAgentLogEmpty"
        :agent-log-running-label="t.apps.workbenchAgentLogRunning"
        :agent-log-idle-label="t.apps.workbenchAgentLogIdle"
        :agent-log-height="agentLogHeightPx"
        :is-resizing-agent-log="isResizingAgentLog"
        :tts-enabled="ttsEnabled"
        :tts-playback-state="ttsPlaybackState"
        :tts-stream-status="ttsStreamStatus"
        :selected-tts-engine="selectedTtsEngine"
        :tts-engine-options="ttsEngineOptions"
        @update-chat-input="setChatInput"
        @composer-selection-change="handleComposerSelectionChange"
        @update-markdown="updateContent"
        @save-markdown="saveCurrentFile"
        @trigger-build="triggerBuild"
        @open-build-session="openBuildSession"
        @back-to-markdown="backToMarkdown"
        @start-resize-agent-log="startResizeAgentLog"
        @toggle-tts-enabled="toggleTtsEnabled"
        @stop-tts="stopTtsPlayback"
        @select-tts-engine="selectTtsEngine"
      />
      <div
        class="column-resizer"
        :class="{ active: isResizingPreview }"
        @pointerdown="startResizePreview"
      >
        <span class="column-resizer-line"></span>
      </div>
    </template>
    <WorkbenchPreviewSection
      :is-preview-renderable="isPreviewRenderable"
      :show-compact-shell="isAssistantCompactSurface"
      :preview-pane-key="previewPaneKey"
      :plugin-id="pluginId"
      :plugin-url="pluginUrl"
      :preview-log-session-id="previewLogSessionId"
      :preview-lifecycle-task="previewLifecycleTask"
      :preview-lifecycle-busy="previewLifecycleBusy"
      :preview-install-status="previewInstallStatus"
      :preview-install-error-message="previewInstallErrorMessage"
      :preview-loading-text="previewLoadingText"
      :chat-input="chatInput"
      :preview-chat-blocked="previewChatBlocked"
      :preview-blocked-text="t.apps.blockedByDepsInstall"
      :tts-enabled="ttsEnabled"
      :tts-playback-state="ttsPlaybackState"
      :tts-stream-status="ttsStreamStatus"
      :on-capability-invoke-request="handleCapabilityInvokeRequest"
      :on-host-invoke-request="handleHostInvokeRequest"
      @restart="handleRestartPreview"
      @retry-install="handleRetryInstall"
      @inspector-select="handleInspectorSelect"
      @context-push="handleContextPush"
      @tts-speak-accepted="handleTtsSpeakAccepted"
      @tts-stopped="handleTtsStopped"
      @update-chat-input="setChatInput"
      @composer-selection-change="handleComposerSelectionChange"
      @toggle-tts-enabled="toggleTtsEnabled"
      @stop-tts="stopTtsPlayback"
    />
    <WorkbenchExitConfirmDialog
      :visible="exitDialogVisible"
      :busy="exitBusy"
      :title="t.apps.workbenchCloseConfirmTitle"
      :message="t.apps.workbenchCloseConfirmMessage"
      :running-warning="exitWarningMessage"
      :save-and-exit-label="t.apps.workbenchCloseSaveAndExit"
      :exit-directly-label="t.apps.workbenchCloseExitDirectly"
      :cancel-label="t.apps.workbenchCloseCancel"
      @save-and-exit="handleExitSaveAndClose"
      @exit-directly="handleExitDirectly"
      @cancel="handleExitCancel"
    />
    <WorkbenchPublishOverlays
      :publish-dialog-visible="publishDialogVisible"
      :plugin-name="activeApp?.name || pluginId"
      :plugin-version="activeApp?.version || '0.1.0'"
      :plugin-description="activeApp?.description || ''"
      :publish-state="publishState"
      :mobile-qr-dialog-visible="mobileQrDialogVisible"
      :mobile-share-url="mobileShareUrl"
      :mobile-lan-ip="mobileLanIp"
      :mobile-qr-loading="mobileQrLoading"
      :mobile-qr-error="mobileQrError"
      :mobile-offline-dialog-visible="mobileOfflineDialogVisible"
      :mobile-publish-state="mobilePublishState"
      :mobile-default-version="mobilePublishState.last_status?.local_version || activeApp?.version || '0.1.0'"
      :publish-toast="publishToast"
      @close-web-publish="closePublishDialog"
      @close-mobile-qr="closeMobileQr"
      @close-mobile-offline="closeMobileOffline"
      @submit-web-publish="handlePublish"
      @submit-mobile-publish="handleMobilePublish"
      @refresh-mobile-share="handleMobileRefreshShare"
    />
  </div>
</template>

<script setup lang="ts">
import WorkbenchHeaderBar from '@/features/plugin-dev-workbench/components/WorkbenchHeaderBar.vue'
import WorkbenchPreviewSection from '@/features/plugin-dev-workbench/components/WorkbenchPreviewSection.vue'
import WorkbenchPublishOverlays from '@/features/plugin-dev-workbench/components/WorkbenchPublishOverlays.vue'
import IwpFileDrawer from '@/features/plugin-dev-workbench/components/IwpFileDrawer.vue'
import WorkbenchCenterPane from '@/features/plugin-dev-workbench/components/WorkbenchCenterPane.vue'
import WorkbenchExitConfirmDialog from '@/features/plugin-dev-workbench/components/WorkbenchExitConfirmDialog.vue'
import { usePluginDevWorkbenchOrchestration } from '@/features/plugin-dev-workbench/composables/usePluginDevWorkbenchOrchestration'

const {
  t,
  chatInput,
  activeApp,
  pluginId,
  appTypeLabel,
  isWebApp,
  isMobileApp,
  isPreviewRenderable,
  previewPaneKey,
  pluginUrl,
  previewLogSessionId,
  previewLifecycleTask,
  previewLifecycleBusy,
  previewInstallStatus,
  previewInstallErrorMessage,
  previewLoadingText,
  previewChatBlocked,
  publishDialogVisible,
  publishState,
  mobileQrDialogVisible,
  mobileShareUrl,
  mobileLanIp,
  mobileQrLoading,
  mobileQrError,
  mobileOfflineDialogVisible,
  mobilePublishState,
  publishToast,
  openPublishDialog,
  closePublishDialog,
  openMobilePreviewQr,
  openMobileOfflinePlaceholder,
  closeMobileQr,
  closeMobileOffline,
  handleCloseWorkbench,
  handleExitSaveAndClose,
  handleExitDirectly,
  handleExitCancel,
  exitDialogVisible,
  exitBusy,
  exitWarningMessage,
  handleRestartPreview,
  handleRetryInstall,
  handleInspectorSelect,
  handleContextPush,
  handleTtsSpeakAccepted,
  handleTtsStopped,
  handleComposerSelectionChange,
  handlePublish,
  handleMobilePublish,
  handleMobileRefreshShare,
  iwpRoot,
  fileTreeCollapsed,
  centerPaneMode,
  filesLoading,
  fileList,
  activeFilePath,
  markdownContent,
  fileLoading,
  fileSaving,
  buildState,
  isDirty,
  hasActiveFile,
  canBuild,
  openFile,
  saveCurrentFile,
  updateContent,
  toggleFileTree,
  triggerBuild,
  readonlyFilePath,
  readonlyFileLine,
  readonlyFileContent,
  readonlyLoading,
  readonlyError,
  backToMarkdown,
  openBuildSession,
  hasBuildSession,
  isBuildRunning,
  workbenchMode,
  workbenchLayoutVariant,
  hasIwpRequirements,
  isAssistantCompactSurface,
  setWorkbenchMode,
  setChatInput,
  previewWidthPx,
  agentLogHeightPx,
  isResizingPreview,
  isResizingAgentLog,
  startResizePreview,
  startResizeAgentLog,
  ttsEnabled,
  selectedTtsEngine,
  ttsEngineOptions,
  ttsPlaybackState,
  ttsStreamStatus,
  toggleTtsEnabled,
  selectTtsEngine,
  stopTtsPlayback,
  handleCapabilityInvokeRequest,
  handleHostInvokeRequest,
} = usePluginDevWorkbenchOrchestration()
</script>

<style scoped>
.plugin-dev-workbench {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: auto minmax(520px, 1fr) 8px minmax(360px, var(--preview-pane-width, 460px));
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  background: var(--wb-canvas);
}

.plugin-dev-workbench.agent-preview-layout {
  grid-template-columns: minmax(360px, var(--agent-pane-width, 460px)) 8px minmax(520px, 1fr);
}

.plugin-dev-workbench.assistant-compact-layout {
  grid-template-columns: minmax(0, 1fr);
}

.plugin-dev-workbench.split-no-iwp-layout {
  grid-template-columns: minmax(520px, 1fr) 8px minmax(360px, var(--preview-pane-width, 460px));
}

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
