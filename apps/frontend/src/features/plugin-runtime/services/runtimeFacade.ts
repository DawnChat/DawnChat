import { storeToRefs } from 'pinia'
import type { Ref } from 'vue'
import { usePluginStore } from '@/features/plugin/store'
import type { Plugin, PluginRunMode } from '@/features/plugin/types'

export interface RuntimeFacade {
  activeApp: Ref<Plugin | null>
  activeMode: Ref<PluginRunMode>
  installedApps: Ref<Plugin[]>
  loadApps: (silent?: boolean) => Promise<void>
  openApp: (app: Plugin, mode: PluginRunMode) => void
  closeApp: () => void
  startPreview: (pluginId: string) => Promise<boolean>
  startAppWithMode: (pluginId: string, mode: PluginRunMode) => Promise<boolean>
  stopPreview: (pluginId: string) => Promise<boolean>
  stopApp: (pluginId: string) => Promise<void>
}

export const useRuntimeFacade = (): RuntimeFacade => {
  const pluginStore = usePluginStore()
  const { activeApp, activeMode, installedApps } = storeToRefs(pluginStore)

  return {
    activeApp,
    activeMode,
    installedApps,
    loadApps: pluginStore.loadApps,
    openApp: pluginStore.openApp,
    closeApp: pluginStore.closeApp,
    startPreview: pluginStore.startPreview,
    startAppWithMode: pluginStore.startAppWithMode,
    stopPreview: pluginStore.stopPreview,
    stopApp: pluginStore.stopApp,
  }
}
