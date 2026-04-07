import { ref, type Ref } from 'vue'
import { useI18n } from '@/composables/useI18n'
import {
  AI_ASSISTANT_TEMPLATE_ID,
  MAIN_AI_ASSISTANT_ID_SUFFIX,
  getAppTemplateCatalog,
  type CreateAppType
} from '@/config/appTemplates'
import type { Plugin } from '@/features/plugin/types'
import type { CreatePluginPayload as StoreCreatePluginPayload, LifecycleTask } from '@/features/plugin/store'
import { logger } from '@/utils/logger'

interface BuildHubUser {
  id: string
  email: string
}

interface CreatePluginFormPayload {
  appType: CreateAppType
  name: string
  pluginId: string
  description: string
}

interface BuildHubCreationFlowOptions {
  user: Ref<BuildHubUser | null>
  installedApps: Ref<Plugin[]>
  openCreateWizard: () => void
  closeCreateWizard: () => void
  createDevSession: (payload: StoreCreatePluginPayload) => Promise<LifecycleTask>
  startAppDevSession: (app: Plugin) => Promise<void>
  openAppDevWorkbench: (app: Plugin) => Promise<void>
  ensureTemplateCache: (templateId: string, force?: boolean) => Promise<unknown>
}

const toSlug = (value: string) =>
  String(value)
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[._-]+|[._-]+$/g, '')

const buildOwnerPrefix = (user: BuildHubUser | null): string => {
  const email = String(user?.email || '').toLowerCase()
  const userId = String(user?.id || 'uid')
  if (!email.includes('@')) return `com.local.user.${userId.slice(0, 12)}`
  const [localPart, domainPart] = email.split('@')
  const domain = String(domainPart || 'local')
    .split('.')
    .reverse()
    .map((item) => item.replace(/[^a-z0-9]+/g, '-'))
    .filter(Boolean)
  const local = String(localPart || 'user').replace(/[^a-z0-9]+/g, '-')
  return ['com', ...domain, local, userId.slice(0, 12)].join('.')
}

