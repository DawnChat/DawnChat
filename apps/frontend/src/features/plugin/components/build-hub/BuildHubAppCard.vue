<template>
  <article
    ref="cardRef"
    class="build-hub-card"
    :class="{ clickable: clickable }"
    @click="handleCardClick"
  >
    <div class="card-head">
      <div class="icon-wrap">
        <component v-if="icon" :is="icon" :size="18" />
      </div>
      <div class="meta">
        <h4>{{ name }}</h4>
        <p>{{ description }}</p>
      </div>
      <span class="status-chip">{{ status }}</span>
    </div>
    <div class="card-footer">
      <button
        v-if="cardType === 'market' && actionLabel"
        class="ui-btn ui-btn--neutral action-btn"
        type="button"
        :disabled="actionDisabled"
        @click.stop="$emit('action-click')"
      >
        {{ actionLabel }}
      </button>
      <div v-else />
      <div v-if="showMoreMenu" class="more-wrap">
        <button class="icon-btn ui-btn ui-btn--neutral" type="button" @click.stop="toggleMenu">
          <MoreHorizontal :size="16" />
        </button>
        <div v-if="menuOpen" class="more-menu">
          <button
            v-for="item in menuItems"
            :key="item.key"
            class="menu-item"
            :class="{ danger: item.danger }"
            type="button"
            @click.stop="handleMenuAction(item.key)"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { MoreHorizontal } from 'lucide-vue-next'

interface MenuItem {
  key: string
  label: string
  danger?: boolean
}

const props = defineProps<{
  icon?: object
  name: string
  description: string
  status: string
  cardType: 'created' | 'installed' | 'market'
  clickable?: boolean
  actionLabel?: string
  actionDisabled?: boolean
  menuItems?: MenuItem[]
}>()

const emit = defineEmits<{
  'card-click': []
  'action-click': []
  'menu-action': [key: string]
}>()

const cardRef = ref<HTMLElement | null>(null)
const menuOpen = ref(false)
const showMoreMenu = computed(() => props.cardType !== 'market' && (props.menuItems || []).length > 0)
const clickable = computed(() => props.clickable !== false)

const closeMenu = () => {
  menuOpen.value = false
}

const toggleMenu = () => {
  menuOpen.value = !menuOpen.value
}

const handleMenuAction = (key: string) => {
  emit('menu-action', key)
  closeMenu()
}

const handleCardClick = () => {
  if (!clickable.value) return
  emit('card-click')
}

const handleDocumentClick = (event: MouseEvent) => {
  if (!menuOpen.value) return
  const target = event.target as Node | null
  if (!target) return
  if (cardRef.value?.contains(target)) return
  closeMenu()
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
})
</script>

<style scoped>
.build-hub-card {
  border: 1px solid color-mix(in srgb, var(--color-border) 56%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-surface-1) 88%, var(--color-app-canvas) 12%);
  padding: 0.66rem 0.68rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-height: 122px;
  transition: border-color 0.18s ease, transform 0.18s ease, background 0.18s ease;
}

.build-hub-card.clickable {
  cursor: pointer;
}

.build-hub-card.clickable:hover {
  border-color: color-mix(in srgb, var(--color-primary) 32%, var(--color-border));
  transform: translateY(-1px);
  background: color-mix(in srgb, var(--color-surface-2) 24%, var(--color-surface-1));
}

.card-head {
  display: flex;
  align-items: flex-start;
  gap: 0.58rem;
}

.icon-wrap {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--color-surface-2) 38%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-border) 62%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.meta {
  flex: 1;
  min-width: 0;
}

.meta h4 {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.18;
  font-weight: 620;
}

.meta p {
  margin: 0.18rem 0 0;
  color: var(--color-text-secondary);
  font-size: 0.7rem;
  line-height: 1.28;
  min-height: 1.3em;
}

.status-chip {
  flex-shrink: 0;
  font-size: 0.62rem;
  font-weight: 500;
  line-height: 1;
  border-radius: 999px;
  padding: 0.14rem 0.36rem;
  border: 1px solid color-mix(in srgb, var(--color-border) 62%, transparent);
  color: var(--color-text-secondary);
  background: transparent;
}

.card-footer {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 28px;
}

.action-btn {
  min-height: 26px;
  padding: 0 0.65rem;
  font-size: 0.72rem;
  border-radius: 7px;
}

.more-wrap {
  position: relative;
}

.icon-btn {
  width: 28px;
  height: 28px;
  min-height: 28px;
  border-radius: 7px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.more-menu {
  position: absolute;
  right: 0;
  bottom: calc(100% + 0.36rem);
  z-index: 10;
  min-width: 132px;
  padding: 0.28rem;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--color-border) 88%, transparent);
  background: color-mix(in srgb, var(--color-surface-2) 92%, var(--color-app-canvas) 8%);
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.32);
  display: grid;
  gap: 0.18rem;
}

.menu-item {
  border: 1px solid transparent;
  background: transparent;
  color: var(--color-text-primary);
  border-radius: 7px;
  min-height: 28px;
  padding: 0 0.56rem;
  text-align: left;
  font-size: 0.72rem;
  cursor: pointer;
}

.menu-item:hover {
  border-color: color-mix(in srgb, var(--color-border) 86%, transparent);
  background: color-mix(in srgb, var(--color-surface-3) 74%, transparent);
}

.menu-item.danger {
  color: var(--color-button-danger-fg);
}
</style>
