import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import type { LifecycleTask } from '@/stores/plugin/types'

interface UseLifecycleProgressSmoothingOptions {
  visible: Ref<boolean>
  taskId: Ref<string>
  rawProgress: Ref<number>
  taskStatus: Ref<LifecycleTask['status']>
}

const clampProgress = (value: number) => Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0))

const idleCap = (raw: number) => {
  if (raw >= 95) return 99
  if (raw >= 82) return 97
  if (raw >= 65) return 95
  if (raw >= 40) return 91
  return 84
}

const idleRate = (raw: number) => {
  if (raw >= 90) return 0.28
  if (raw >= 75) return 0.5
  if (raw >= 60) return 0.85
  return 1.25
}

export function useLifecycleProgressSmoothing(options: UseLifecycleProgressSmoothingOptions) {
  const smoothedProgress = ref(clampProgress(options.rawProgress.value))
  const optimisticProgress = ref(clampProgress(options.rawProgress.value))
  const stagnantMs = ref(0)
  const lastRawProgress = ref(clampProgress(options.rawProgress.value))
  const lastTimestamp = ref(0)
  const rafId = ref<number | null>(null)
  const activeTaskId = ref(options.taskId.value)

  const stopLoop = () => {
    if (rafId.value !== null) {
      cancelAnimationFrame(rafId.value)
      rafId.value = null
    }
  }

  const resetProgressState = () => {
    const raw = clampProgress(options.rawProgress.value)
    smoothedProgress.value = raw
    optimisticProgress.value = raw
    lastRawProgress.value = raw
    stagnantMs.value = 0
    lastTimestamp.value = 0
  }

  const computeTarget = (deltaMs: number) => {
    const raw = clampProgress(options.rawProgress.value)
    const status = options.taskStatus.value
    const isTerminal = status === 'completed' || status === 'failed' || status === 'cancelled'
    const isRunning = status === 'running' || status === 'pending'

    if (raw > lastRawProgress.value) {
      lastRawProgress.value = raw
      stagnantMs.value = 0
      optimisticProgress.value = Math.max(optimisticProgress.value, raw)
    } else if (isRunning) {
      stagnantMs.value += deltaMs
    }

    if (status === 'completed' || raw >= 100) {
      optimisticProgress.value = 100
      return 100
    }

    if (!isRunning || isTerminal) {
      optimisticProgress.value = Math.max(optimisticProgress.value, raw)
      return Math.max(raw, Math.min(optimisticProgress.value, 99))
    }

    if (stagnantMs.value >= 700) {
      const cap = idleCap(raw)
      const next = optimisticProgress.value + idleRate(raw) * (deltaMs / 1000)
      optimisticProgress.value = Math.min(cap, Math.max(raw, next))
    } else {
      optimisticProgress.value = Math.max(optimisticProgress.value, raw)
    }

    return Math.min(99, Math.max(raw, optimisticProgress.value))
  }

  const animateFrame = (timestamp: number) => {
    if (!options.visible.value) {
      stopLoop()
      return
    }

    if (!lastTimestamp.value) {
      lastTimestamp.value = timestamp
    }

    const deltaMs = Math.min(48, Math.max(8, timestamp - lastTimestamp.value))
    lastTimestamp.value = timestamp

    const target = computeTarget(deltaMs)
    const delta = target - smoothedProgress.value

    if (delta > 0) {
      const status = options.taskStatus.value
      const baseSpeed = status === 'completed' || target >= 100 ? 260 : 20
      const followSpeed = baseSpeed + Math.max(0, delta) * 7
      const next = smoothedProgress.value + followSpeed * (deltaMs / 1000)
      smoothedProgress.value = Math.min(target, next)
    } else if (delta < 0) {
      smoothedProgress.value = target
    }

    if (smoothedProgress.value >= 99.95 && target >= 100) {
      smoothedProgress.value = 100
    }

    rafId.value = requestAnimationFrame(animateFrame)
  }

  const ensureLoop = () => {
    if (!options.visible.value) {
      stopLoop()
      return
    }
    if (rafId.value !== null) return
    rafId.value = requestAnimationFrame(animateFrame)
  }

  watch(options.visible, (nextVisible) => {
    if (!nextVisible) {
      stopLoop()
      resetProgressState()
      return
    }
    ensureLoop()
  }, { immediate: true })

  watch(options.taskId, (nextTaskId) => {
    if (nextTaskId === activeTaskId.value) return
    activeTaskId.value = nextTaskId
    resetProgressState()
    ensureLoop()
  })

  watch(options.rawProgress, (nextRaw) => {
    if (clampProgress(nextRaw) >= 100) {
      optimisticProgress.value = 100
      ensureLoop()
      return
    }
    if (!options.visible.value) {
      smoothedProgress.value = clampProgress(nextRaw)
      optimisticProgress.value = clampProgress(nextRaw)
      lastRawProgress.value = clampProgress(nextRaw)
      return
    }
    ensureLoop()
  })

  watch(options.taskStatus, () => {
    ensureLoop()
  })

  onBeforeUnmount(() => {
    stopLoop()
  })

  const progressPercent = computed(() => clampProgress(smoothedProgress.value))
  const progressLabel = computed(() => `${Math.round(progressPercent.value)}%`)

  return {
    progressPercent,
    progressLabel,
  }
}
