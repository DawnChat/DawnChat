<template>
  <ChatMessageList
    :timeline-items="timelineItems"
    :active-reasoning-item-id="activeReasoningItemId"
    :is-streaming="isStreaming"
    :waiting-reason="waitingReason"
    :can-switch-plan-to-build="canSwitchPlanToBuild"
    :last-error="lastError"
    :last-error-raw="lastErrorRaw"
    :labels="labels"
    @permission="(id, response, remember) => emit('permission', id, response, remember)"
    @question-reply="(requestID, answers) => emit('question-reply', requestID, answers)"
    @question-reject="(requestID) => emit('question-reject', requestID)"
    @switch-to-build="emit('switch-to-build')"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import '@dawnchat/assistant-chat-ui/style.css'
import { ChatMessageList } from '@dawnchat/assistant-chat-ui'
import type {
  ChatMessageListLabels,
  ChatRenderItem,
  ChatTimelineItem,
  ChatTodoItem,
} from '@dawnchat/assistant-chat-ui'
import { useI18n } from '@/composables/useI18n'

interface RenderRow {
  info: {
    id: string
    role: string
  }
  items: ChatRenderItem[]
}

const props = defineProps<{
  chatRows?: RenderRow[]
  permissionCards?: unknown[]
  questionCards?: unknown[]
  todos?: ChatTodoItem[]
  timelineItems: ChatTimelineItem[]
  activeReasoningItemId: string
  isStreaming: boolean
  waitingReason: '' | 'generating' | 'waiting_permission' | 'waiting_question' | 'stalled'
  canSwitchPlanToBuild: boolean
  lastError: string | null
  lastErrorRaw?: string | null
  emptyText: string
  streamingText: string
}>()

const emit = defineEmits<{
  permission: [id: string, response: 'once' | 'always' | 'reject', remember?: boolean]
  'question-reply': [requestID: string, answers: string[][]]
  'question-reject': [requestID: string]
  'switch-to-build': []
}>()

const { t } = useI18n()
const labels = computed<Partial<ChatMessageListLabels>>(() => {
  const apps = (t.value as any).apps || {}
  return {
    userLabel: String(apps.you || 'You'),
    assistantLabel: String(apps.agent || 'Agent'),
    emptyText: props.emptyText,
    streamingText: props.streamingText,
    permissionRequiredLabel: String(apps.permissionRequired || 'Permission required'),
    questionRequiredLabel: String(apps.questionRequired || 'Question required'),
    questionLabel: String(apps.question || 'Question'),
    customAnswerLabel: String(apps.customAnswer || 'Custom answer'),
    allowOnceLabel: String(apps.allowOnce || 'Allow once'),
    alwaysAllowLabel: String(apps.alwaysAllow || 'Always allow'),
    rejectLabel: String(apps.reject || 'Reject'),
    submitLabel: String(apps.submit || 'Submit'),
    planSwitchLabel: String(apps.planSwitchToBuild || 'Switch to Build'),
    planQuickSwitchTip: String(apps.planQuickSwitchTip || 'Plan 已完成后，可切换到 Build 执行。'),
    todoTitle: String(apps.todosTitle || 'To-dos'),
    todoCollapseLabel: String(apps.todoCollapse || 'Collapse'),
    todoExpandLabel: String(apps.todoExpand || 'Expand'),
    errorDetailToggle: String(apps.codingErrorDetailsToggle || '查看错误详情'),
    waitingGeneratingText: String(apps.codingWaitingGenerating || props.streamingText || '生成中...'),
    waitingPermissionText: String(apps.codingWaitingPermission || '等待你授权以继续执行...'),
    waitingQuestionText: String(apps.codingWaitingQuestion || '等待你回答问题...'),
    waitingStalledText: String(apps.codingWaitingStalled || '连接正常，正在等待运行结果...'),
  }
})
</script>
