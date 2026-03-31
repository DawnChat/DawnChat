<template>
  <div id="app" :class="{ dark: theme === 'dark' }">
    <div class="titlebar-separator"></div>

    <TheDock
      :current-space="currentSpace"
      :user="user"
      @change-space="handleSpaceChange"
      @resume-dev="handleResumeDev"
      @logout="handleLogout"
    />

    <TheNavigator v-if="showNavigator" :title="navigatorTitle">
      <KeepAlive :include="['WorkbenchNavigator']">
        <component
          v-if="currentNavigatorComponent"
          :is="currentNavigatorComponent"
          :user="user"
          :current-section="currentSection"
          :selected-room-id="selectedRoomId"
          @change-section="handleSectionChange"
          @create-app="handleCreateApp"
          @resume-dev="handleResumeDev"
          @select-room="handleRoomSelect"
          @new-project="handleNewProject"
        />
      </KeepAlive>
    </TheNavigator>

    <TheCanvas>
      <KeepAlive :include="['WorkbenchView']">
        <component
          :is="currentViewComponent"
          :user="user"
          :section="currentSection"
          :selected-room-id="selectedRoomId"
          :room-id="selectedRoomId"
          @change-section="handleSectionChange"
          @navigate-to-settings="handleNavigateToSettings"
          @back="handleProjectSettingsBack"
          @project-deleted="handleProjectDeleted"
          @room-created="handleRoomSelect"
        />
      </KeepAlive>
    </TheCanvas>
    <UnifiedLifecycleProgressModal
      :visible="lifecycleModalVisible"
      :task="activeLifecycleTask"
      @close="closeLifecycleModal"
      @cancel="handleCancelLifecycle"
      @retry="handleRetryLifecycle"
      @done="handleLifecycleDone"
    />
  </div>
</template>

<script setup lang="ts">
import { KeepAlive, computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import type { LocationQueryRaw } from 'vue-router'
import type { SpaceType } from '@/shared/types/common'
import { useI18n } from '@/composables/useI18n'
import { useTheme } from '@/composables/useTheme'
import { useAuth } from '@/shared/composables/useAuth'
import { logger } from '@/utils/logger'
import { usePluginStore } from '@/features/plugin/store'
import UnifiedLifecycleProgressModal from '@/features/plugin/components/UnifiedLifecycleProgressModal.vue'

import TheDock from './TheDock.vue'
import TheNavigator from './TheNavigator.vue'
import TheCanvas from './TheCanvas.vue'

import ProjectSettingsView from '@/views/ProjectSettingsView.vue'
import { getSpaceDefaultSection, getSpaceManifest } from '@/app/router/manifest'
import { goToSection, goToSpace } from '@/app/router/navigation'
import { APPS_HUB_PATH } from '@/app/router/paths'
import { useRecentDevSession } from '@/features/plugin/composables/useRecentDevSession'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()
const { theme } = useTheme()
const { user, logout } = useAuth()
const pluginStore = usePluginStore()
const { closeLifecycleModal, cancelLifecycleTask, retryLifecycleTaskAndHandle, finalizeActiveLifecycleTask } = pluginStore
const { activeLifecycleTask, lifecycleModalVisible } = storeToRefs(pluginStore)
const { resumeRecentSession } = useRecentDevSession()
const isLoggingOut = ref(false)

const currentSpace = computed<SpaceType>(() => {
  const space = route.meta.space
  if (typeof space === 'string') {
    return space as SpaceType
  }
  return 'workbench'
})

const currentSection = computed(() => {
  const sectionParam = route.params.section
  if (typeof sectionParam === 'string') {
    return sectionParam
  }

  const sectionMeta = route.meta.section
  if (typeof sectionMeta === 'string') {
    return sectionMeta
  }

  return getSpaceDefaultSection(currentSpace.value)
})

const selectedRoomId = computed<string | null>(() => {
  if (typeof route.params.roomId === 'string') {
    return route.params.roomId
  }
  return null
})

const isProjectSettingsMode = computed(() => Boolean(route.meta.projectSettings))

const navigatorTitle = computed(() => {
  const manifest = getSpaceManifest(currentSpace.value)
  const navKey = manifest.titleKey.replace('nav.', '')
  return t.value.nav[navKey as keyof typeof t.value.nav] || ''
})

const currentNavigatorComponent = computed(() => getSpaceManifest(currentSpace.value).navigatorComponent)
const showNavigator = computed(() => currentSpace.value !== 'apps')

const currentViewComponent = computed(() => {
  if (isProjectSettingsMode.value) {
    return ProjectSettingsView
  }
  return getSpaceManifest(currentSpace.value).viewComponent
})

const navigateToSpace = (space: SpaceType, section?: string) => {
  goToSpace(router, space, section, selectedRoomId.value)
}

const handleSpaceChange = (space: SpaceType) => {
  logger.info(`🔄 切换空间: ${currentSpace.value} -> ${space}`)
  navigateToSpace(space)
}

const handleSectionChange = (section: string) => {
  if (currentSpace.value === 'apps') {
    const normalized = String(section || 'hub')
    const nextFilter = normalized === 'hub' ? undefined : normalized
    const nextQuery: LocationQueryRaw = { ...route.query }
    if (nextFilter) {
      nextQuery.filter = nextFilter
    } else {
      delete nextQuery.filter
    }
    router.push({
      name: 'apps',
      params: { section: 'hub' },
      query: nextQuery
    })
    return
  }
  goToSection(router, currentSpace.value, section, selectedRoomId.value)
}

const handleRoomSelect = (roomId: string) => {
  logger.info('选择房间:', roomId)
  router.push({ name: 'workbench-room', params: { roomId } })
}

const handleNewProject = () => {
  logger.info('收到新建项目事件')
}

const handleCreateApp = () => {
  pluginStore.openCreateWizard()
}

const handleResumeDev = async () => {
  await resumeRecentSession()
}

const handleNavigateToSettings = (roomId: string | null) => {
  logger.info('导航到项目设置:', roomId)
  router.push({ name: 'project-settings', params: roomId ? { roomId } : {} })
}

const handleProjectSettingsBack = () => {
  logger.info('返回项目页面')
  if (selectedRoomId.value) {
    router.push({ name: 'workbench-room', params: { roomId: selectedRoomId.value } })
    return
  }
  router.push({ name: 'workbench' })
}

const handleProjectDeleted = () => {
  logger.info('项目已删除')
  router.push({ name: 'workbench' })
}

const handleLogout = async () => {
  if (isLoggingOut.value) {
    return
  }
  isLoggingOut.value = true
  try {
    if (route.name !== 'login') {
      await router.replace({ name: 'login' })
    }
    await logout()
  } finally {
    isLoggingOut.value = false
  }
}

const handleCancelLifecycle = async () => {
  await cancelLifecycleTask()
}

const handleRetryLifecycle = async () => {
  await retryLifecycleTaskAndHandle({
    from: String(route.fullPath || APPS_HUB_PATH),
    completionMessage: '启动完成，打开中...',
    uiMode: 'modal'
  })
}

const handleLifecycleDone = () => {
  finalizeActiveLifecycleTask()
}

</script>

<style scoped>
#app {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
}

.titlebar-separator {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--color-separator);
  z-index: 9999;
  pointer-events: none;
}
</style>
