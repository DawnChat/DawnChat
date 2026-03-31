<template>
  <div ref="rootRef" class="inline-select" :class="{ open: isOpen, disabled }">
    <button
      ref="triggerRef"
      class="inline-select-trigger"
      type="button"
      :disabled="disabled"
      :title="selectedTitle"
      :aria-label="label"
      :aria-expanded="isOpen ? 'true' : 'false'"
      :aria-controls="isOpen ? menuId : undefined"
      :aria-activedescendant="isOpen && activeIndex >= 0 ? getOptionId(activeIndex) : undefined"
      aria-haspopup="listbox"
      @click="toggleOpen"
      @keydown="handleTriggerKeydown"
    >
      <span class="inline-select-value">
        <span
          v-if="selectedStatus"
          class="inline-select-status-dot"
          :class="`is-${selectedStatus}`"
          :title="selectedStatusTitle || selectedTitle"
          aria-hidden="true"
        />
        <span class="inline-select-label">{{ selectedLabel }}</span>
      </span>
      <svg class="inline-select-arrow" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M5.5 7.5 10 12l4.5-4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
  </div>
  <Teleport to="body">
    <div
      v-if="isOpen"
      :id="menuId"
      ref="menuRef"
      class="inline-select-menu"
      role="listbox"
      :style="menuStyle"
      :aria-label="label"
    >
      <button
        v-for="(option, index) in options"
        :id="getOptionId(index)"
        :key="option.value"
        class="inline-select-option"
        :class="{
          selected: option.value === modelValue,
          active: index === activeIndex
        }"
        type="button"
        role="option"
        :title="option.title || option.label"
        :aria-selected="option.value === modelValue ? 'true' : 'false'"
        @click="handleSelect(option.value)"
        @mouseenter="activeIndex = index"
      >
        <span class="inline-select-option-main">
          <span class="inline-select-option-header">
            <span
              v-if="selectedStatus && option.value === modelValue"
              class="inline-select-status-dot"
              :class="`is-${selectedStatus}`"
              :title="selectedStatusTitle || selectedTitle"
              aria-hidden="true"
            />
            <span class="inline-select-option-label">{{ option.label }}</span>
          </span>
          <span v-if="option.description" class="inline-select-option-description">{{ option.description }}</span>
        </span>
        <span class="inline-select-option-meta">
          <svg v-if="option.value === modelValue" class="inline-select-check" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="m5.5 10 3 3 6-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
      </button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

export interface PluginDevInlineSelectOption {
  value: string
  label: string
  title?: string
  description?: string
}

