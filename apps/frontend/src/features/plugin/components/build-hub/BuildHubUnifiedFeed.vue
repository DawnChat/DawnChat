<template>
  <section class="feed-root">
    <div class="filter-row">
      <button
        v-for="item in filters"
        :key="item.id"
        class="filter-btn ui-btn ui-btn--neutral"
        :class="{ 'ui-selected': activeFilter === item.id }"
        type="button"
        @click="$emit('change-filter', item.id)"
      >
        {{ item.label }}
      </button>
    </div>

    <div v-if="createdApps.length > 0" class="feed-section">
      <div class="section-head">
        <div class="section-title-group">
          <h3>{{ t.apps.myCreatedApps }}</h3>
          <span class="count-chip">{{ createdApps.length }}</span>
        </div>
      </div>
      <div class="feed-grid">
        <BuildHubAppCard
          v-for="app in createdApps"
          :key="`created-${app.id}`"
          :icon="resolveAppTypeIcon(app.app_type)"
          :name="app.name"
          :description="app.description"
          :status="executionStatusLabel(app)"
          card-type="created"
          :clickable="!(app.preview?.install_status === 'running' || isPreviewStarting(app.id))"
          :menu-items="[
            { key: 'open', label: t.apps.openApp },
            { key: 'fork', label: t.apps.forkApp },
            { key: 'delete', label: t.common.delete, danger: true }
          ]"
          @card-click="app.preview?.state === 'running' ? $emit('open-dev', app) : $emit('start-dev', app)"
          @menu-action="(key) => handleCreatedMenuAction(key, app)"
        />
      </div>
    </div>

    <div v-if="installedApps.length > 0" class="feed-section">
      <div class="section-head">
        <div class="section-title-group">
          <h3>{{ t.apps.installed }}</h3>
          <span class="count-chip">{{ installedApps.length }}</span>
        </div>
      </div>
      <div class="feed-grid">
        <BuildHubAppCard
          v-for="app in installedApps"
          :key="`installed-${app.id}`"
          :icon="resolveAppTypeIcon(app.app_type)"
          :name="app.name"
          :description="app.description"
          :status="executionStatusLabel(app)"
          card-type="installed"
          :clickable="!(app.preview?.install_status === 'running' || isPreviewStarting(app.id))"
          :menu-items="[
            { key: 'fork', label: t.apps.forkApp },
            { key: 'uninstall', label: t.common.uninstall, danger: true }
          ]"
          @card-click="$emit('open-runtime', app)"
          @menu-action="(key) => handleInstalledMenuAction(key, app)"
        />
      </div>
    </div>

    <div v-if="marketApps.length > 0" class="feed-section">
      <div class="section-head">
        <div class="section-title-group">
          <h3>{{ t.apps.recommendedMarket }}</h3>
          <span class="count-chip">{{ marketApps.length }}</span>
        </div>
      </div>
      <div class="feed-grid">
        <BuildHubAppCard
          v-for="app in marketApps"
          :key="`market-${app.id}`"
          :icon="resolveAppTypeIcon(app.app_type)"
          :name="app.name"
          :description="app.description"
          :status="executionStatusLabel(app)"
          card-type="market"
          :clickable="false"
          :action-label="app.installed ? t.common.installed : t.apps.installApp"
          :action-disabled="app.installed"
          @action-click="$emit('install-market', app.id)"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Globe, MonitorSmartphone, Smartphone } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'
import type { BuildHubFilter, MarketPlugin } from '@/features/plugin/store/types'
import type { Plugin } from '@/features/plugin/types'
import BuildHubAppCard from './BuildHubAppCard.vue'

defineProps<{
  activeFilter: BuildHubFilter
  createdApps: Plugin[]
  installedApps: Plugin[]
  marketApps: MarketPlugin[]
  executionStatusLabel: (app: Plugin | MarketPlugin) => string
  isPreviewStarting: (appId: string) => boolean
}>()

const { t } = useI18n()

const resolveAppTypeIcon = (appType?: string) => {
  if (appType === 'web') return Globe
  if (appType === 'mobile') return Smartphone
  return MonitorSmartphone
}

const filters = computed<Array<{ id: BuildHubFilter; label: string }>>(() => [
  { id: 'all', label: t.value.apps.filterAll },
  { id: 'recent', label: t.value.apps.filterRecent },
  { id: 'installed', label: t.value.apps.filterInstalled },
  { id: 'market', label: t.value.apps.filterMarket },
])

const emit = defineEmits<{
  'change-filter': [filter: BuildHubFilter]
  'open-dev': [app: Plugin]
  'start-dev': [app: Plugin]
  'open-runtime': [app: Plugin]
  'fork-app': [app: Plugin]
  'delete-app': [app: Plugin]
  'uninstall-app': [app: Plugin]
  'install-market': [appId: string]
}>()

const handleCreatedMenuAction = (key: string, app: Plugin) => {
  if (key === 'open') {
    emit('open-runtime', app)
    return
  }
  if (key === 'fork') {
    emit('fork-app', app)
    return
  }
  if (key === 'delete') {
    emit('delete-app', app)
  }
}

const handleInstalledMenuAction = (key: string, app: Plugin) => {
  if (key === 'fork') {
    emit('fork-app', app)
    return
  }
  if (key === 'uninstall') {
    emit('uninstall-app', app)
  }
}
</script>

<style scoped>
.feed-root {
  display: flex;
  flex-direction: column;
  gap: 0.84rem;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  padding: 0.04rem 0 0.1rem;
}

.filter-btn {
  border-radius: 7px;
  min-height: 24px;
  padding: 0 0.5rem;
  font-size: 0.71rem;
  line-height: 1;
  border-width: 1px;
  opacity: 0.92;
}

.feed-section {
  padding: 0;
}

.section-head {
  display: flex;
  align-items: center;
  margin-bottom: 0.5rem;
}

.section-title-group {
  display: inline-flex;
  align-items: center;
  gap: 0.42rem;
}

.feed-section h3 {
  margin: 0;
  font-size: 1.02rem;
  line-height: 1.2;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.count-chip {
  font-size: 0.7rem;
  color: var(--color-text-secondary);
  border: 1px solid color-mix(in srgb, var(--color-border) 46%, transparent);
  border-radius: 999px;
  padding: 0.12rem 0.34rem;
  background: transparent;
  opacity: 0.9;
}

.feed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 0.5rem;
}
</style>
