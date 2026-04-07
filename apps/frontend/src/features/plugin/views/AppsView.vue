<template>
  <div class="apps-view build-hub-view">
    <section class="launcher-stage">
      <section class="launcher-shell">
        <header class="launcher-header">
          <div class="brand-bar">
            <img src="/logo.svg" alt="DawnChat" class="brand-logo" width="20" height="20" />
            <div class="brand-copy">
              <h1>{{ t.app.name }}</h1>
              <p class="launcher-slogan">{{ t.app.subtitle }}</p>
            </div>
          </div>
        </header>

        <button
          class="launcher-create-card assistant-hero-card"
          type="button"
          :disabled="quickCreateLoadingType === 'assistant'"
          @click="handleAssistantEntryClick"
        >
          <div class="card-icon">
            <Bot :size="20" />
          </div>
          <div class="card-copy">
            <h3>{{ t.apps.launcherAssistantTitle }}</h3>
            <p>{{ t.apps.launcherAssistantDescription }}</p>
          </div>
        </button>

        <div class="create-toolbar">
          <h2>{{ t.apps.newProjectSectionTitle }}</h2>
        </div>

        <div class="launcher-create-grid">
          <button
            v-for="card in createCards"
            :key="card.appType"
            class="launcher-create-card"
            type="button"
            :disabled="quickCreateLoadingType === card.appType"
            @click="handleCreateCardClick(card.appType)"
          >
            <div class="card-icon">
              <component :is="card.icon" :size="20" />
            </div>
            <div class="card-copy">
              <h3>{{ card.title }}</h3>
              
              <p>{{ card.description }}</p>
            </div>
          </button>
        </div>

      </section>

      <div class="recent-toolbar">
        <h2 v-if="!showMoreApps">{{ t.apps.recentProjects }}</h2>
        <button class="apps-toggle-trigger" type="button" @click="toggleMoreApps">
          <span>{{ showMoreApps ? t.apps.collapseAppsList : t.apps.viewMoreApps }}</span>
          <ChevronRight class="toggle-chevron" :class="{ 'toggle-chevron--expanded': showMoreApps }" :size="14" />
        </button>
      </div>

      <section v-if="!showMoreApps" class="recent-panel">
        <div v-if="recentQuickList.length > 0" class="recent-list">
          <button
            v-for="app in recentQuickList"
            :key="app.id"
            class="recent-item"
            type="button"
            @click="handleOpenRecent(app)"
          >
            <span class="recent-icon">
              <component :is="resolveAppTypeIcon(app.app_type)" :size="11" />
            </span>
            <span class="recent-main">
              <strong>{{ app.name }}</strong>
              <small>{{ executionStatusLabel(app) }}</small>
            </span>
            <span class="recent-action">{{ app.preview?.state === 'running' ? '~/running' : `~/${app.id}` }}</span>
          </button>
        </div>
        <p v-else class="recent-empty">{{ t.apps.noRecentProjects }}</p>
      </section>
    </section>

    <Transition name="feed-expand">
      <section v-if="showMoreApps" class="feed-panel">
        <BuildHubUnifiedFeed
          :active-filter="buildHubFilter"
          :created-apps="visibleRecentApps"
          :installed-apps="visibleInstalledApps"
          :market-apps="visibleMarketApps"
          :execution-status-label="executionStatusLabel"
          :is-preview-starting="isPreviewStarting"
          @change-filter="setFilter"
          @open-dev="openAppDevWorkbench"
          @start-dev="startAppDevSession"
          @open-runtime="openAppRuntime"
          @fork-app="handleForkApp"
          @delete-app="handleDeleteApp"
          @uninstall-app="handleUninstallApp"
          @install-market="installFromMarket"
        />
      </section>
    </Transition>

    <footer class="apps-footer">
      <span class="brand-name">@InstructWare Protocol v1.0</span>
    </footer>

    <CreateAppWizardModal
      :visible="createWizardVisible"
      :creating="creatingPlugin"
      :template-info="templateCacheInfo"
      :user="user"
      @close="closeCreateWizard"
      @app-type-change="handleCreateAppTypeChange"
      @confirm="handleCreatePlugin"
    />

  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ChevronRight, MonitorSmartphone, Globe, Smartphone, Bot } from 'lucide-vue-next'
import CreateAppWizardModal from '@/features/plugin/components/CreateAppWizardModal.vue'
import BuildHubUnifiedFeed from '@/features/plugin/components/build-hub/BuildHubUnifiedFeed.vue'
import { useBuildHubState } from '@/features/plugin/composables/useBuildHubState'
import { useBuildHubActions } from '@/features/plugin/composables/useBuildHubActions'
import { useBuildHubCreationFlow } from '@/features/plugin/composables/useBuildHubCreationFlow'
import { useBuildHubLifecycleFacade } from '@/features/plugin/services/buildHubLifecycleFacade'
import { usePluginStore } from '@/stores/plugin'
import { useI18n } from '@/composables/useI18n'
import type { CreateAppType } from '@/config/appTemplates'
import type { Plugin } from '@/features/plugin/types'

