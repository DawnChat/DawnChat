import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import type { BackendStatus } from '@/composables/useBackendStatus'

/** Wall-clock expectation for Python backend to become reachable (UX hint). */
export const EXPECTED_BOOT_MS = 10_000
const CAP_BEFORE_READY = 95
const IDLE_CAP = 98

const easeOutQuad = (t: number) => 1 - (1 - t) * (1 - t)

/** Exposed for unit tests — maps elapsed ms to 0–98% before ready. */
export function computeStartupTargetForElapsed(elapsedMs: number): number {
  if (elapsedMs <= 0) return 0
  if (elapsedMs <= EXPECTED_BOOT_MS) {
    const t = elapsedMs / EXPECTED_BOOT_MS
    return Math.min(CAP_BEFORE_READY, easeOutQuad(t) * CAP_BEFORE_READY)
  }
  const idleElapsed = elapsedMs - EXPECTED_BOOT_MS
  const idle = Math.min(3, (idleElapsed / 30_000) * 3)
  return Math.min(IDLE_CAP, CAP_BEFORE_READY + idle)
}

export function useBackendStartupProgress(status: Ref<BackendStatus>) {
  const startTime = ref(performance.now())
  const displayed = ref(0)
  let lastFrameTs = 0
  let rafId: number | null = null

  const resetForRestart = () => {
    startTime.value = performance.now()
    lastFrameTs = 0
    displayed.value = 0
  }

  watch(
    () => status.value.phase,
    (phase) => {
      if (phase === 'backend_restarting') {
        resetForRestart()
      }
    }
  )

  const computeTarget = (): number => {
    if (status.value.error) return 0
    if (status.value.isReady) return 100
    const elapsed = performance.now() - startTime.value
    return computeStartupTargetForElapsed(elapsed)
  }

  const tick = (now: number) => {
    if (!lastFrameTs) {
      lastFrameTs = now
    }
    const dt = Math.min(48, Math.max(8, now - lastFrameTs))
    lastFrameTs = now

    const target = computeTarget()
    const delta = target - displayed.value
    const speed = status.value.isReady ? 400 : 110
    if (Math.abs(delta) < 0.05) {
      displayed.value = target
    } else {
      const step = Math.sign(delta) * Math.min(Math.abs(delta), speed * (dt / 1000))
      displayed.value += step
    }
    displayed.value = Math.max(0, Math.min(100, displayed.value))

    rafId = requestAnimationFrame(tick)
  }

  onMounted(() => {
    startTime.value = performance.now()
    lastFrameTs = 0
    displayed.value = 0
    rafId = requestAnimationFrame(tick)
  })

  onBeforeUnmount(() => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  })

  const progressPercent = computed(() => displayed.value)
  const progressLabel = computed(() => `${Math.round(displayed.value)}%`)

  return { progressPercent, progressLabel }
}
