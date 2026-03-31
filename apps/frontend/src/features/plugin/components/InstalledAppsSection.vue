<template>
  <div class="section-content">
    <div class="apps-container">
      <div class="section-header">
        <h2>{{ t.apps.installed }}</h2>
        <button class="create-btn ui-btn ui-btn--neutral" @click="handleOpenCreateWizard">{{ t.apps.createApp }}</button>
      </div>

      <div v-if="loading" class="loading">{{ t.common.loading }}</div>
      <div v-else-if="installedApps.length === 0" class="empty-state">
        <p>{{ t.apps.noInstalled }}</p>
      </div>
      <div v-else class="apps-grid">
        <AppCardShell
          v-for="app in installedApps"
          :key="app.id"
          :icon="app.icon"
          :name="app.name"
          :description="app.description"
          :is-official="app.is_official"
          :is-user-created="app.source_type === 'user_created'"
          :running="app.state === 'running'"
          :official-text="t.apps.official"
          :created-text="t.apps.createdByMe"
        >
          <template #meta>
            <div class="app-meta">
              <span class="badge">v{{ app.version }}</span>
              <span class="author">by {{ app.author }}</span>
            </div>
            <div class="app-status">
              <span :class="['status-dot', app.state]"></span>
              <span class="status-text">{{ getStatusText(app.state) }}</span>
            </div>
          </template>
          <template #actions>
            <button
              v-if="isDesktopApp(app) && app.state === 'running'"
              class="btn-secondary ui-btn ui-btn--neutral"
              @click="handleOpenApp(app)"
            >
              {{ t.apps.openApp }}
            </button>
            <button
              v-if="app.preview?.state === 'running'"
              class="btn-secondary ui-btn ui-btn--neutral"
              @click="handleOpenDevWorkbench(app)"
            >
              开发模式
            </button>
            <button
              v-if="isDesktopApp(app) && ['stopped', 'error', 'starting'].includes(app.state)"
              class="btn-primary ui-btn ui-btn--emphasis"
              :disabled="app.state === 'starting'"
              @click="handleStartApp(app.id)"
            >
              <Play :size="16" class="mr-1" v-if="app.state !== 'starting'" />
              {{ app.state === 'starting' ? t.apps.starting : t.apps.start }}
            </button>
            <button
              v-if="isDesktopApp(app) && app.state === 'running'"
              class="btn-danger"
              @click="stopApp(app.id)"
            >
              <Square :size="16" class="mr-1" />
              {{ t.apps.stop }}
            </button>
            <button
              v-if="app.preview?.state !== 'running'"
              class="btn-secondary ui-btn ui-btn--neutral"
              :disabled="isPreviewStarting(app.id)"
              @click="handleStartDevMode(app.id)"
            >
              {{ isPreviewStarting(app.id) ? t.apps.starting : '开发模式' }}
            </button>
            <button
              v-else
              class="btn-danger"
              @click="stopPreview(app.id)"
            >
              关闭预览
            </button>
            <div class="more-menu-wrap">
              <button class="btn-secondary ui-btn ui-btn--neutral more-btn" @click="toggleMore(app.id)">
                {{ t.common.more }}
              </button>
              <div v-if="moreOpenId === app.id" class="more-menu">
                <button class="more-item" @click="handleViewDetail(app.id)">查看详情</button>
                <button class="more-item danger" @click="handleUninstall(app.id)">卸载</button>
                <button class="more-item" @click="handleOpenSource(app.plugin_path)">打开源码</button>
              </div>
            </div>
          </template>
          <div v-if="app.error_message" class="app-error">
            {{ app.error_message }}
          </div>
          <div v-if="app.preview?.error_message" class="app-error">
            预览错误：{{ app.preview.error_message }}
          </div>
        </AppCardShell>
      </div>
    </div>

    <div v-if="detailModalVisible" class="modal-mask" @click.self="closeDetailModal">
      <div class="modal-panel">
        <div class="modal-header">
          <h3>{{ detailApp?.name || t.common.detail }}</h3>
          <button class="icon-btn" @click="closeDetailModal">×</button>
        </div>
        <div v-if="detailLoading" class="modal-loading">{{ t.common.loading }}</div>
        <div v-else class="modal-body">
          <div class="detail-grid">
            <div class="detail-item"><span>ID</span><code>{{ detailManifest.id || detailApp?.id || '-' }}</code></div>
            <div class="detail-item"><span>Version</span><code>{{ detailManifest.version || detailPyproject.version || detailApp?.version || '-' }}</code></div>
            <div class="detail-item"><span>Author</span><span>{{ detailManifest.author || detailApp?.author || '-' }}</span></div>
            <div class="detail-item"><span>Framework</span><span>{{ detailManifest.framework || '-' }}</span></div>
            <div class="detail-item full"><span>Description</span><span>{{ detailManifest.description || detailPyproject.description || detailApp?.description || '-' }}</span></div>
            <div class="detail-item"><span>Python</span><code>{{ detailPyproject.requires_python || '-' }}</code></div>
            <div class="detail-item full"><span>Source</span><code>{{ detailApp?.plugin_path || '-' }}</code></div>
            <div class="detail-item full"><span>Tags</span><span>{{ (detailManifest.tags || detailApp?.tags || []).join(', ') || '-' }}</span></div>
            <div class="detail-item full">
              <span>Dependencies</span>
              <div class="deps-list">
                <code v-for="dep in detailDependencies" :key="dep">{{ dep }}</code>
                <span v-if="detailDependencies.length === 0">-</span>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary ui-btn ui-btn--neutral" @click="closeDetailModal">{{ t.common.close }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { Play, Square } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { usePluginStore } from '@/features/plugin/store'
