import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { usePluginStore } from '@/features/plugin/store'
import type { Plugin } from '@/features/plugin/types'
import { openPluginDevWorkbench } from '@/app/router/navigation'
import { APPS_HUB_PATH } from '@/app/router/paths'
import { useBuildHubLifecycleFacade } from '@/features/plugin/services/buildHubLifecycleFacade'

const parseTime = (value: string | undefined): number => {
  if (!value) return 0
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : 0
}

export function useRecentDevSession() {
  const router = useRouter()
  const pluginStore = usePluginStore()
  const lifecycleFacade = useBuildHubLifecycleFacade()
  const { installedApps, activeLifecycleTask, buildHubRecentPluginId } = storeToRefs(pluginStore)
  const resuming = ref(false)

  const sortedInstalledApps = computed(() => {
    return [...installedApps.value].sort((a, b) => parseTime(b.created_at) - parseTime(a.created_at))
  })

  const findInstalledById = (pluginId: string): Plugin | null => {
    const found = installedApps.value.find((app) => app.id === pluginId)
    return found || null
  }

  const resolveResumeTarget = (): Plugin | null => {
    const pendingTaskPluginId = String(activeLifecycleTask.value?.plugin_id || '')
    if (pendingTaskPluginId) {
      const pendingTarget = findInstalledById(pendingTaskPluginId)
      if (pendingTarget) return pendingTarget
    }

    const rememberedId = String(buildHubRecentPluginId.value || '')
    if (rememberedId) {
      const rememberedTarget = findInstalledById(rememberedId)
      if (rememberedTarget) return rememberedTarget
    }

    return sortedInstalledApps.value[0] || null
  }

  const openTargetWorkbench = async (target: Plugin) => {
    pluginStore.openApp(target, 'preview')
    pluginStore.rememberBuildHubRecentSession(target.id)
    if (target.preview?.state === 'running' && target.preview?.url) {
      await openPluginDevWorkbench(router, target.id, APPS_HUB_PATH)
      return
    }
    await lifecycleFacade.startDevSession(target.id)
  }

  const resumeRecentSession = async (): Promise<boolean> => {
    if (resuming.value) return false
    resuming.value = true
    try {
      pluginStore.hydrateBuildHubRecentSession()
      await pluginStore.loadApps(true)
      const target = resolveResumeTarget()
      if (!target) return false
      await openTargetWorkbench(target)
      return true
    } finally {
      resuming.value = false
    }
  }

  return {
    resuming,
    resolveResumeTarget,
    resumeRecentSession,
  }
}
