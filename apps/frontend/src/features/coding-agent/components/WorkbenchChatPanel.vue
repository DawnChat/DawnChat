<template>
  <div class="workbench-chat-panel">
    <CodingChatShell
      :model-value="modelValue"
      :workspace-target="workspaceTarget"
      :panel-title="''"
      :empty-text="labels.empty"
      :placeholder="labels.placeholder"
      :streaming-text="labels.streaming"
      :blocked-text="labels.blocked"
      :run-label="labels.run"
      :new-chat-label="labels.newChat"
      :show-rules-status="false"
      :show-session-tabs="false"
      :show-engine-selector="true"
      :show-agent-selector="false"
      :show-model-selector="true"
      :allow-plan-to-build="false"
      :force-agent="'general'"
      @update:model-value="(value) => emit('update:modelValue', value)"
      @composer-selection-change="(payload) => emit('composer-selection-change', payload)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/composables/useI18n'
import type { WorkspaceTarget } from '@/features/coding-agent'
import CodingChatShell from './CodingChatShell.vue'

defineProps<{
  modelValue: string
  workspaceTarget: WorkspaceTarget
  showModelSelector?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'composer-selection-change': [payload: { start: number; end: number; focused: boolean }]
}>()

const { t } = useI18n()

const labels = computed(() => {
  const apps = (t.value as any).apps || {}
  const workbench = (t.value as any).workbench || {}
  return {
    empty: String(workbench.startChatDesc || workbench.emptyState?.startNew || '开始一个新的对话'),
    placeholder: String(workbench.chatPlaceholder || '输入你的问题...'),
    streaming: String(apps.devChatStreaming || '正在生成中'),
    blocked: String(apps.blockedByQuestion || '请先回答待处理问题或权限请求，再继续发送消息。'),
    run: String(t.value.common.run || '发送'),
    newChat: String(apps.newChat || 'New Chat')
  }
})
</script>

<style scoped>
.workbench-chat-panel {
  min-height: 0;
  height: 100%;
}
</style>
