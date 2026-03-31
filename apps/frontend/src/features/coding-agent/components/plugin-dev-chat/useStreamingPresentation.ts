import { computed, onUnmounted, ref, watch, type Ref } from 'vue'

type StreamingPartType = 'text' | 'reasoning'

export interface StreamingPresentationPart {
  id: string
  type: string
  text?: string
  isStreaming: boolean
}

export interface StreamingPresentationTimelinePart {
  id: string
  kind: 'part'
  role: string
  item: StreamingPresentationPart
}

export interface StreamingPresentationTimelineOther {
  id: string
  kind: string
}

export type StreamingPresentationTimelineItem =
  | StreamingPresentationTimelinePart
  | StreamingPresentationTimelineOther

interface PlaybackState {
  displayedLength: number
  targetText: string
  isStreaming: boolean
  expedite: boolean
  supportsTyping: boolean
}

const NORMAL_TICK_MS = 34

function isPlayablePartType(type: unknown): type is StreamingPartType {
  const normalized = String(type || '').toLowerCase()
  return normalized === 'text' || normalized === 'reasoning'
}

type StreamingSourcePart = {
  id: string
  type: string
  text?: string
  isStreaming: boolean
}

type StreamingSourceTimelineItem = {
  id: string
  kind: string
}

type PlayableTimelineShape = StreamingSourceTimelineItem & {
  kind: 'part'
  role: string
  item: StreamingSourcePart
}

function isPlayableTimelinePart<T extends StreamingSourceTimelineItem>(item: T): item is T & PlayableTimelineShape {
  if (item.kind !== 'part' || !('item' in item)) return false
  const part = (item as T & PlayableTimelineShape).item
  return isPlayablePartType(part?.type)
}

function supportsTypingPlayback<T extends StreamingSourceTimelineItem>(item: T): item is T & PlayableTimelineShape {
  return isPlayableTimelinePart(item) && String(item.role || '').toLowerCase() !== 'user'
}

function computeStep(backlog: number, options: { isStreaming: boolean; expedite: boolean }): number {
  const { isStreaming, expedite } = options
  if (backlog <= 0) return 0

  let step = 2
  if (backlog > 24) step = 4
  if (backlog > 72) step = 8
  if (backlog > 180) step = 16
  if (backlog > 420) step = 28
  if (expedite) step = Math.max(step, 24)
  if (!isStreaming) {
    step = Math.max(step, 36, Math.ceil(backlog / 2))
  }
  return step
}

export function useStreamingPresentation<T extends StreamingSourceTimelineItem>(source: Readonly<Ref<T[]>>) {
  const playbackStateById = ref<Record<string, PlaybackState>>({})
  let playbackTimer: number | null = null
  const latestStreamingPartId = ref('')
  const hasHydratedInitialSnapshot = ref(false)

  const stopPlayback = () => {
    if (playbackTimer !== null) {
      window.clearInterval(playbackTimer)
      playbackTimer = null
    }
  }

  const hasPendingPlaybackNow = () => {
    return Object.values(playbackStateById.value).some((state) => state.displayedLength < state.targetText.length)
  }

  const tickPlayback = () => {
    let changed = false
    for (const state of Object.values(playbackStateById.value)) {
      const backlog = state.targetText.length - state.displayedLength
      if (backlog <= 0) continue
      const step = computeStep(backlog, {
        isStreaming: state.isStreaming,
        expedite: state.expedite
      })
      if (step <= 0) continue
      state.displayedLength = Math.min(state.targetText.length, state.displayedLength + step)
      changed = true
    }
    if (!changed || !hasPendingPlaybackNow()) {
      stopPlayback()
    }
  }

  const ensurePlayback = () => {
    if (!hasPendingPlaybackNow() || playbackTimer !== null) return
    playbackTimer = window.setInterval(() => {
      tickPlayback()
    }, NORMAL_TICK_MS)
  }

  const syncPlaybackState = (items: T[]) => {
    const isInitialSnapshot = !hasHydratedInitialSnapshot.value
    const nextPlayableIds = new Set<string>()
    const playablePartIdsInOrder: string[] = []

    for (const item of items) {
      if (!isPlayableTimelinePart(item)) {
        continue
      }

      const itemId = String(item.id || '')
      if (!itemId) continue
      nextPlayableIds.add(itemId)
      playablePartIdsInOrder.push(itemId)

      const targetText = String(item.item.text || '')
      const isStreaming = Boolean(item.item.isStreaming)
      const supportsTyping = supportsTypingPlayback(item)
      const existing = playbackStateById.value[itemId]

      if (!existing) {
        playbackStateById.value[itemId] = {
          displayedLength: supportsTyping && isStreaming && !isInitialSnapshot ? 0 : targetText.length,
          targetText,
          isStreaming,
          expedite: false,
          supportsTyping
        }
        continue
      }

      existing.targetText = targetText
      existing.isStreaming = isStreaming
      existing.supportsTyping = supportsTyping

      if (isInitialSnapshot || !supportsTyping) {
        existing.displayedLength = targetText.length
        existing.expedite = false
        continue
      }

      if (existing.displayedLength > targetText.length) {
        existing.displayedLength = targetText.length
      }
      if (!isStreaming && existing.displayedLength < targetText.length) {
        existing.expedite = true
      }
    }

    latestStreamingPartId.value = ''
    for (let i = playablePartIdsInOrder.length - 1; i >= 0; i -= 1) {
      const itemId = playablePartIdsInOrder[i]
      const state = playbackStateById.value[itemId]
      if (state?.isStreaming && state.supportsTyping) {
        latestStreamingPartId.value = itemId
        break
      }
    }

    for (const itemId of playablePartIdsInOrder) {
      const state = playbackStateById.value[itemId]
      if (!state) continue
      if (!state.supportsTyping) {
        state.expedite = false
        state.displayedLength = state.targetText.length
        continue
      }
      const hasBacklog = state.displayedLength < state.targetText.length
      state.expedite = hasBacklog && latestStreamingPartId.value !== '' && itemId !== latestStreamingPartId.value
    }

    for (const itemId of Object.keys(playbackStateById.value)) {
      if (nextPlayableIds.has(itemId)) continue
      delete playbackStateById.value[itemId]
    }

    ensurePlayback()
    hasHydratedInitialSnapshot.value = true
  }

  const presentedTimelineItems = computed<T[]>(() => {
    return source.value.map((item) => {
      if (!isPlayableTimelinePart(item)) {
        return item
      }
      const state = playbackStateById.value[item.id]
      if (!state) {
        return item
      }
      const presentedText = state.targetText.slice(0, state.displayedLength)
      return {
        ...item,
        item: {
          ...item.item,
          text: presentedText,
          isStreaming: Boolean(item.item.isStreaming) || state.displayedLength < state.targetText.length
        }
      } as T
    })
  })

  watch(
    source,
    (items) => {
      syncPlaybackState(items)
    },
    { deep: true, immediate: true }
  )

  onUnmounted(() => {
    stopPlayback()
  })

  return {
    presentedTimelineItems,
    hasPendingPlayback: computed(() => hasPendingPlaybackNow()),
    latestStreamingPartId: computed(() => latestStreamingPartId.value)
  }
}
