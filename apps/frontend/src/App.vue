<template>
  <div class="app-root" :class="{ dark: theme === 'dark' }">
    <BackendFatalView
      v-if="backendStatus.phase === 'backend_failed'"
      :status="backendStatus"
      :retry="retryBackend"
    />
    <LoadingView
      v-else-if="!backendStatus.isReady"
      :status="backendStatus"
      :retry="retryBackend"
    />
    <template v-else>
      <EnvironmentManager />
      <RouterView />
      <AppUpdateDialog
        v-if="mode"
        :visible="shouldShowDialog"
        :mode="mode"
        :latest-version="latestVersion"
        :detail="detail"
        @download="openDownload"
        @later="dismiss"
        @update:visible="handleVisibleChange"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import { useTheme } from '@/composables/useTheme'
import { useI18n } from '@/composables/useI18n'
import { useAuth } from '@/shared/composables/useAuth'
import { useBackendStatus } from '@/composables/useBackendStatus'
import EnvironmentManager from '@/features/environment/components/EnvironmentManager.vue'
import { bootstrapApp } from '@/app/bootstrap'
import AppUpdateDialog from '@/features/update/components/AppUpdateDialog.vue'
import { useAppUpdate } from '@/features/update/composables/useAppUpdate'
import LoadingView from '@/shared/ui/LoadingView.vue'
import BackendFatalView from '@/shared/ui/BackendFatalView.vue'

let cleanupBootstrap: (() => void) | null = null
const { theme, initTheme } = useTheme()
const { initI18n } = useI18n()
const { initAuthListener, loadUserFromStorage } = useAuth()
const { status: backendStatus, retry: retryBackend } = useBackendStatus()
const { shouldShowDialog, mode, latestVersion, detail, checkOnColdStart, openDownload, dismiss, handleVisibleChange } = useAppUpdate()
const router = useRouter()

onMounted(async () => {
  void checkOnColdStart()
  cleanupBootstrap = await bootstrapApp({
    router,
    initTheme,
    getTheme: () => theme.value,
    initI18n,
    initAuthListener,
    loadUserFromStorage
  })
})

onUnmounted(() => {
  if (cleanupBootstrap) {
    cleanupBootstrap()
    cleanupBootstrap = null
  }
})
</script>

<style>
.app-root {
  width: 100%;
  height: 100%;
}
</style>