interface Props {
  section?: string
  user?: {
    id: string
    email: string
  } | null
}

const props = defineProps<Props>()
const pluginStore = usePluginStore()
const lifecycleFacade = useBuildHubLifecycleFacade()
const { t } = useI18n()
const { createWizardVisible, creatingPlugin, templateCacheInfo, installedApps } = storeToRefs(pluginStore)
const { closeCreateWizard } = pluginStore
const currentUser = computed(() => props.user || null)
const {
  buildHubFilter,
  visibleRecentApps,
  visibleInstalledApps,
  visibleMarketApps,
  executionStatusLabel,
  isPreviewStarting,
  setFilter,
} = useBuildHubState()
const {
  openCreateWizard,
  openAppRuntime,
  openAppDevWorkbench,
  startAppDevSession,
  installFromMarket,
} = useBuildHubActions(currentUser.value)
const {
  quickCreateLoadingType,
  handleCreatePlugin,
  handleCreateAppTypeChange,
  handleQuickCreate,
  openOrCreateMainAssistant,
  handleForkApp,
} = useBuildHubCreationFlow({
  user: currentUser,
  installedApps,
  openCreateWizard,
  closeCreateWizard,
  createDevSession: lifecycleFacade.createDevSession,
  startAppDevSession,
  openAppDevWorkbench,
  ensureTemplateCache: pluginStore.ensureTemplateCache,
})
const showMoreApps = ref(buildHubFilter.value !== 'all')

const createCards = computed(() => [
  {
    appType: 'desktop' as const,
    icon: MonitorSmartphone,
    title: t.value.apps.launcherDesktopTitle,
    description: t.value.apps.launcherDesktopDescription
  },
  {
    appType: 'web' as const,
    icon: Globe,
    title: t.value.apps.launcherWebTitle,
    description: t.value.apps.launcherWebDescription
  },
  {
    appType: 'mobile' as const,
    icon: Smartphone,
    title: t.value.apps.launcherMobileTitle,
    description: t.value.apps.launcherMobileDescription
  }
])

const recentQuickList = computed(() => visibleRecentApps.value.slice(0, 6))

const resolveAppTypeIcon = (appType?: string) => {
  if (appType === 'web') return Globe
  if (appType === 'mobile') return Smartphone
  return MonitorSmartphone
}

watch(buildHubFilter, (next) => {
  if (next !== 'all') {
    showMoreApps.value = true
  }
})


const handleOpenRecent = async (app: (typeof visibleRecentApps.value)[number]) => {
  if (app.preview?.state === 'running') {
    await openAppDevWorkbench(app)
    return
  }
  await startAppDevSession(app)
}

const toggleMoreApps = () => {
  showMoreApps.value = !showMoreApps.value
}

const handleAssistantEntryClick = () => {
  void openOrCreateMainAssistant()
}

const handleCreateCardClick = (appType: CreateAppType) => {
  void handleQuickCreate(appType)
}

const handleDeleteApp = async (app: Plugin) => {
  const id = String(app.id || '').trim()
  if (!id) return
  await pluginStore.uninstallApp(id)
}

const handleUninstallApp = async (app: Plugin) => {
  const id = String(app.id || '').trim()
  if (!id) return
  await pluginStore.uninstallApp(id)
}

</script>

<style scoped>
.apps-view {
  height: 100%;
  overflow: auto;
  background: var(--color-app-canvas);
}

.build-hub-view {
  width: 100%;
  min-height: 100%;
  padding: 12vh 1rem 1.4rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.72rem;
}

.launcher-stage {
  width: 100%;
  max-width: 520px;
  display: flex;
  flex-direction: column;
  gap: 0.74rem;
}

.launcher-shell {
  border: none;
  border-radius: 0;
  background: transparent;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.82rem;
}

.brand-bar {
  display: flex;
  align-items: center;
  gap: 0.52rem;
}

.brand-logo {
  width: 40px;
  height: 40px;
  opacity: 0.9;
  filter: grayscale(0.1);
}

.brand-name {
  color: color-mix(in srgb, var(--color-text-secondary) 72%, var(--color-app-canvas));
  font-size: 0.72rem;
  letter-spacing: 0.04em;
  display: block;
  white-space: nowrap;
  flex-shrink: 0;
}

.brand-copy {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
}

.brand-copy h1 {
  margin: 0;
  font-size: 1.95rem;
  line-height: 1.2;
  letter-spacing: 0.01em;
  font-weight: 620;
}

.launcher-slogan {
  margin: 0.12rem 0 0;
  color: var(--color-text-secondary);
  font-size: 0.8rem;
  line-height: 1.35;
}

.launcher-create-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.46rem;
}

.launcher-create-card.assistant-hero-card {
  width: 100%;
  min-height: 92px;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  align-items: center;
  gap: 0.56rem;
  padding: 0.66rem 0.72rem;
  text-align: left;
}

