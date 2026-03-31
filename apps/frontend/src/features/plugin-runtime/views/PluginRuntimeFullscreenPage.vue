<template>
  <div class="plugin-fullscreen-view">
    <ActiveAppFrame
      v-if="activeApp"
      :active-app="activeApp"
      :plugin-url="pluginUrl"
      @stop="handleStop"
    />
    <div v-else class="loading">
      <span class="spinner"></span>
      <span>{{ t.apps.starting }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ActiveAppFrame from '@/features/plugin/components/ActiveAppFrame.vue'
import { useTheme } from '@/composables/useTheme'
import { useI18n } from '@/composables/useI18n'
import { logger } from '@/utils/logger'
import { usePluginBackTarget } from '@/features/plugin-shared/navigation/usePluginBackTarget'
import { useRuntimeSessionGuard } from '@/features/plugin-runtime/composables/useRuntimeSessionGuard'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()
const { theme } = useTheme()
const { redirectToAppsInstalled } = usePluginBackTarget(route, router)

const pluginId = computed(() => String(route.params.pluginId || ''))
const runMode = computed(() => (String(route.query.mode || 'normal') === 'preview' ? 'preview' : 'normal'))

const {
  activeApp,
  activeMode,
  installedApps,
  ensurePluginRunning,
  syncActiveApp,
  stopAndExit,
  closeApp,
} = useRuntimeSessionGuard({
  pluginId,
  runMode,
  redirectToAppsInstalled,
})

const pluginUrl = computed(() => {
  const previewUrl = activeApp.value?.preview?.url || ''
  const runtimeUrl = activeApp.value?.runtime?.gradio_url || ''
  const baseUrl = runMode.value === 'preview' ? previewUrl : runtimeUrl
  if (!baseUrl) return ''
  const separator = baseUrl.includes('?') ? '&' : '?'
  return `${baseUrl}${separator}theme=${theme.value}&lang=${locale.value}`
})

const handleStop = async (appId: string) => {
  await stopAndExit(appId)
}

watch(
  () => installedApps.value,
  () => {
    syncActiveApp()
  },
  { deep: true }
)

onMounted(async () => {
  activeMode.value = runMode.value
  await ensurePluginRunning()
})

onUnmounted(() => {
  logger.info('plugin_fullscreen_exit', { pluginId: pluginId.value })
  closeApp()
})
</script>

<style scoped>
.plugin-fullscreen-view {
  width: 100%;
  height: 100%;
}

.loading {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  color: var(--color-text-secondary);
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