const props = withDefaults(defineProps<{
  modelValue: string
  options: PluginDevInlineSelectOption[]
  label: string
  placeholder?: string
  disabled?: boolean
  selectedStatus?: 'checking' | 'healthy' | 'unhealthy' | null
  selectedStatusTitle?: string
}>(), {
  placeholder: '',
  disabled: false,
  selectedStatus: null,
  selectedStatusTitle: ''
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
}>()

const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLElement | null>(null)
const menuRef = ref<HTMLElement | null>(null)
const isOpen = ref(false)
const activeIndex = ref(-1)
const menuStyle = ref<Record<string, string>>({})
const menuId = `plugin-dev-inline-select-${Math.random().toString(36).slice(2, 10)}`

const selectedOption = computed(() => {
  return props.options.find((option) => option.value === props.modelValue) || null
})

const selectedLabel = computed(() => {
  return selectedOption.value?.label || props.placeholder || ''
})

const selectedTitle = computed(() => {
  return props.selectedStatusTitle || selectedOption.value?.title || selectedOption.value?.label || props.label
})

const syncActiveIndex = () => {
  if (props.options.length === 0) {
    activeIndex.value = -1
    return
  }
  const selectedIndex = props.options.findIndex((option) => option.value === props.modelValue)
  activeIndex.value = selectedIndex >= 0 ? selectedIndex : 0
}

const close = () => {
  isOpen.value = false
}

const open = () => {
  if (props.disabled || props.options.length === 0) return
  syncActiveIndex()
  isOpen.value = true
  void nextTick(() => {
    updateMenuPosition()
    scrollActiveOptionIntoView()
  })
}

const toggleOpen = () => {
  if (isOpen.value) {
    close()
    return
  }
  open()
}

const handleSelect = (value: string) => {
  if (!props.options.some((option) => option.value === value)) {
    close()
    return
  }
  if (value !== props.modelValue) {
    emit('update:modelValue', value)
    emit('change', value)
  }
  close()
}

const moveActive = (step: number) => {
  if (!isOpen.value) {
    open()
    return
  }
  const nextIndex = activeIndex.value + step
  const optionCount = props.options.length
  if (optionCount === 0) return
  activeIndex.value = (nextIndex + optionCount) % optionCount
  void nextTick(() => scrollActiveOptionIntoView())
}

const handleTriggerKeydown = (event: KeyboardEvent) => {
  if (props.disabled) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    moveActive(1)
    return
  }
  if (event.key === 'ArrowUp') {
    event.preventDefault()
    moveActive(-1)
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (!isOpen.value) {
      open()
      return
    }
    const option = props.options[activeIndex.value]
    if (option) {
      handleSelect(option.value)
    }
    return
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  if (event.key === 'Home') {
    event.preventDefault()
    if (!isOpen.value) open()
    activeIndex.value = 0
    void nextTick(() => scrollActiveOptionIntoView())
    return
  }
  if (event.key === 'End') {
    event.preventDefault()
    if (!isOpen.value) open()
    activeIndex.value = Math.max(0, props.options.length - 1)
    void nextTick(() => scrollActiveOptionIntoView())
  }
}

const handlePointerDown = (event: PointerEvent) => {
  const root = rootRef.value
  const menu = menuRef.value
  const target = event.target as Node
  if (!root) return
  if (root.contains(target)) return
  if (menu?.contains(target)) return
  close()
}

const handleWindowBlur = () => {
  close()
}

const updateMenuPosition = () => {
  const trigger = triggerRef.value
  const menu = menuRef.value
  if (!trigger) return
  const rect = trigger.getBoundingClientRect()
  const gap = 1
  const viewportPadding = 8
  const preferredHeight = 320
  const estimatedContentHeight = Math.min(preferredHeight, props.options.length * 44 + 12)

  let measuredNaturalHeight = 0
  if (menu) {
    const prevMaxHeight = menu.style.maxHeight
    const prevOverflowY = menu.style.overflowY
    menu.style.maxHeight = 'none'
    menu.style.overflowY = 'visible'
    measuredNaturalHeight = menu.scrollHeight
    menu.style.maxHeight = prevMaxHeight
    menu.style.overflowY = prevOverflowY
  }

  const contentHeight = Math.max(measuredNaturalHeight, estimatedContentHeight)
  const desiredHeight = Math.min(preferredHeight, contentHeight)
  const spaceBelow = window.innerHeight - rect.bottom - viewportPadding - gap
  const spaceAbove = rect.top - viewportPadding - gap
  const placeUpward = spaceBelow < desiredHeight && spaceAbove > spaceBelow
  const availableHeight = Math.max(0, placeUpward ? spaceAbove : spaceBelow)
  const maxHeight = Math.max(0, Math.min(desiredHeight, availableHeight))
  const top = placeUpward
    ? Math.max(viewportPadding, rect.top - maxHeight - gap)
    : Math.min(window.innerHeight - viewportPadding - maxHeight, rect.bottom + gap)

  menuStyle.value = {
    position: 'fixed',
    top: `${Math.max(viewportPadding, top)}px`,
    left: `${Math.max(viewportPadding, rect.left)}px`,
    width: `${rect.width}px`,
    maxHeight: `${maxHeight}px`,
    overflowY: 'auto',
    zIndex: '1300',
  }
}

const scrollActiveOptionIntoView = () => {
  const menu = menuRef.value
  if (!menu || activeIndex.value < 0) return
  const activeEl = menu.querySelectorAll<HTMLElement>('.inline-select-option').item(activeIndex.value)
  activeEl?.scrollIntoView({ block: 'nearest' })
}

const handleWindowLayoutChange = () => {
  if (!isOpen.value) return
  updateMenuPosition()
}

watch(
  () => props.modelValue,
  () => {
    syncActiveIndex()
  },
  { immediate: true }
)

watch(
  () => props.options,
  () => {
    syncActiveIndex()
    if (props.options.length === 0) {
      close()
      return
    }
    if (isOpen.value) {
      void nextTick(() => {
        updateMenuPosition()
        scrollActiveOptionIntoView()
      })
    }
  },
  { deep: true }
)

watch(isOpen, (openNow) => {
  if (openNow) {
    window.addEventListener('resize', handleWindowLayoutChange)
    window.addEventListener('scroll', handleWindowLayoutChange, true)
    return
  }
  window.removeEventListener('resize', handleWindowLayoutChange)
  window.removeEventListener('scroll', handleWindowLayoutChange, true)
})

onMounted(() => {
  window.addEventListener('pointerdown', handlePointerDown)
  window.addEventListener('blur', handleWindowBlur)
})

onUnmounted(() => {
  window.removeEventListener('pointerdown', handlePointerDown)
  window.removeEventListener('blur', handleWindowBlur)
  window.removeEventListener('resize', handleWindowLayoutChange)
  window.removeEventListener('scroll', handleWindowLayoutChange, true)
})

const getOptionId = (index: number) => `${props.label.replace(/\s+/g, '-').toLowerCase()}-${index}`
</script>

<style scoped>
.inline-select {
  position: relative;
  min-width: 0;
}

.inline-select.disabled {
  opacity: 0.56;
}

.inline-select-trigger {
  width: 100%;
  min-width: 0;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  border: 1px solid color-mix(in srgb, var(--color-border-strong) 72%, transparent);
  border-radius: 10px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--color-surface-3) 88%, white 4%), color-mix(in srgb, var(--color-surface-2) 94%, black 2%));
  color: var(--color-text);
  padding: 0 0.7rem;
  box-shadow:
    inset 0 1px 0 color-mix(in srgb, white 10%, transparent),
    0 6px 18px rgba(0, 0, 0, 0.12);
  cursor: pointer;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, background 0.16s ease, transform 0.16s ease;
}

