<template>
  <div class="section-content">
    <div class="market-container">
      <div class="section-header">
        <h2>{{ t.apps.market }}</h2>
        <button class="create-btn ui-btn ui-btn--neutral" @click="handleOpenCreateWizard">{{ t.apps.createApp }}</button>
      </div>
      <div class="market-toolbar">
        <input
          class="market-search"
          :value="marketQuery"
          :placeholder="t.apps.searchPlaceholder"
          @input="setMarketQuery(($event.target as HTMLInputElement).value)"
        />
        <button
          class="refresh-btn"
          type="button"
          :disabled="marketLoading"
          :title="t.apps.refresh"
          @click="refreshMarket"
        >
          <RefreshCw :size="16" :class="{ spinning: marketLoading }" />
          <span>{{ t.apps.refresh }}</span>
        </button>
      </div>
      <div v-if="marketLoading" class="loading">{{ t.common.loading }}</div>
      <div v-else-if="marketError" class="empty-state error-state">
        <p>{{ t.apps.marketLoadFailed }}</p>
        <button class="retry-btn" type="button" @click="refreshMarket">
          {{ (t.common.retry as string) || '重试' }}
        </button>
      </div>
      <div v-else-if="filteredMarketApps.length === 0" class="empty-state">
        <p>{{ t.apps.noInstalled }}</p>
      </div>
      <div v-else class="apps-grid">
        <AppCardShell
          v-for="app in filteredMarketApps"
          :key="app.id"
          :icon="app.icon"
          :name="app.name"
          :description="app.description"
          :is-official="app.is_official"
          :is-user-created="app.source_type === 'user_created'"
          :official-text="t.apps.official"
          :created-text="t.apps.createdByMe"
        >
          <template #meta>
            <div class="app-meta">
              <span class="badge">v{{ app.version }}</span>
              <span v-if="app.installed_version && app.installed_version !== app.version" class="author">
                installed v{{ app.installed_version }}
              </span>
            </div>
          </template>
          <template #actions>
            <button
              v-if="isDesktopApp(app) && app.action === 'open'"
              class="btn-secondary ui-btn ui-btn--neutral"
              @click="openInstalledFromMarket(app.id)"
            >
              {{ t.apps.openApp }}
            </button>
            <button
              v-else-if="app.action === 'update'"
              class="btn-primary ui-btn ui-btn--emphasis"
              @click="updateApp(app.id)"
            >
              更新
            </button>
            <button
              v-else-if="isDesktopApp(app) && app.action === 'installed'"
              class="btn-secondary ui-btn ui-btn--neutral"
              @click="handleStartApp(app.id)"
            >
              {{ t.apps.start }}
            </button>
            <button
              v-else
              class="btn-primary ui-btn ui-btn--emphasis"
              @click="installApp(app.id)"
            >
              安装
            </button>
            <button
              v-if="app.installed"
              class="btn-danger"
              @click="uninstallApp(app.id)"
            >
              卸载
            </button>
            <button
              v-if="app.installed"
              class="btn-secondary ui-btn ui-btn--neutral"
              :disabled="isPreviewStarting(app.id)"
              @click="handleStartDevMode(app.id)"
            >
              {{ isPreviewStarting(app.id) ? t.apps.starting : '开发模式' }}
            </button>
          </template>
          <div v-if="getInstallProgress(app.id)" class="app-status mt-2">
            <span :class="['status-dot', getInstallProgress(app.id)?.status === 'failed' ? 'error' : 'starting']"></span>
            <span class="status-text">
              {{ getInstallProgress(app.id)?.message }} ({{ getInstallProgress(app.id)?.progress || 0 }}%)
            </span>
          </div>
        </AppCardShell>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { RefreshCw } from 'lucide-vue-next'
import { usePluginStore } from '@/features/plugin/store'
import { useI18n } from '@/composables/useI18n'
import AppCardShell from '@/features/plugin/components/AppCardShell.vue'

defineProps<{
  openInstalledFromMarket: (appId: string) => void
}>()

const pluginStore = usePluginStore()
const { marketLoading, marketError, marketQuery, filteredMarketApps } = storeToRefs(pluginStore)
const { setMarketQuery, loadMarketApps, installApp, updateApp, uninstallApp, getInstallProgress, isPreviewStarting, openCreateWizard, runLifecycleOperation } = pluginStore
const { t } = useI18n()

const isDesktopApp = (app: { app_type?: string }) => String(app.app_type || 'desktop') === 'desktop'

const handleStartApp = async (appId: string) => {
  await runLifecycleOperation({
    operationType: 'start_runtime',
    payload: { plugin_id: appId },
    navigationIntent: 'runtime',
    from: '/app/apps',
    uiMode: 'modal',
    completionMessage: '启动完成，打开中...'
  })
}

const handleStartDevMode = async (appId: string) => {
  await runLifecycleOperation({
    operationType: 'start_dev_session',
    payload: { plugin_id: appId },
    navigationIntent: 'workbench',
    from: '/app/apps',
    uiMode: 'modal',
    completionMessage: '启动完成，打开中...'
  })
}

const handleOpenCreateWizard = async () => {
  openCreateWizard()
}

const refreshMarket = async () => {
  await loadMarketApps(true)
}
</script>

<style scoped>
.section-content {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.market-container h2 {
  margin: 0;
  font-size: 1.5rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.apps-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 1.5rem;
}

.app-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.badge {
  padding: 0.25rem 0.5rem;
  background: color-mix(in srgb, var(--color-primary) 14%, var(--color-surface-2));
  color: var(--color-text-primary);
  border: 1px solid color-mix(in srgb, var(--color-primary) 36%, var(--color-border));
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
}

.author {
  color: var(--color-text-secondary);
  font-size: 0.85rem;
}

.app-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-secondary);
}

.status-dot.starting {
  background: #f59e0b;
  animation: pulse 1.5s infinite;
}

.status-dot.error {
  background: #ef4444;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}

.btn-primary,
.btn-secondary,
.btn-danger {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 0.75rem;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  border: none;
}

.btn-secondary {
  border: 1px solid var(--color-button-neutral-border);
}

.btn-danger {
  background: #ef4444;
  color: white;
}

.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  color: var(--color-text-secondary);
}

.loading {
  text-align: center;
  padding: 4rem 2rem;
  color: var(--color-primary);
}

.market-toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.market-search {
  flex: 1;
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface-3);
  color: var(--color-text);
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  flex-shrink: 0;
  padding: 0.7rem 0.9rem;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface-3);
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
}

.refresh-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.refresh-btn .spinning {
  animation: rotate 0.9s linear infinite;
}

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.retry-btn {
  padding: 0.6rem 1.1rem;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface-3);
  color: var(--color-text);
  cursor: pointer;
}

.retry-btn:hover {
  border-color: var(--color-primary);
}

.create-btn {
  border: 1px solid var(--color-button-neutral-border);
  border-radius: 0.5rem;
  padding: 0.625rem 1rem;
  background: var(--color-button-neutral-bg);
  color: var(--color-button-neutral-fg);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.create-btn:hover {
  border-color: var(--color-button-neutral-hover-border);
  background: var(--color-button-neutral-hover-bg);
}

@keyframes rotate {
  to {
    transform: rotate(360deg);
  }
}
</style>