export function useBuildHubCreationFlow({
  user,
  installedApps,
  openCreateWizard,
  closeCreateWizard,
  createDevSession,
  startAppDevSession,
  openAppDevWorkbench,
  ensureTemplateCache,
}: BuildHubCreationFlowOptions) {
  const { t } = useI18n()
  const quickCreateLoadingType = ref<CreateAppType | 'assistant' | null>(null)

  const buildPluginIdFromName = (name: string) => {
    const slug = toSlug(String(name || '').slice(0, 36)) || 'new-app'
    return `${buildOwnerPrefix(user.value)}.${slug}-${Date.now().toString().slice(-6)}`
  }

  const buildMainAssistantPluginId = () => `${buildOwnerPrefix(user.value)}.${MAIN_AI_ASSISTANT_ID_SUFFIX}`

  const isMainAssistantIdentity = (plugin: Plugin) => {
    if (plugin.is_main_assistant === true) return true
    if (String(plugin.source_type || '') === 'official_user_main_assistant') return true
    const templateId = String(plugin.template_id || '')
    return templateId === AI_ASSISTANT_TEMPLATE_ID && String(plugin.id || '').endsWith(`.${MAIN_AI_ASSISTANT_ID_SUFFIX}`)
  }

  const isOwnedByCurrentUser = (plugin: Plugin) => {
    const currentUser = user.value
    if (!currentUser) return false
    const ownerUserId = String(plugin.owner_user_id || '').trim()
    if (ownerUserId && ownerUserId === String(currentUser.id || '').trim()) return true
    const ownerEmail = String(plugin.owner_email || '').trim().toLowerCase()
    return Boolean(ownerEmail && ownerEmail === String(currentUser.email || '').trim().toLowerCase())
  }

  const handleCreatePlugin = async (payload: CreatePluginFormPayload) => {
    if (!user.value?.id || !user.value.email) return
    try {
      const template = getAppTemplateCatalog(payload.appType)
      closeCreateWizard()
      await createDevSession({
        template_id: template.templateId,
        app_type: payload.appType,
        name: payload.name,
        plugin_id: payload.pluginId,
        description: payload.description,
        owner_email: user.value.email,
        owner_user_id: user.value.id,
      })
    } catch (err) {
      logger.error('Create plugin failed:', err)
    }
  }

  const handleCreateAppTypeChange = async (appType: CreateAppType) => {
    const template = getAppTemplateCatalog(appType)
    try {
      await ensureTemplateCache(template.templateId, false)
    } catch (err) {
      logger.warn('Preload template cache failed', { appType, err })
    }
  }

  const handleQuickCreate = async (appType: CreateAppType) => {
    if (quickCreateLoadingType.value) return
    if (!user.value?.id || !user.value.email) {
      openCreateWizard()
      return
    }
    quickCreateLoadingType.value = appType
    try {
      const template = getAppTemplateCatalog(appType)
      const defaultName = appType === 'desktop'
        ? t.value.apps.quickCreateDesktopName
        : appType === 'web'
          ? t.value.apps.quickCreateWebName
          : t.value.apps.quickCreateMobileName
      await createDevSession({
        template_id: template.templateId,
        app_type: appType,
        name: defaultName,
        plugin_id: buildPluginIdFromName(defaultName),
        description: '',
        owner_email: user.value.email,
        owner_user_id: user.value.id,
      })
    } catch (err) {
      logger.error('Quick create app failed', { appType, err })
    } finally {
      quickCreateLoadingType.value = null
    }
  }

  const openOrCreateMainAssistant = async () => {
    if (quickCreateLoadingType.value) return
    if (!user.value?.id || !user.value.email) {
      openCreateWizard()
      return
    }
    quickCreateLoadingType.value = 'assistant'
    try {
      const mainPluginId = buildMainAssistantPluginId()
      const ownedPlugins = installedApps.value.filter(isOwnedByCurrentUser)
      const exactMain = ownedPlugins.find((item) => item.id === mainPluginId && isMainAssistantIdentity(item))
      const legacyMain = ownedPlugins.find((item) => {
        return item.id === mainPluginId && String(item.template_id || '') === AI_ASSISTANT_TEMPLATE_ID
      })
      const fallbackMain = ownedPlugins.find((item) => isMainAssistantIdentity(item))
      const mainAssistant = exactMain || legacyMain || fallbackMain || null
      if (mainAssistant) {
        if (mainAssistant.preview?.state === 'running') {
          await openAppDevWorkbench(mainAssistant)
        } else {
          await startAppDevSession(mainAssistant)
        }
        return
      }
      await createDevSession({
        template_id: AI_ASSISTANT_TEMPLATE_ID,
        app_type: 'desktop',
        name: t.value.apps.quickCreateAssistantName,
        plugin_id: mainPluginId,
        description: '',
        owner_email: user.value.email,
        owner_user_id: user.value.id,
        is_main_assistant: true,
      })
    } catch (err) {
      logger.error('Open or create main assistant failed', { err })
    } finally {
      quickCreateLoadingType.value = null
    }
  }

  const handleForkApp = async (app: Plugin) => {
    const appType: CreateAppType = app.app_type === 'web' || app.app_type === 'mobile' ? app.app_type : 'desktop'
    if (!user.value?.id || !user.value.email) {
      openCreateWizard()
      return
    }
    try {
      const templateId = String(app.template_id || getAppTemplateCatalog(appType).templateId)
      await createDevSession({
        template_id: templateId,
        app_type: appType,
        name: `${app.name} Copy`,
        plugin_id: buildPluginIdFromName(`${app.name}-copy`),
        description: app.description || '',
        owner_email: user.value.email,
        owner_user_id: user.value.id,
      })
    } catch (err) {
      logger.error('Fork app failed', { appId: app.id, err })
    }
  }

  return {
    quickCreateLoadingType,
    handleCreatePlugin,
    handleCreateAppTypeChange,
    handleQuickCreate,
    openOrCreateMainAssistant,
    handleForkApp,
  }
}
