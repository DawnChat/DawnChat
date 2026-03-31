<template>
  <div class="dev-chat-panel">
    <CodingChatShell
      :model-value="modelValue"
      :plugin-id="pluginId"
      :panel-title="panelTitle || labels.devChatTitle"
      :empty-text="labels.devChatEmpty"
      :placeholder="labels.devChatPlaceholder"
      :streaming-text="labels.devChatStreaming"
      :blocked-text="labels.blockedByQuestion"
      :external-blocked="externallyBlocked"
      :external-blocked-text="labels.blockedByDepsInstall"
      :run-label="t.common.run"
      :new-chat-label="labels.newChat"
      :show-rules-status="true"
      :show-panel-header="showPanelHeader"
      :show-session-tabs="showSessionTabs"
      :show-engine-selector="showEngineSelector"
      :show-agent-selector="showAgentSelector"
      :show-model-selector="showModelSelector"
      :show-composer="showComposer"
      :show-tts-control="showTtsControl"
      :tts-enabled="ttsEnabled"
      :tts-playback-state="ttsPlaybackState"
      :tts-stream-status="ttsStreamStatus"
      :selected-tts-engine="selectedTtsEngine"
      :tts-engine-options="ttsEngineOptions"
      :allow-plan-to-build="true"
      :plan-switch-applied-text="labels.planSwitchApplied"
      :plan-keep-input-hint-text="labels.planKeepInputHint"
      :plan-build-prefill-text="labels.planBuildPrefill"
      @update:model-value="(value) => emit('update:modelValue', value)"
      @composer-selection-change="(payload) => emit('composer-selection-change', payload)"
      @toggle-tts-enabled="emit('toggle-tts-enabled')"
      @stop-tts="emit('stop-tts')"
      @select-tts-engine="(value) => emit('select-tts-engine', value)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/composables/useI18n'
import { CodingChatShell } from '@/features/coding-agent'
import type { TtsPlaybackState } from '@/services/tts/ttsPlaybackQueue'

withDefaults(defineProps<{
  modelValue: string
  pluginId?: string
  externallyBlocked?: boolean
  panelTitle?: string
  showPanelHeader?: boolean
  showSessionTabs?: boolean
  showEngineSelector?: boolean
  showAgentSelector?: boolean
  showModelSelector?: boolean
  showComposer?: boolean
  showTtsControl?: boolean
  ttsEnabled?: boolean
  ttsPlaybackState?: TtsPlaybackState
  ttsStreamStatus?: 'idle' | 'connecting' | 'reconnecting' | 'streaming' | 'closed'
  selectedTtsEngine?: string
  ttsEngineOptions?: Array<{ id: string; label: string }>
}>(), {
  showPanelHeader: true,
  showSessionTabs: true,
  showEngineSelector: true,
  showAgentSelector: true,
  showModelSelector: true,
  showComposer: true,
  showTtsControl: false,
  ttsEnabled: true,
  ttsPlaybackState: 'idle',
  ttsStreamStatus: 'idle',
  selectedTtsEngine: 'system',
  ttsEngineOptions: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'composer-selection-change': [payload: { start: number; end: number; focused: boolean }]
  'toggle-tts-enabled': []
  'stop-tts': []
  'select-tts-engine': [value: string]
}>()

const { t } = useI18n()

const labels = computed(() => {
  const apps = (t.value as any).apps || {}
  return {
    devChatTitle: String(apps.devChatTitle || '开发助手'),
    devChatEmpty: String(apps.devChatEmpty || '等待输入指令...'),
    devChatPlaceholder: String(apps.devChatPlaceholder || '描述你想要的修改...'),
    devChatStreaming: String(apps.devChatStreaming || '正在生成中'),
    newChat: String(apps.newChat || 'New Chat'),
    sharedRulesDisabled: String(apps.sharedRulesDisabled || '共享规则: 未启用'),
    sharedRulesEnabled: String(apps.sharedRulesEnabled || '共享规则: 已启用'),
    sharedRulesVersion: String(apps.sharedRulesVersion || '共享规则: v{version}'),
    blockedByQuestion: String(apps.blockedByQuestion || '请先回答待处理问题或权限请求，再继续发送消息。'),
    blockedByDepsInstall: String(apps.blockedByDepsInstall || '正在准备开发环境，完成后你就可以继续让 Coding Agent 修改代码。'),
    planSwitchApplied: String(apps.planSwitchApplied || '已切换到 Build 模式。'),
    planKeepInputHint: String(apps.planKeepInputHint || '已保留你当前输入。'),
    planBuildPrefill: String(apps.planBuildPrefill || '请根据计划开始执行实现。')
  }
})
</script>

<style scoped>
.dev-chat-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-surface-1);
  border-left: 1px solid var(--color-border);
}
</style>