.launcher-create-card.assistant-hero-card .card-icon {
  width: 26px;
  height: 26px;
  border-radius: 8px;
}

.launcher-create-card.assistant-hero-card .card-copy h3 {
  font-size: 0.88rem;
}

.launcher-create-card.assistant-hero-card .card-copy p {
  margin-top: 0.2rem;
  font-size: 0.66rem;
  line-height: 1.3;
}

.launcher-create-card {
  border: 1px solid color-mix(in srgb, var(--color-border) 70%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-surface-2) 82%, transparent);
  color: var(--color-text-primary);
  padding: 0.62rem 0.64rem 0.56rem;
  min-height: 96px;
  display: flex;
  flex-direction: column;
  gap: 0.42rem;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.18s ease, transform 0.18s ease, background 0.18s ease;
}

.launcher-create-card:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--color-primary) 36%, var(--color-border));
  transform: translateY(-1px);
  background: color-mix(in srgb, var(--color-surface-2) 92%, transparent);
}

.launcher-create-card:disabled {
  opacity: 0.66;
  cursor: not-allowed;
}

.card-icon {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  border: 1px solid color-mix(in srgb, var(--color-border) 85%, transparent);
  background: color-mix(in srgb, var(--color-surface-1) 54%, transparent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.card-copy h3 {
  margin: 0;
  font-size: 0.7rem;
  line-height: 1.2;
}

.card-copy p {
  margin: 0.2rem 0 0;
  color: var(--color-text-secondary);
  font-size: 0.6rem;
  line-height: 1.3;
}

.card-cta {
  margin-top: auto;
  color: color-mix(in srgb, var(--color-text-secondary) 92%, white 8%);
  font-size: 0.58rem;
}

.recent-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 0.1rem;
}

.create-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 0.12rem;
}

.apps-toggle-trigger {
  margin-left: auto;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  min-height: 24px;
  padding: 0.08rem 0.08rem;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.76rem;
  line-height: 1.2;
  cursor: pointer;
  border-radius: 6px;
  transition: color 0.18s ease, background 0.18s ease;
}

.apps-toggle-trigger:hover {
  color: var(--color-text-primary);
  background: color-mix(in srgb, var(--color-surface-2) 24%, transparent);
}

.apps-toggle-trigger:focus-visible {
  outline: 1px solid color-mix(in srgb, var(--color-primary) 48%, transparent);
  outline-offset: 1px;
}

.toggle-chevron {
  color: currentColor;
  transition: transform 0.2s ease;
}

.toggle-chevron--expanded {
  transform: rotate(90deg);
}

.recent-panel {
  border: none;
  border-radius: 0;
  background: transparent;
  padding: 0;
}

.recent-toolbar h2,
.create-toolbar h2 {
  margin: 0;
  font-size: 0.96rem;
  line-height: 1.2;
  font-weight: 600;
}

.recent-list {
  display: grid;
  gap: 0.04rem;
  margin-top: 0.42rem;
}

.recent-item {
  width: 100%;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-primary);
  min-height: 32px;
  padding: 0.22rem 0.26rem;
  display: grid;
  grid-template-columns: 18px 1fr auto;
  align-items: center;
  gap: 0.34rem;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease;
  text-align: left;
}

.recent-item:hover {
  border-color: color-mix(in srgb, var(--color-border) 86%, transparent);
  background: color-mix(in srgb, var(--color-surface-2) 24%, transparent);
}

.recent-icon {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--color-surface-2) 44%, transparent);
  color: var(--color-text-secondary);
  font-size: 0.56rem;
}

.recent-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.recent-main strong {
  font-size: 0.86rem;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}

.recent-main small {
  color: var(--color-text-secondary);
  font-size: 0.62rem;
}

.recent-action {
  color: var(--color-text-secondary);
  font-size: 0.62rem;
  letter-spacing: 0.01em;
  max-width: 170px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recent-empty {
  margin: 0.46rem 0 0;
  color: var(--color-text-secondary);
  font-size: 0.82rem;
}

.feed-panel {
  width: 100%;
  max-width: min(1040px, calc(100vw - 7rem));
  border: none;
  border-radius: 0;
  background: var(--color-app-canvas);
  padding: 0;
}

.apps-footer {
  margin-top: auto;
  padding-top: clamp(2rem, 8vh, 5rem);
  width: 100%;
  text-align: center;
  color: var(--color-text-secondary);
  opacity: 0.86;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.22rem;
}

.resume-hint {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 0.82rem;
}

.feed-expand-enter-active,
.feed-expand-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.feed-expand-enter-from,
.feed-expand-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 760px) {
  .build-hub-view {
    padding: 2.4rem 0.7rem 1rem;
  }

  .brand-copy h1 {
    font-size: 1.5rem;
  }

  .launcher-create-grid {
    grid-template-columns: 1fr;
  }

  .feed-panel {
    max-width: calc(100vw - 1.4rem);
  }

  .brand-name {
    white-space: normal;
    text-wrap: balance;
  }
}
</style>
