import { computed, ref, type ComputedRef, type Ref } from 'vue'
import type { Plugin, PluginRunMode } from '@/features/plugin/types'
import type { BuildHubFilter, LifecycleTask, MarketPlugin, MobilePublishState, PluginInstallProgress, TemplateCacheInfo, WebPublishState } from '@/stores/plugin/types'
import { PollingRegistry } from '@/stores/plugin/pollingRegistry'

export interface PluginStoreState {
  installedApps: Ref<Plugin[]>
  activeApp: Ref<Plugin | null>
  activeMode: Ref<PluginRunMode>
  loading: Ref<boolean>
  refreshing: Ref<boolean>
  error: Ref<string | null>
  marketApps: Ref<MarketPlugin[]>
  marketLoading: Ref<boolean>
  marketError: Ref<string | null>
  marketQuery: Ref<string>
  installProgressMap: Ref<Map<string, PluginInstallProgress>>
  previewStartingMap: Ref<Map<string, boolean>>
  createWizardVisible: Ref<boolean>
  creatingPlugin: Ref<boolean>
  templateCacheInfo: Ref<TemplateCacheInfo | null>
  publishStateMap: Ref<Map<string, WebPublishState>>
  mobilePublishStateMap: Ref<Map<string, MobilePublishState>>
  activeLifecycleTask: Ref<LifecycleTask | null>
  lifecycleModalVisible: Ref<boolean>
  lifecycleLastHandledTaskId: Ref<string>
  lifecycleCompletionMessage: Ref<string>
  buildHubFilter: Ref<BuildHubFilter>
  buildHubPromptDraft: Ref<string>
  buildHubRecentPluginId: Ref<string>
  buildHubRecentVisitedAt: Ref<number>
  hasStartingApp: ComputedRef<boolean>
  filteredMarketApps: ComputedRef<MarketPlugin[]>
  pollInterval: Ref<ReturnType<typeof setInterval> | null>
  installPollers: PollingRegistry
  publishPollers: PollingRegistry
  mobilePublishPollers: PollingRegistry
  lifecyclePollers: PollingRegistry
}

export function createPluginStoreState(): PluginStoreState {
  const installedApps = ref<Plugin[]>([])
  const activeApp = ref<Plugin | null>(null)
  const activeMode = ref<PluginRunMode>('normal')
  const loading = ref(false)
  const refreshing = ref(false)
  const error = ref<string | null>(null)
  const marketApps = ref<MarketPlugin[]>([])
  const marketLoading = ref(false)
  const marketError = ref<string | null>(null)
  const marketQuery = ref('')
  const installProgressMap = ref<Map<string, PluginInstallProgress>>(new Map())
  const previewStartingMap = ref<Map<string, boolean>>(new Map())
  const createWizardVisible = ref(false)
  const creatingPlugin = ref(false)
  const templateCacheInfo = ref<TemplateCacheInfo | null>(null)
  const publishStateMap = ref<Map<string, WebPublishState>>(new Map())
  const mobilePublishStateMap = ref<Map<string, MobilePublishState>>(new Map())
  const activeLifecycleTask = ref<LifecycleTask | null>(null)
  const lifecycleModalVisible = ref(false)
  const lifecycleLastHandledTaskId = ref('')
  const lifecycleCompletionMessage = ref('')
  const buildHubFilter = ref<BuildHubFilter>('all')
  const buildHubPromptDraft = ref('')
  const buildHubRecentPluginId = ref('')
  const buildHubRecentVisitedAt = ref(0)

  const pollInterval = ref<ReturnType<typeof setInterval> | null>(null)
  const installPollers = new PollingRegistry()
  const publishPollers = new PollingRegistry()
  const mobilePublishPollers = new PollingRegistry()
  const lifecyclePollers = new PollingRegistry()

  const hasStartingApp = computed(() => {
    return installedApps.value.some((app) => app.state === 'starting' || app.state === 'stopping')
  })

  const filteredMarketApps = computed(() => {
    const q = marketQuery.value.trim().toLowerCase()
    if (!q) return marketApps.value
    return marketApps.value.filter(
      (app: MarketPlugin) =>
        app.name.toLowerCase().includes(q) ||
        app.description.toLowerCase().includes(q) ||
        app.id.toLowerCase().includes(q) ||
        (app.tags || []).some((tag: string) => String(tag).toLowerCase().includes(q)),
    )
  })

  return {
    installedApps,
    activeApp,
    activeMode,
    loading,
    refreshing,
    error,
    marketApps,
    marketLoading,
    marketError,
    marketQuery,
    installProgressMap,
    previewStartingMap,
    createWizardVisible,
    creatingPlugin,
    templateCacheInfo,
    publishStateMap,
    mobilePublishStateMap,
    activeLifecycleTask,
    lifecycleModalVisible,
    lifecycleLastHandledTaskId,
    lifecycleCompletionMessage,
    buildHubFilter,
    buildHubPromptDraft,
    buildHubRecentPluginId,
    buildHubRecentVisitedAt,
    hasStartingApp,
    filteredMarketApps,
    pollInterval,
    installPollers,
    publishPollers,
    mobilePublishPollers,
    lifecyclePollers,
  }
}
