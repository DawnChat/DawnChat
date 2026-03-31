<template>
  <div ref="messageListRef" class="message-list" @scroll="handleScroll">
    <div v-if="presentedTimelineItems.length === 0 && !props.isStreaming" class="empty-tip">
      {{ emptyText }}
    </div>

    <template v-for="timeline in presentedTimelineItems" :key="timeline.id">
      <div v-if="timeline.kind === 'part'" class="msg-item-row" :class="timeline.role === 'user' ? 'user' : 'assistant-flat'">
        <template v-if="timeline.role === 'user'">
          <span class="msg-role">{{ labels.you }}</span>
          <div class="msg-item">
            <PluginDevMessagePartRenderer
              :item="timeline.item"
              :reasoning-expanded="isReasoningExpanded(timeline.item.id, timeline.item.isStreaming)"
              @toggle-reasoning="toggleReasoning(timeline.item.id, timeline.item.isStreaming)"
            />
          </div>
        </template>
        <template v-else>
          <PluginDevMessagePartRenderer
            :item="timeline.item"
            :reasoning-expanded="isReasoningExpanded(timeline.item.id, timeline.item.isStreaming)"
            @toggle-reasoning="toggleReasoning(timeline.item.id, timeline.item.isStreaming)"
          />
        </template>
      </div>

      <PluginDevQuestionCard
        v-else-if="timeline.kind === 'question'"
        :question="timeline.question"
        :agent-label="labels.agent"
        :question-required-label="labels.questionRequired"
        :question-label="labels.question"
        :custom-answer-label="labels.customAnswer"
        :submit-label="labels.submit"
        :reject-label="labels.reject"
        @question-reply="(requestID, answers) => emit('question-reply', requestID, answers)"
        @question-reject="(requestID) => emit('question-reject', requestID)"
      />

      <PluginDevPermissionCard
        v-else-if="timeline.kind === 'permission'"
        :permission="timeline.permission"
        :agent-label="labels.agent"
        :permission-required-label="labels.permissionRequired"
        :allow-once-label="labels.allowOnce"
        :always-allow-label="labels.alwaysAllow"
        :reject-label="labels.reject"
        @permission="(id, response, remember) => emit('permission', id, response, remember)"
      />

      <div v-else-if="timeline.kind === 'todo'" class="todo-timeline-item" :class="{ pinned: isScrollingDown }">
        <PluginDevTodoDock
          :todos="timeline.todos"
          :title="labels.todosTitle"
          :collapse-label="labels.todoCollapse"
          :expand-label="labels.todoExpand"
        />
      </div>
    </template>

    <PluginDevAssistantWaiting
      :timeline-items="props.timelineItems"
      :is-streaming="props.isStreaming"
      :has-pending-playback="hasPendingPlayback"
      :text="waitingText"
      :waiting-reason="props.waitingReason"
    />
    <div v-if="showPlanQuickSwitch" class="plan-quick-switch">
      <span class="plan-quick-switch-tip">{{ labels.planQuickSwitchTip }}</span>
      <button class="plan-quick-switch-btn" type="button" @click="emit('switch-to-build')">
        {{ labels.planSwitchToBuild }}
      </button>
    </div>
    <div v-if="lastError" class="error-tip">
      <div class="error-summary">{{ lastError }}</div>
      <details v-if="showErrorDetails" class="error-details">
        <summary>{{ labels.errorDetailToggle }}</summary>
        <pre>{{ props.lastErrorRaw }}</pre>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import PluginDevAssistantWaiting from '@/features/coding-agent/components/plugin-dev-chat/PluginDevAssistantWaiting.vue'
import PluginDevMessagePartRenderer from '@/features/coding-agent/components/plugin-dev-chat/PluginDevMessagePartRenderer.vue'
import PluginDevPermissionCard from '@/features/coding-agent/components/plugin-dev-chat/PluginDevPermissionCard.vue'
import PluginDevQuestionCard from '@/features/coding-agent/components/plugin-dev-chat/PluginDevQuestionCard.vue'
import PluginDevTodoDock from '@/features/coding-agent/components/plugin-dev-chat/PluginDevTodoDock.vue'
import { useI18n } from '@/composables/useI18n'
import { useStreamingPresentation } from '@/features/coding-agent/components/plugin-dev-chat/useStreamingPresentation'

