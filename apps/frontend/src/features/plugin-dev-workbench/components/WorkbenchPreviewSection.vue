<template>
  <div class="preview-column" :class="{ compact: showCompactShell }">
    <div class="preview-content">
      <PluginPreviewPane
        v-if="isPreviewRenderable"
        :key="previewPaneKey"
        :plugin-id="pluginId"
        :plugin-url="pluginUrl"
        :log-session-id="previewLogSessionId"
        :lifecycle-task="previewLifecycleTask"
        :lifecycle-busy="previewLifecycleBusy"
        :install-status="previewInstallStatus"
        :install-error-message="previewInstallErrorMessage"
        :show-stop-button="false"
        :is-compact-surface="showCompactShell"
        :on-capability-invoke-request="onCapabilityInvokeRequest"
        :on-host-invoke-request="onHostInvokeRequest"
        @restart="(appId) => emit('restart', appId)"
        @toggle-fullscreen="emit('toggleFullscreen')"
        @retry-install="emit('retryInstall')"
        @inspector-select="(payload) => emit('inspectorSelect', payload)"
        @context-push="(payload) => emit('contextPush', payload)"
        @tts-speak-accepted="(payload) => emit('ttsSpeakAccepted', payload)"
        @tts-stopped="(payload) => emit('ttsStopped', payload)"
      />
      <div v-else class="loading">
        <span class="spinner"></span>
        <span>{{ previewLoadingText }}</span>
      </div>
      <AssistantCompactShell
        v-if="showCompactShell"
        :model-value="chatInput"
        :plugin-id="pluginId"
        :external-blocked="previewChatBlocked"
        :external-blocked-text="previewBlockedText"
        :tts-enabled="ttsEnabled"
        :tts-playback-state="ttsPlaybackState"
        :tts-stream-status="ttsStreamStatus"
        @update-model-value="(value) => emit('updateChatInput', value)"
        @composer-selection-change="(payload) => emit('composerSelectionChange', payload)"
        @toggle-tts-enabled="emit('toggleTtsEnabled')"
        @stop-tts="emit('stopTts')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import PluginPreviewPane from '@/features/plugin/components/PluginPreviewPane.vue'
import AssistantCompactShell from '@/features/plugin-dev-workbench/components/AssistantCompactShell.vue'
import type { InspectorSelectPayload } from '@/types/inspector'
import type {
  CapabilityInvokeExecutionContext,
  HostInvokeExecutionContext
} from '@/composables/usePluginUiBridge'
import type {
  ContextPushPayload,
  TtsSpeakAcceptedPayload,
  TtsStoppedPayload
} from '@/services/plugin-ui-bridge/messageProtocol'
import type { LifecycleTask } from '@/features/plugin/store'
import type { TtsPlaybackState } from '@/services/tts/ttsPlaybackQueue'

defineProps<{
  isPreviewRenderable: boolean
  showCompactShell: boolean
  previewPaneKey: number
  pluginId: string
  pluginUrl: string
  previewLogSessionId: string
  previewLifecycleTask: LifecycleTask | null
  previewLifecycleBusy: boolean
  previewInstallStatus: 'idle' | 'running' | 'success' | 'failed'
  previewInstallErrorMessage: string
  previewLoadingText: string
  chatInput: string
  previewChatBlocked: boolean
  previewBlockedText: string
  ttsEnabled: boolean
  ttsPlaybackState: TtsPlaybackState
  ttsStreamStatus: 'idle' | 'connecting' | 'reconnecting' | 'streaming' | 'closed'
  onCapabilityInvokeRequest?: (
    context: CapabilityInvokeExecutionContext
  ) => Promise<Record<string, unknown> | null> | Record<string, unknown> | null
  onHostInvokeRequest?: (
    context: HostInvokeExecutionContext
  ) => Promise<Record<string, unknown>> | Record<string, unknown>
}>()

const emit = defineEmits<{
  restart: [appId: string]
  toggleFullscreen: []
  retryInstall: []
  inspectorSelect: [payload: InspectorSelectPayload]
  contextPush: [payload: ContextPushPayload]
  ttsSpeakAccepted: [payload: TtsSpeakAcceptedPayload]
  ttsStopped: [payload: TtsStoppedPayload]
  updateChatInput: [value: string]
  composerSelectionChange: [payload: { start: number; end: number; focused: boolean }]
  toggleTtsEnabled: []
  stopTts: []
}>()
</script>

<style scoped>
.preview-column {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--wb-pane-side);
  border-left: 1px solid var(--wb-border-subtle);
  padding: 0.62rem 0.62rem 0.62rem 0.58rem;
}

.preview-column.compact {
  border-left: none;
  padding: 0;
  background: var(--wb-pane-main);
}

.preview-content {
  flex: 1;
  min-height: 0;
  background: var(--wb-pane-main);
  border: 1px solid var(--wb-border-strong);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: var(--wb-inset-shadow);
  position: relative;
}

.preview-column.compact .preview-content {
  border: none;
  border-radius: 0;
  box-shadow: none;
}

.loading {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  color: var(--color-text-secondary);
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
