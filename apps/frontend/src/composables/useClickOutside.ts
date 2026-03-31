import { onMounted, onUnmounted, Ref } from 'vue'

export function useClickOutside(elementRef: Ref<HTMLElement | null>, callback: () => void) {
  const handleClick = (event: MouseEvent) => {
    if (elementRef.value && !elementRef.value.contains(event.target as Node)) {
      callback()
    }
  }

  onMounted(() => {
    document.addEventListener('click', handleClick)
  })

  onUnmounted(() => {
    document.removeEventListener('click', handleClick)
  })
}