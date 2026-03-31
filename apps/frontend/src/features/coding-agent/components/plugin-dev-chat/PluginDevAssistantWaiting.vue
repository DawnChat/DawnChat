<template>
  <div v-if="showWaiting" class="waiting-placeholder" :class="`is-${waitingMode}`" aria-live="polite">
    <div class="waiting-content">
      <span class="waiting-label">{{ text }}</span>
      <span class="waiting-indicator" aria-hidden="true">
        <span class="waiting-dot" />
        <span class="waiting-dot" />
        <span class="waiting-dot" />
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

interface WaitingTimelinePart {
  id: string
  kind: 'part'
  role: string
  item: {
    id: string
    type: string
    text?: string
    isStreaming: boolean
    status?: string
  }
}

interface WaitingTimelineQuestion {
  id: string
  kind: 'question'
  question: { id: string }
}

interface WaitingTimelinePermission {
  id: string
  kind: 'permission'
  permission: { id: string; status: string }
}

interface WaitingTimelineTodo {
  id: string
  kind: 'todo'
  todos: Array<{ id: string; status: string }>
}

type WaitingTimelineItem =
  | WaitingTimelinePart
  | WaitingTimelineQuestion
  | WaitingTimelinePermission
  | WaitingTimelineTodo

const props = defineProps<{
  timelineItems: WaitingTimelineItem[]
  isStreaming: boolean
  hasPendingPlayback: boolean
  text: string
  waitingReason: '' | 'generating' | 'waiting_permission' | 'waiting_question' | 'stalled'
}>()

const STALL_WAIT_MS = 1000

const waitingMode = ref<'initial' | 'stalled' | ''>('')
let stallWaitTimer: number | null = null

const latestUserMessageIndex = computed(() => {
  for (let i = props.timelineItems.length - 1; i >= 0; i -= 1) {
    const item = props.timelineItems[i]
    if (item.kind === 'part' && item.role === 'user') {
      return i
    }
  }
  return -1
})

const hasAssistantResponseStarted = computed(() => {
  return props.timelineItems.some((item) => {
    if (item.kind === 'part') {
      return item.role !== 'user'
    }
    return true
  })
})

const hasAssistantResponseForLatestUser = computed(() => {
  if (latestUserMessageIndex.value < 0) {
    return hasAssistantResponseStarted.value
  }
  return props.timelineItems.slice(latestUserMessageIndex.value + 1).some((item) => {
    if (item.kind === 'part') {
      return item.role !== 'user'
    }
    return true
  })
})

const activitySignature = computed(() => {
  return [
    props.isStreaming ? '1' : '0',
    props.hasPendingPlayback ? '1' : '0',
    props.timelineItems.map((item) => {
      if (item.kind === 'part') {
        return [
          item.kind,
          item.id,
          item.role,
          item.item.type,
          String(item.item.text || '').length,
          item.item.isStreaming ? '1' : '0',
          String(item.item.status || '')
        ].join(':')
      }
      if (item.kind === 'todo') {
        return [item.kind, item.id, item.todos.map((todo) => `${todo.id}:${todo.status}`).join('|')].join(':')
      }
      if (item.kind === 'permission') {
        return [item.kind, item.id, item.permission.status].join(':')
      }
      return [item.kind, item.id, item.question.id].join(':')
    }).join(';')
  ].join(':')
})

const showWaiting = computed(() => waitingMode.value !== '')

const clearStallWaitTimer = () => {
  if (stallWaitTimer !== null) {
    window.clearTimeout(stallWaitTimer)
    stallWaitTimer = null
  }
}

const syncWaitingState = () => {
  clearStallWaitTimer()
  waitingMode.value = ''

  if (!props.isStreaming) return

  if (props.waitingReason === 'waiting_permission' || props.waitingReason === 'waiting_question') {
    waitingMode.value = 'initial'
    return
  }

  if (props.waitingReason === 'stalled') {
    waitingMode.value = 'stalled'
    return
  }

  if (latestUserMessageIndex.value >= 0 && !hasAssistantResponseForLatestUser.value) {
    waitingMode.value = 'initial'
    return
  }

  if (!hasAssistantResponseForLatestUser.value || props.hasPendingPlayback) {
    return
  }

  stallWaitTimer = window.setTimeout(() => {
    if (!props.isStreaming || !hasAssistantResponseForLatestUser.value || props.hasPendingPlayback) {
      return
    }
    waitingMode.value = 'stalled'
  }, STALL_WAIT_MS)
}

watch(
  () => [activitySignature.value, latestUserMessageIndex.value, hasAssistantResponseForLatestUser.value] as const,
  () => {
    syncWaitingState()
  },
  { immediate: true }
)

onUnmounted(() => {
  clearStallWaitTimer()
})
</script>

<style scoped>
.waiting-placeholder {
  display: flex;
  justify-content: flex-start;
}

.waiting-content {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  max-width: min(360px, 100%);
  padding: 0.3rem 0.4rem;
  border-radius: 8px;
  background: transparent;
  color: var(--color-text-secondary);
  overflow: hidden;
}

.waiting-content::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(100deg, transparent 0%, color-mix(in srgb, white 9%, transparent) 46%, transparent 74%);
  transform: translateX(-120%);
  animation: waiting-sheen 2.1s ease-in-out infinite;
  pointer-events: none;
}

.waiting-label {
  position: relative;
  z-index: 1;
  font-size: 0.82rem;
  line-height: 1.2;
  color: inherit;
}

.waiting-indicator {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  color: inherit;
}

.waiting-dot {
  width: 4px;
  height: 4px;
  border-radius: 999px;
  background: currentColor;
  animation: waiting-pulse 1.12s infinite ease-in-out;
}

.waiting-dot:nth-child(2) {
  animation-delay: 0.14s;
}

.waiting-dot:nth-child(3) {
  animation-delay: 0.28s;
}

.waiting-placeholder.is-stalled .waiting-content {
  color: color-mix(in srgb, var(--color-text) 62%, var(--color-text-secondary));
}

@keyframes waiting-pulse {
  0%,
  80%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  40% {
    opacity: 0.82;
    transform: translateY(-1px);
  }
}

@keyframes waiting-sheen {
  0% {
    transform: translateX(-130%);
  }
  100% {
    transform: translateX(130%);
  }
}
</style>
