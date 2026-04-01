import { computed, onMounted, ref, watch } from 'vue'
import type { WorkbenchLayoutProfile } from '@/features/plugin-dev-workbench/services/workbenchLayoutProfile'
import { getWorkbenchLayoutProfile } from '@/features/plugin-dev-workbench/services/workbenchLayoutProfile'
import type { WorkbenchLayoutVariant } from '@/features/plugin-dev-workbench/services/workbenchLayoutVariant'

const LAYOUT_STORAGE_KEY = 'plugin-dev-workbench.layout.v1'
const DEFAULT_PREVIEW_WIDTH = 460
const DEFAULT_AGENT_LOG_HEIGHT = 188
const MIN_PREVIEW_WIDTH = 360
const MAX_PREVIEW_WIDTH = 900
const AGENT_PREVIEW_RESIZER_WIDTH = 8
const MIN_AGENT_LOG_HEIGHT = 120
const MAX_AGENT_LOG_HEIGHT = 420
const MIN_PREVIEW_CONTENT_WIDTH = 520

interface StoredLayoutState {
  previewWidthPx?: number
  agentLogHeightPx?: number
}

interface UseWorkbenchLayoutStateOptions {
  profile?: WorkbenchLayoutProfile | { value: WorkbenchLayoutProfile }
  layoutVariant?: WorkbenchLayoutVariant | { value: WorkbenchLayoutVariant }
}

const clamp = (value: number, min: number, max: number) => {
  return Math.min(Math.max(value, min), max)
}

const resolveAgentPreviewMaxWidth = (containerWidth: number) => {
  const usable = Math.max(containerWidth - AGENT_PREVIEW_RESIZER_WIDTH, MIN_PREVIEW_WIDTH * 2)
  return Math.max(MIN_PREVIEW_WIDTH, Math.floor(usable / 2))
}