interface RenderItem {
  id: string
  type: 'text' | 'tool' | 'reasoning' | 'step' | 'unknown'
  text?: string
  tool?: string
  status?: string
  toolDisplay?: {
    kind: string
    renderMode?: 'inline' | 'collapsible'
    toolName?: string
    argsText?: string
    argsPreview?: string
    hasDetails?: boolean
    title: string
    summary: string
    detailBody?: string
    detailsText?: string
    command: string
    outputTail: string
    diffStat: string
    patchPreview: string
    languageHint?: string
    codeLines?: string[]
    previewLineCount?: number
    hiddenLineCount?: number
  }
  isStreaming: boolean
}

interface RenderRow {
  info: {
    id: string
    role: string
  }
  items: RenderItem[]
}

interface PermissionCardLite {
  id: string
  tool: string
  detail: string
  status: 'pending' | 'approved' | 'rejected'
}

interface TodoItemLite {
  id: string
  content: string
  status: string
}

interface QuestionCardLite {
  id: string
  questions: Array<{
    question: string
    header: string
    options: Array<{ label: string; description: string }>
    multiple?: boolean
    custom?: boolean
  }>
}

interface TimelineItemPartLite {
  id: string
  kind: 'part'
  role: string
  item: RenderItem
}

interface TimelineItemQuestionLite {
  id: string
  kind: 'question'
  question: QuestionCardLite
}

interface TimelineItemPermissionLite {
  id: string
  kind: 'permission'
  permission: PermissionCardLite
}

interface TimelineItemTodoLite {
  id: string
  kind: 'todo'
  todos: TodoItemLite[]
}

type TimelineItemLite = TimelineItemPartLite | TimelineItemQuestionLite | TimelineItemPermissionLite | TimelineItemTodoLite

const props = defineProps<{
  chatRows?: RenderRow[]
  permissionCards?: PermissionCardLite[]
  questionCards?: QuestionCardLite[]
  todos?: TodoItemLite[]
  timelineItems: TimelineItemLite[]
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

const messageListRef = ref<HTMLElement | null>(null)
const reasoningExpanded = ref<Record<string, boolean>>({})
const shouldAutoScroll = ref(true)
const isScrollingDown = ref(false)
const lastScrollTop = ref(0)
const { t } = useI18n()
const timelineItemsRef = computed(() => props.timelineItems)
const { presentedTimelineItems, hasPendingPlayback } = useStreamingPresentation(timelineItemsRef)

const labels = computed(() => {
  const apps = (t.value as any).apps || {}
  return {
    you: String(apps.you || 'You'),
    agent: String(apps.agent || 'Agent'),
    permissionRequired: String(apps.permissionRequired || 'Permission required'),
    questionRequired: String(apps.questionRequired || 'Question required'),
    question: String(apps.question || 'Question'),
    customAnswer: String(apps.customAnswer || 'Custom answer'),
    allowOnce: String(apps.allowOnce || 'Allow once'),
    alwaysAllow: String(apps.alwaysAllow || 'Always allow'),
    reject: String(apps.reject || 'Reject'),
    submit: String(apps.submit || 'Submit'),
    planSwitchToBuild: String(apps.planSwitchToBuild || 'Switch to Build'),
    planQuickSwitchTip: String(apps.planQuickSwitchTip || 'Plan 已完成后，可切换到 Build 执行。'),
    todosTitle: String(apps.todosTitle || 'To-dos'),
    todoCollapse: String(apps.todoCollapse || 'Collapse'),
    todoExpand: String(apps.todoExpand || 'Expand'),
    errorDetailToggle: String(apps.codingErrorDetailsToggle || '查看错误详情'),
    waitingGenerating: String(apps.codingWaitingGenerating || props.streamingText || '生成中...'),
    waitingPermission: String(apps.codingWaitingPermission || '等待你授权以继续执行...'),
    waitingQuestion: String(apps.codingWaitingQuestion || '等待你回答问题...'),
    waitingStalled: String(apps.codingWaitingStalled || '连接正常，正在等待运行结果...')
  }
})

const waitingText = computed(() => {
  if (props.waitingReason === 'waiting_permission') return labels.value.waitingPermission
  if (props.waitingReason === 'waiting_question') return labels.value.waitingQuestion
  if (props.waitingReason === 'stalled') return labels.value.waitingStalled
  return labels.value.waitingGenerating
})

const hasAssistantReply = computed(() => {
  return presentedTimelineItems.value.some((item) => {
    if (item.kind !== 'part' || item.role === 'user') return false
    if (item.item.type === 'text' || item.item.type === 'reasoning') {
      return String(item.item.text || '').length > 0
    }
    return true
  })
})

const showPlanQuickSwitch = computed(() => {
  if (props.isStreaming) return false
  return props.canSwitchPlanToBuild && hasAssistantReply.value
})

const showErrorDetails = computed(() => {
  if (!props.lastError || !props.lastErrorRaw) return false
  const readable = String(props.lastError).trim()
  const raw = String(props.lastErrorRaw).trim()
  return Boolean(raw) && raw !== readable
})

const renderActivitySignature = computed(() => {
  const last = presentedTimelineItems.value[presentedTimelineItems.value.length - 1]
  if (!last) {
    return `empty:${props.isStreaming ? '1' : '0'}:${hasPendingPlayback.value ? '1' : '0'}`
  }
  if (last.kind === 'part') {
    return [
      'part',
      presentedTimelineItems.value.length,
      props.isStreaming ? '1' : '0',
      last.id,
      last.item.type,
      String(last.item.text || '').length,
      String(last.item.status || ''),
      last.item.isStreaming ? '1' : '0'
    ].join(':')
  }
  if (last.kind === 'todo') {
    return [
      'todo',
      presentedTimelineItems.value.length,
      props.isStreaming ? '1' : '0',
      last.id,
      last.todos.length,
      last.todos.map((item) => `${item.id}:${item.status}`).join('|')
    ].join(':')
  }
  if (last.kind === 'permission') {
    return [
      'permission',
      presentedTimelineItems.value.length,
      props.isStreaming ? '1' : '0',
      last.id,
      last.permission.status
    ].join(':')
  }
  return [
    'question',
    presentedTimelineItems.value.length,
    props.isStreaming ? '1' : '0',
    last.id,
    last.question.id
  ].join(':')
})

const isReasoningExpanded = (id: string, isStreamingItem: boolean) => {
  if (isStreamingItem) return true
  return Boolean(reasoningExpanded.value[id])
}

const toggleReasoning = (id: string, isStreamingItem: boolean) => {
  if (isStreamingItem) return
  reasoningExpanded.value[id] = !reasoningExpanded.value[id]
}

watch(
  () => props.activeReasoningItemId,
  (activeId) => {
    const nextState: Record<string, boolean> = {}
    if (activeId) {
      nextState[activeId] = true
    }
    reasoningExpanded.value = nextState
  }
)

watch(
  () => renderActivitySignature.value,
  async () => {
    await nextTick()
    const el = messageListRef.value
    if (el && shouldAutoScroll.value) {
      el.scrollTop = el.scrollHeight
    }
  }
)

const handleScroll = () => {
  const el = messageListRef.value
  if (!el) return
  const top = el.scrollTop
  isScrollingDown.value = top > lastScrollTop.value
  lastScrollTop.value = top
  const distanceToBottom = el.scrollHeight - (el.scrollTop + el.clientHeight)
  shouldAutoScroll.value = distanceToBottom <= 72
}
</script>

<style scoped>
.message-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  background: var(--color-surface-1);
}

