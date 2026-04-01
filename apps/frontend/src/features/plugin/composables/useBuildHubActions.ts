import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { usePluginStore } from '@/stores/plugin'
import type { CreateAppType } from '@/config/appTemplates'
import { getAppTemplateCatalog } from '@/config/appTemplates'
import { openPluginDevWorkbench, openPluginFullscreen } from '@/app/router/navigation'
import { APPS_HUB_PATH } from '@/app/router/paths'
import { useRecentDevSession } from '@/features/plugin/composables/useRecentDevSession'
import { useBuildHubLifecycleFacade } from '@/features/plugin/services/buildHubLifecycleFacade'
import type { MarketPlugin } from '@/features/plugin/store/types'
import type { Plugin } from '@/features/plugin/types'

interface BuildHubUser {
  id: string
  email: string
}

const toSlug = (value: string) =>
  String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[._-]+|[._-]+$/g, '')

const buildOwnerPrefix = (user?: BuildHubUser | null): string => {
  if (!user?.email) return 'com.local.user.uid'
  const email = user.email.toLowerCase()
  const [localRaw, domainRaw] = email.includes('@') ? email.split('@') : [email, 'local']
  const local = toSlug(localRaw) || 'user'
  const domainParts = domainRaw
    .split('.')
    .map((part) => toSlug(part))
    .filter(Boolean)
    .reverse()
  const uid = toSlug(user.id).slice(0, 12) || 'uid'
  return ['com', ...domainParts, local, uid].join('.')
}

const inferAppTypeFromPrompt = (prompt: string): CreateAppType => {
  const text = prompt.toLowerCase()
  if (text.includes('mobile') || text.includes('移动') || text.includes('手机')) return 'mobile'
  if (text.includes('web') || text.includes('网页') || text.includes('网站')) return 'web'
  return 'desktop'
}

const inferAppName = (prompt: string): string => {
  const firstLine = String(prompt || '').trim().split('\n')[0]
  return (firstLine || 'My App').slice(0, 48)
}

export function useBuildHubActions(user: BuildHubUser | null | undefined) {
  const router = useRouter()
  const pluginStore = usePluginStore()
  const lifecycleFacade = useBuildHubLifecycleFacade()
  const { resuming, resumeRecentSession } = useRecentDevSession()
  const canCreateDirectly = computed(() => Boolean(user?.id && user?.email))

  const createFromPrompt = async (prompt: string) => {
    const normalizedPrompt = String(prompt || '').trim()
    pluginStore.setBuildHubPromptDraft(normalizedPrompt)
    if (!normalizedPrompt) {
      pluginStore.openCreateWizard()
      return false
    }
    if (!canCreateDirectly.value || !user) {
      pluginStore.openCreateWizard()
      return false
    }
    const appType = inferAppTypeFromPrompt(normalizedPrompt)
    const template = getAppTemplateCatalog(appType)
    const appName = inferAppName(normalizedPrompt)
    const appSlug = toSlug(appName).slice(0, 36) || 'new-app'
    const pluginId = `${buildOwnerPrefix(user)}.${appSlug}-${Date.now().toString().slice(-6)}`
    await lifecycleFacade.createDevSession({
      template_id: template.templateId,
      app_type: appType,
      name: appName,
      plugin_id: pluginId,
      description: normalizedPrompt,
      owner_email: user.email,
      owner_user_id: user.id,
    })
    return true
  }

  const openCreateWizard = () => {
    pluginStore.openCreateWizard()
  }

  const openImportOrCopy = async () => {
    await router.replace({
      name: 'apps',
      params: { section: 'hub' },
      query: {
        ...router.currentRoute.value.query,
        filter: 'market'
      }
    })
    pluginStore.setBuildHubFilter('market')
  }

  const openAppRuntime = async (app: Plugin) => {
    pluginStore.openApp(app, 'normal')
    await openPluginFullscreen(router, app.id, APPS_HUB_PATH, 'normal')
  }

  const openAppDevWorkbench = async (app: Plugin) => {
    pluginStore.openApp(app, 'preview')
    pluginStore.rememberBuildHubRecentSession(app.id)
    await openPluginDevWorkbench(router, app.id, APPS_HUB_PATH)
  }

  const startAppDevSession = async (app: Plugin) => {
    pluginStore.rememberBuildHubRecentSession(app.id)
    await lifecycleFacade.startDevSession(app.id)
  }

  const openMarketApp = async (marketApp: MarketPlugin) => {
    const installed = pluginStore.installedApps.find((item) => item.id === marketApp.id)
    if (!installed) return
    await openAppRuntime(installed)
  }

  const installFromMarket = async (appId: string) => {
    await pluginStore.installApp(appId)
  }

  return {
    resuming,
    createFromPrompt,
    openCreateWizard,
    openImportOrCopy,
    resumeRecentSession,
    openAppRuntime,
    openAppDevWorkbench,
    startAppDevSession,
    openMarketApp,
    installFromMarket,
  }
}
