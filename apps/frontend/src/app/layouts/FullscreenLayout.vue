<template>
  <div class="fullscreen-layout">
    <button v-if="showCloseButton" class="close-btn" :title="t.common.back" @click="handleClose">
      <X :size="18" />
    </button>
    <RouterView />
  </div>
</template>

<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { computed } from 'vue'
import { useRouter, useRoute, RouterView } from 'vue-router'
import { useI18n } from '@/composables/useI18n'
import { resolveFullscreenBackTarget } from '@/app/router/deepLink'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const showCloseButton = computed(() => route.name !== 'plugin-dev-workbench')

const handleClose = () => {
  const target = resolveFullscreenBackTarget(route.query.from)
  router.replace(target)
}
</script>

<style scoped>
.fullscreen-layout {
  width: 100vw;
  height: 100vh;
  background: var(--color-bg);
  position: relative;
}

.close-btn {
  position: fixed;
  top: 16px;
  left: 16px;
  width: 40px;
  height: 40px;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  color: var(--color-text);
  cursor: pointer;
  z-index: 120;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  background: var(--color-hover);
}
</style>
