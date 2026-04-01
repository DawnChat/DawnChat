import { computed, onMounted, onUnmounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import type { LocationQueryRaw } from 'vue-router'
import type { BuildHubFilter, MarketPlugin, PluginInstallProgress } from '@/features/plugin/store/types'
import type { Plugin } from '@/features/plugin/types'
import { usePluginStore } from '@/stores/plugin'
import { useI18n } from '@/composables/useI18n'

const HUB_SECTION = 'hub'
const FILTER_QUERY_KEY = 'filter'

const normalizeFilter = (value: unknown): BuildHubFilter => {
  if (value === 'recent' || value === 'installed' || value === 'market') {
    return value
  }
  return 'all'
}

const parseCreatedTime = (value: string | undefined): number => {
  if (!value) return 0
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? timestamp : 0
}

export function useBuildHubState() {
  const route = useRoute()
  const router = useRouter()
  const pluginStore = usePluginStore()
  const { t } = useI18n()
  const { installedApps, filteredMarketApps, loading, marketLoading, buildHubFilter } =
    storeToRefs(pluginStore)

  const routeFilter = computed<BuildHubFilter>(() => {
    const queryFilter = normalizeFilter(route.query[FILTER_QUERY_KEY])
    if (queryFilter !== 'all') return queryFilter
    const legacySection = String(route.params.section || '').trim().toLowerCase()
    if (legacySection === 'installed' || legacySection === 'market') {
      return legacySection
    }
    return 'all'
  })

  const syncFilterToRoute = async (nextFilter: BuildHubFilter) => {
    const nextQuery: LocationQueryRaw = { ...route.query }
    if (nextFilter === 'all') {
      delete nextQuery[FILTER_QUERY_KEY]
    } else {
      nextQuery[FILTER_QUERY_KEY] = nextFilter
    }
    if (String(route.params.section || '') !== HUB_SECTION || String(route.query[FILTER_QUERY_KEY] || '') !== String(nextQuery[FILTER_QUERY_KEY] || '')) {
      await router.replace({
        name: 'apps',
        params: { section: HUB_SECTION },
        query: nextQuery,
      })
    }
  }

  const executionStatusLabel = (app: Plugin | MarketPlugin): string => {
    const installStatus = String(app.preview?.install_status || 'idle')
    if (installStatus === 'running') return t.value.apps.executionStatusInstalling
    if (String(app.preview?.state || '') === 'running' && app.preview?.url) return t.value.apps.executionStatusPreviewable
    if (app.app_type === 'web' || app.app_type === 'mobile') return t.value.apps.executionStatusPublishable
    return t.value.apps.executionStatusReady
  }

  const sortedInstalledApps = computed(() => {
    return [...installedApps.value].sort((a, b) => parseCreatedTime(b.created_at) - parseCreatedTime(a.created_at))
  })

  const installedMarketIds = computed(() => {
    return new Set(
      filteredMarketApps.value
        .filter((item) => item.installed)
        .map((item) => item.id)
    )
  })

  const isMarketInstalledApp = (app: Plugin) => {
    if (String(app.source_type || '').toLowerCase() === 'market') return true
    return installedMarketIds.value.has(app.id)
  }

  const createdApps = computed(() => {
    return sortedInstalledApps.value.filter((app) => !isMarketInstalledApp(app))
  })

  const installedMarketApps = computed(() => {
    return sortedInstalledApps.value.filter((app) => isMarketInstalledApp(app))
  })

  const marketApps = computed(() => filteredMarketApps.value.slice(0, 8))

  const visibleRecentApps = computed(() => {
    if (buildHubFilter.value === 'all' || buildHubFilter.value === 'recent') return createdApps.value
    return []
  })

  const visibleInstalledApps = computed(() => {
    if (buildHubFilter.value === 'all' || buildHubFilter.value === 'installed') return installedMarketApps.value
    return []
  })

  const visibleMarketApps = computed(() => {
    if (buildHubFilter.value === 'all' || buildHubFilter.value === 'market') return marketApps.value
    return []
  })

  const getInstallProgress = (appId: string): PluginInstallProgress | null => {
    return pluginStore.getInstallProgress(appId) || null
  }

  watch(
    () => routeFilter.value,
    (next) => {
      pluginStore.setBuildHubFilter(next)
    },
    { immediate: true }
  )

  onMounted(async () => {
    pluginStore.hydrateBuildHubRecentSession()
    pluginStore.startStatusPolling()
    await Promise.all([pluginStore.loadApps(), pluginStore.loadMarketApps()])
    await syncFilterToRoute(routeFilter.value)
  })

  onUnmounted(() => {
    pluginStore.stopStatusPolling()
  })

  return {
    loading,
    marketLoading,
    buildHubFilter,
    visibleRecentApps,
    visibleInstalledApps,
    visibleMarketApps,
    executionStatusLabel,
    getInstallProgress,
    isPreviewStarting: pluginStore.isPreviewStarting,
    setFilter: async (filter: BuildHubFilter) => {
      pluginStore.setBuildHubFilter(filter)
      await syncFilterToRoute(filter)
    },
  }
}