export const useWorkbenchLayoutState = (options: UseWorkbenchLayoutStateOptions = {}) => {
  const previewWidthPx = ref(DEFAULT_PREVIEW_WIDTH)
  const agentLogHeightPx = ref(DEFAULT_AGENT_LOG_HEIGHT)
  const isResizingPreview = ref(false)
  const isResizingAgentLog = ref(false)

  const resolveProfile = () => {
    const value = options.profile
    if (!value) return getWorkbenchLayoutProfile('default')
    if ('layout' in value) return value
    return value.value
  }

  const resolveLayoutVariant = (): WorkbenchLayoutVariant => {
    const value = options.layoutVariant
    if (!value) return 'split_with_iwp'
    if (typeof value === 'string') return value
    return value.value
  }

  const applyAgentPreviewPreset = () => {
    const max = resolveAgentPreviewMaxWidth(window.innerWidth)
    previewWidthPx.value = clamp(DEFAULT_PREVIEW_WIDTH, MIN_PREVIEW_WIDTH, max)
  }

  const applySplitNoIwpPreset = () => {
    const containerWidth = window.innerWidth
    const max = Math.max(
      MIN_PREVIEW_WIDTH,
      containerWidth - AGENT_PREVIEW_RESIZER_WIDTH - MIN_PREVIEW_CONTENT_WIDTH
    )
    previewWidthPx.value = clamp(DEFAULT_PREVIEW_WIDTH, MIN_PREVIEW_WIDTH, max)
  }

  const persistState = () => {
    if (typeof window === 'undefined') return
    if (resolveProfile().lockLayoutPersistence) return
    const payload: StoredLayoutState = {
      previewWidthPx: previewWidthPx.value,
      agentLogHeightPx: agentLogHeightPx.value,
    }
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(payload))
  }

  const restoreState = () => {
    if (typeof window === 'undefined') return
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw) as StoredLayoutState
      if (typeof parsed.previewWidthPx === 'number') {
        previewWidthPx.value = clamp(parsed.previewWidthPx, MIN_PREVIEW_WIDTH, MAX_PREVIEW_WIDTH)
      }
      if (typeof parsed.agentLogHeightPx === 'number') {
        agentLogHeightPx.value = clamp(parsed.agentLogHeightPx, MIN_AGENT_LOG_HEIGHT, MAX_AGENT_LOG_HEIGHT)
      }
    } catch {
      localStorage.removeItem(LAYOUT_STORAGE_KEY)
    }
  }

  const startResizePreview = (event: PointerEvent) => {
    if (typeof window === 'undefined') return
    event.preventDefault()
    isResizingPreview.value = true
    const previousUserSelect = document.body.style.userSelect
    document.body.style.userSelect = 'none'

    const parentRect = (event.currentTarget as HTMLElement | null)?.parentElement?.getBoundingClientRect()

    const onMove = (moveEvent: PointerEvent) => {
      const layoutVariant = resolveLayoutVariant()
      const useAgentWidthResize = layoutVariant === 'split_no_iwp' || resolveProfile().previewResizeMode === 'agent_width_capped'
      if (useAgentWidthResize) {
        const containerWidth = parentRect?.width || window.innerWidth
        const max = layoutVariant === 'split_no_iwp'
          ? Math.max(MIN_PREVIEW_WIDTH, containerWidth - AGENT_PREVIEW_RESIZER_WIDTH - MIN_PREVIEW_CONTENT_WIDTH)
          : resolveAgentPreviewMaxWidth(containerWidth)
        const next = parentRect ? (moveEvent.clientX - parentRect.left) : moveEvent.clientX
        previewWidthPx.value = clamp(next, MIN_PREVIEW_WIDTH, max)
        return
      }
      const next = parentRect ? (parentRect.right - moveEvent.clientX) : (window.innerWidth - moveEvent.clientX)
      previewWidthPx.value = clamp(next, MIN_PREVIEW_WIDTH, MAX_PREVIEW_WIDTH)
    }

    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      isResizingPreview.value = false
      document.body.style.userSelect = previousUserSelect
      persistState()
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  const startResizeAgentLog = (event: PointerEvent) => {
    if (typeof window === 'undefined') return
    event.preventDefault()
    isResizingAgentLog.value = true
    const startY = event.clientY
    const startHeight = agentLogHeightPx.value
    const previousUserSelect = document.body.style.userSelect
    document.body.style.userSelect = 'none'

    const onMove = (moveEvent: PointerEvent) => {
      const delta = startY - moveEvent.clientY
      agentLogHeightPx.value = clamp(startHeight + delta, MIN_AGENT_LOG_HEIGHT, MAX_AGENT_LOG_HEIGHT)
    }

    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      isResizingAgentLog.value = false
      document.body.style.userSelect = previousUserSelect
      persistState()
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }

  onMounted(() => {
    const profile = resolveProfile()
    const layoutVariant = resolveLayoutVariant()
    if (layoutVariant === 'split_no_iwp') {
      applySplitNoIwpPreset()
      return
    }
    if (profile.lockLayoutPersistence) {
      applyAgentPreviewPreset()
      return
    }
    restoreState()
  })

  const layoutPresetKey = computed(() => `${resolveProfile().layout}:${resolveLayoutVariant()}`)
  watch(layoutPresetKey, (next, prev) => {
    if (!prev || next === prev || typeof window === 'undefined') return
    const layoutVariant = resolveLayoutVariant()
    const profile = resolveProfile()
    if (layoutVariant === 'split_no_iwp') {
      applySplitNoIwpPreset()
      return
    }
    if (profile.lockLayoutPersistence) {
      applyAgentPreviewPreset()
      return
    }
    restoreState()
  })

  return {
    previewWidthPx,
    agentLogHeightPx,
    isResizingPreview,
    isResizingAgentLog,
    startResizePreview,
    startResizeAgentLog,
    persistState,
  }
}