import { useI18n } from '@/composables/useI18n'
import {
  openPluginDevWorkbench,
  openPluginFullscreen as navigateToPluginFullscreen
} from '@/app/router/navigation'
import { logger } from '@/utils/logger'
import { buildBackendUrl } from '@/utils/backendUrl'
import AppCardShell from '@/features/plugin/components/AppCardShell.vue'

const pluginStore = usePluginStore()
const { installedApps, loading } = storeToRefs(pluginStore)
const { stopApp, stopPreview, openApp, isPreviewStarting, openCreateWizard, uninstallApp, runLifecycleOperation } = pluginStore
const { t } = useI18n()
const router = useRouter()
const moreOpenId = ref('')
const detailModalVisible = ref(false)
const detailLoading = ref(false)
const detailApp = ref<(typeof installedApps.value)[number] | null>(null)
const detailMetadata = ref<Record<string, any>>({})

const detailManifest = computed<Record<string, any>>(() => detailMetadata.value.manifest || {})
const detailPyproject = computed<Record<string, any>>(() => detailMetadata.value.pyproject || {})
const detailDependencies = computed<string[]>(() => {
  const deps = detailPyproject.value.dependencies
  if (!Array.isArray(deps)) return []
  return deps.map(item => String(item)).slice(0, 12)
})

const isDesktopApp = (app: { app_type?: string }) => String(app.app_type || 'desktop') === 'desktop'

const openPluginFullscreen = async (
  appId: string,
  from = '/app/apps',
  mode: 'normal' | 'preview' = 'normal'
) => {
  await navigateToPluginFullscreen(router, appId, from, mode)
}

const handleOpenApp = (app: (typeof installedApps.value)[number]) => {
  openApp(app, 'normal')
  openPluginFullscreen(app.id)
}

const handleOpenDevWorkbench = (app: (typeof installedApps.value)[number]) => {
  openApp(app, 'preview')
  openPluginDevWorkbench(router, app.id, '/app/apps')
}

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

const toggleMore = (appId: string) => {
  moreOpenId.value = moreOpenId.value === appId ? '' : appId
}

