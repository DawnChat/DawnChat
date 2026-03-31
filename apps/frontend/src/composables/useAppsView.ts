import { type Ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { usePluginStore } from '@/features/plugin/store'
import { openPluginFullscreen } from '@/app/router/navigation'

export function useAppsView(section: Ref<string | undefined>) {
  const router = useRouter()
  const pluginStore = usePluginStore()
  const { installedApps } = storeToRefs(pluginStore)

  const openInstalledFromMarket = (appId: string) => {
    const app = installedApps.value.find(item => item.id === appId)
    if (app) {
      pluginStore.openApp(app)
      openPluginFullscreen(router, appId, '/app/apps')
    }
  }

  watch(section, (newSection) => {
    if (newSection === 'installed') {
      pluginStore.loadApps()
    }
    if (newSection === 'market') {
      pluginStore.loadMarketApps()
    }
  }, { immediate: true })

  return {
    openInstalledFromMarket
  }
}
