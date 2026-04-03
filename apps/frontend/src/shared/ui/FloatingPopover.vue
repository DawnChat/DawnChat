<template>
  <Teleport to="body">
    <Transition name="floating-popover">
      <div
        v-if="visible"
        ref="popoverRef"
        :class="['floating-popover', panelClass, `is-${resolvedPlacement}`]"
        :style="popoverStyle"
      >
        <slot />
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  visible: boolean
  top?: number
  left?: number
  width?: number
  maxWidth?: string
  maxHeight?: string
  zIndex?: number
  placement?: 'auto' | 'top' | 'bottom'
  panelClass?: string
  surfaceMix?: number
  anchorEl?: HTMLElement | null
  offset?: number
  edgePadding?: number
}>(), {
  top: 0,
  left: 0,
  width: 360,
  maxWidth: 'min(520px, calc(100vw - 16px))',
  maxHeight: '320px',
  zIndex: 8,
  placement: 'auto',
  panelClass: '',
  surfaceMix: 92,
  anchorEl: null,
  offset: 6,
  edgePadding: 8
})

const emit = defineEmits<{
  'outside-click': [event: MouseEvent]
}>()

const popoverRef = ref<HTMLElement | null>(null)
const resolvedTop = ref(0)
const resolvedLeft = ref(0)
const resolvedWidth = ref(Math.max(180, Number(props.width || 360)))
const resolvedPlacement = ref<'top' | 'bottom'>('bottom')

const popoverStyle = computed(() => {
  const surfaceMix = Math.min(100, Math.max(70, Number(props.surfaceMix || 92)))
  return {
    top: `${resolvedTop.value}px`,
    left: `${resolvedLeft.value}px`,
    width: `${resolvedWidth.value}px`,
    maxWidth: props.maxWidth,
    maxHeight: props.maxHeight,
    zIndex: String(props.zIndex),
    '--floating-popover-surface-mix': `${surfaceMix}%`
  }
})

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

function syncLayout() {
  if (!props.visible) return
  const viewportWidth = window.innerWidth || 0
  const viewportHeight = window.innerHeight || 0
  const edgePadding = Math.max(0, Number(props.edgePadding || 8))
  const offset = Math.max(0, Number(props.offset || 6))
  const preferredWidth = Math.max(180, Number(props.width || 360))
  const width = clamp(preferredWidth, 180, Math.max(180, viewportWidth - edgePadding * 2))
  const measuredHeight = popoverRef.value?.offsetHeight || 260

  resolvedWidth.value = width

  if (!props.anchorEl) {
    resolvedPlacement.value = props.placement === 'top' ? 'top' : 'bottom'
    resolvedLeft.value = clamp(Number(props.left || 0), edgePadding, viewportWidth - width - edgePadding)
    resolvedTop.value = clamp(Number(props.top || 0), edgePadding, viewportHeight - measuredHeight - edgePadding)
    return
  }

  const anchorRect = props.anchorEl.getBoundingClientRect()
  const leftWanted = anchorRect.right - width
  const maxLeft = viewportWidth - width - edgePadding
  resolvedLeft.value = clamp(leftWanted, edgePadding, maxLeft)

  const roomBelow = viewportHeight - anchorRect.bottom
  const roomAbove = anchorRect.top
  if (props.placement === 'top') {
    resolvedPlacement.value = 'top'
  } else if (props.placement === 'bottom') {
    resolvedPlacement.value = 'bottom'
  } else {
    resolvedPlacement.value = roomBelow >= measuredHeight + offset || roomBelow >= roomAbove ? 'bottom' : 'top'
  }

  if (resolvedPlacement.value === 'bottom') {
    resolvedTop.value = clamp(anchorRect.bottom + offset, edgePadding, viewportHeight - measuredHeight - edgePadding)
  } else {
    resolvedTop.value = clamp(anchorRect.top - measuredHeight - offset, edgePadding, viewportHeight - measuredHeight - edgePadding)
  }
}

function handleWindowLayoutChange() {
  syncLayout()
}

function handlePointerDown(event: MouseEvent) {
  if (!props.visible) return
  const target = event.target as Node | null
  if (!target) return
  if (popoverRef.value?.contains(target)) return
  if (props.anchorEl?.contains(target)) return
  emit('outside-click', event)
}

watch(
  () => props.visible,
  async (visible) => {
    if (visible) {
      await nextTick()
      syncLayout()
      window.addEventListener('resize', handleWindowLayoutChange)
      window.addEventListener('scroll', handleWindowLayoutChange, true)
      document.addEventListener('mousedown', handlePointerDown, true)
      return
    }
    window.removeEventListener('resize', handleWindowLayoutChange)
    window.removeEventListener('scroll', handleWindowLayoutChange, true)
    document.removeEventListener('mousedown', handlePointerDown, true)
  }
)

watch(
  () => [props.width, props.placement, props.top, props.left, props.anchorEl],
  () => {
    if (!props.visible) return
    nextTick(() => {
      syncLayout()
    })
  }
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleWindowLayoutChange)
  window.removeEventListener('scroll', handleWindowLayoutChange, true)
  document.removeEventListener('mousedown', handlePointerDown, true)
})
</script>

<style scoped>
.floating-popover {
  position: fixed;
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  border-radius: 12px;
  background: color-mix(in srgb, var(--color-surface-2) var(--floating-popover-surface-mix, 92%), transparent);
  box-shadow:
    0 14px 30px rgba(0, 0, 0, 0.16),
    0 2px 8px rgba(0, 0, 0, 0.08);
  padding: 0.55rem 0.6rem;
  overflow: auto;
}

.floating-popover-enter-active,
.floating-popover-leave-active {
  transition: opacity 140ms ease, transform 140ms ease;
}

.floating-popover-enter-from,
.floating-popover-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}
</style>