.empty-tip {
  color: var(--color-text-secondary);
  font-size: 0.85rem;
}

.msg-item-row {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.msg-item-row.user {
  align-items: flex-end;
}

.msg-item-row.assistant {
  align-items: flex-start;
}

.msg-item-row.assistant-flat {
  align-items: stretch;
}

.msg-role {
  display: block;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  padding: 0 0.1rem;
}

.msg-item {
  max-width: 92%;
  min-width: 0;
  border-radius: 10px;
  padding: 0.65rem 0.75rem;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
}

.msg-item-row.assistant .msg-item {
  background: var(--color-surface-2);
}

.msg-item-row.user .msg-item {
  background: color-mix(in srgb, var(--color-primary) 14%, var(--color-surface-2));
}

.todo-timeline-item {
  width: min(760px, 100%);
}

.todo-timeline-item.pinned {
  position: sticky;
  top: 0;
  z-index: 2;
}


.plan-quick-switch {
  border: 1px solid color-mix(in srgb, var(--color-primary) 30%, var(--color-border));
  border-radius: 8px;
  padding: 0.55rem 0.65rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  background: color-mix(in srgb, var(--color-primary) 8%, var(--color-surface-2));
}

.plan-quick-switch-tip {
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}

.plan-quick-switch-btn {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface-3);
  color: var(--color-text);
  height: 30px;
  padding: 0 0.65rem;
  font-size: 0.78rem;
  cursor: pointer;
}

.error-tip {
  color: #d9534f;
  font-size: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.error-summary {
  line-height: 1.35;
}

.error-details {
  color: color-mix(in srgb, #d9534f 90%, var(--color-text));
}

.error-details summary {
  cursor: pointer;
  user-select: none;
}

.error-details pre {
  margin: 0.35rem 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.35;
}

</style>