const closeMoreByOutside = (event: MouseEvent) => {
  const target = event.target as HTMLElement | null
  if (!target) return
  if (target.closest('.more-menu-wrap')) return
  moreOpenId.value = ''
}

const handleUninstall = async (appId: string) => {
  moreOpenId.value = ''
  await uninstallApp(appId)
}

const handleOpenSource = async (pluginPath?: string | null) => {
  moreOpenId.value = ''
  if (!pluginPath) return
  try {
    const { revealItemInDir } = await import('@tauri-apps/plugin-opener')
    await revealItemInDir(pluginPath)
  } catch (err) {
    logger.error('Failed to open source directory:', err)
  }
}

const handleViewDetail = async (appId: string) => {
  moreOpenId.value = ''
  const target = installedApps.value.find(item => item.id === appId) || null
  detailApp.value = target
  detailMetadata.value = {}
  detailModalVisible.value = true
  detailLoading.value = true
  try {
    const res = await fetch(buildBackendUrl(`/api/plugins/${encodeURIComponent(appId)}`))
    const data = await res.json()
    if (data?.status === 'success') {
      detailMetadata.value = data.detail_metadata || {}
    }
  } catch (err) {
    logger.error('Failed to load plugin detail metadata:', err)
  } finally {
    detailLoading.value = false
  }
}

const closeDetailModal = () => {
  detailModalVisible.value = false
}

const getStatusText = (state: string) => {
  const statusMap: Record<string, string> = {
    stopped: t.value.apps.stopped,
    starting: t.value.apps.starting,
    running: t.value.apps.running,
    stopping: t.value.apps.stopping,
    error: t.value.apps.error,
  }
  return statusMap[state] || state
}

onMounted(() => {
  document.addEventListener('click', closeMoreByOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', closeMoreByOutside)
})
</script>

<style scoped>
.section-content {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}

.apps-container h2 {
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

.status-dot.running {
  background: #10b981;
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.5);
}

.status-dot.starting,
.status-dot.stopping {
  background: #f59e0b;
  animation: pulse 1.5s infinite;
}

.status-dot.error {
  background: #ef4444;
}

.status-dot.stopped {
  background: #6b7280;
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

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  border: 1px solid var(--color-button-neutral-border);
}

.btn-secondary:hover {
  background: var(--color-button-neutral-hover-bg);
}

.btn-danger {
  background: #ef4444;
  color: white;
}

.btn-danger:hover {
  opacity: 0.9;
}

.app-error {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  color: #ef4444;
  font-size: 0.85rem;
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

.more-menu-wrap {
  position: relative;
}

.more-btn {
  min-width: 90px;
}

.more-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  display: flex;
  flex-direction: column;
  min-width: 140px;
  background: var(--color-surface-1);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  z-index: 30;
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.15);
}

.more-item {
  text-align: left;
  border: none;
  background: transparent;
  color: var(--color-text);
  padding: 0.55rem 0.75rem;
  cursor: pointer;
}

.more-item:hover {
  background: var(--color-hover);
}

.more-item.danger {
  color: #ef4444;
}

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-panel {
  width: 720px;
  max-width: calc(100vw - 2rem);
  background: var(--color-surface-1);
  border: 1px solid var(--color-border);
  border-radius: 12px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--color-border);
}

.icon-btn {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 1.25rem;
  cursor: pointer;
}

.modal-loading {
  padding: 2rem 1.25rem;
  color: var(--color-text-secondary);
}

.modal-body {
  padding: 1rem 1.25rem;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface-2);
  font-size: 0.85rem;
}

.detail-item.full {
  grid-column: 1 / -1;
}

.detail-item > span:first-child {
  color: var(--color-text-secondary);
}

.detail-item code {
  word-break: break-all;
}

.deps-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.deps-list code {
  background: var(--color-surface-3);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 0.15rem 0.35rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  padding: 0.9rem 1.25rem 1.1rem;
  border-top: 1px solid var(--color-border);
}
</style>