.inline-select-trigger:hover,
.inline-select.open .inline-select-trigger {
  border-color: color-mix(in srgb, var(--color-primary) 42%, var(--color-border-strong));
  box-shadow:
    inset 0 1px 0 color-mix(in srgb, white 12%, transparent),
    0 0 0 1px color-mix(in srgb, var(--color-primary) 10%, transparent),
    0 10px 24px rgba(0, 0, 0, 0.16);
}

.inline-select-trigger:focus-visible {
  outline: none;
  border-color: color-mix(in srgb, var(--color-primary) 58%, var(--color-border-strong));
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--color-primary) 22%, transparent),
    0 10px 24px rgba(0, 0, 0, 0.16);
}

.inline-select-trigger:disabled {
  cursor: not-allowed;
}

.inline-select-value {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.42rem;
}

.inline-select-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.82rem;
  font-weight: 500;
  letter-spacing: 0.01em;
}

.inline-select-arrow {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
  color: var(--color-text-secondary);
  transition: transform 0.16s ease, color 0.16s ease;
}

.inline-select.open .inline-select-arrow {
  transform: rotate(180deg);
  color: var(--color-text);
}

.inline-select-menu {
  padding: 0.38rem;
  border: 1px solid color-mix(in srgb, var(--color-border-strong) 82%, transparent);
  border-radius: 12px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--color-surface-3) 96%, white 4%), color-mix(in srgb, var(--color-surface-2) 98%, black 2%));
  box-shadow:
    inset 0 1px 0 color-mix(in srgb, white 8%, transparent),
    0 18px 42px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(16px);
}

.inline-select-option {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--color-text);
  padding: 0.55rem 0.62rem;
  text-align: left;
  cursor: pointer;
  transition: background 0.14s ease, color 0.14s ease, transform 0.14s ease;
}

.inline-select-option:hover,
.inline-select-option.active {
  background: color-mix(in srgb, var(--color-primary) 11%, var(--color-surface-3));
}

.inline-select-option.selected {
  background: color-mix(in srgb, var(--color-primary) 16%, var(--color-surface-3));
}

.inline-select-option-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.14rem;
}

.inline-select-option-header {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.42rem;
}

.inline-select-option-label {
  font-size: 0.82rem;
  font-weight: 500;
  line-height: 1.2;
}

.inline-select-option-description {
  font-size: 0.72rem;
  line-height: 1.25;
  color: var(--color-text-secondary);
}

.inline-select-option-meta {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 0.38rem;
  color: var(--color-primary);
}

.inline-select-check {
  width: 14px;
  height: 14px;
}

.inline-select-status-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-text-secondary) 88%, transparent);
  box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 14%, transparent);
}

.inline-select-status-dot.is-healthy {
  background: #22c55e;
  color: #22c55e;
}

.inline-select-status-dot.is-unhealthy {
  background: #ef4444;
  color: #ef4444;
}

.inline-select-status-dot.is-checking {
  background: #f59e0b;
  color: #f59e0b;
  animation: select-status-pulse 1.15s ease-in-out infinite;
}

@keyframes select-status-pulse {
  0%,
  100% {
    opacity: 0.7;
    transform: scale(0.92);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
