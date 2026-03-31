<template>
  <div class="workbench-view-v2">
    <div v-if="!workspaceTarget" class="empty-state">
      <div class="empty-copy">
        <h2>{{ emptyTitle }}</h2>
        <p>{{ emptyDescription }}</p>
      </div>
    </div>

    <template v-else>
      <header class="workbench-header">
        <div class="workspace-meta">
          <h2>{{ workspaceTarget.displayName }}</h2>
          <p>{{ workspaceSubtitle }}</p>
        </div>
        <button class="settings-button" type="button" @click="goToSettings">
          <Settings :size="18" />
        </button>
      </header>

      <div class="chat-shell-wrap">
        <WorkbenchChatPanel
          v-model="chatInput"
          :workspace-target="workspaceTarget"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Settings } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'
import { storeToRefs } from 'pinia'
import type { WorkbenchProject } from '@/stores/workbenchProjectsApi'
import { useWorkbenchProjectsStore } from '@/stores/workbenchProjectsStore'
import { logger } from '@/utils/logger'
import { WorkbenchChatPanel } from '@/features/coding-agent'
import type { WorkspaceTarget } from '@/features/coding-agent'
import { createWorkbenchWorkspaceTarget } from '@/features/coding-agent'

defineOptions({
  name: 'WorkbenchView'
})

interface Props {
  selectedRoomId?: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  navigateToSettings: [roomId: string | null]
  roomCreated: [roomId: string]
}>()

const { t } = useI18n()
const workbenchProjectsStore = useWorkbenchProjectsStore()
const { isLoadingProjects } = storeToRefs(workbenchProjectsStore)
const chatInput = ref('')
const currentProject = ref<WorkbenchProject | null>(null)

const workspaceTarget = computed<WorkspaceTarget | null>(() => {
  if (!currentProject.value) return null
  return createWorkbenchWorkspaceTarget(currentProject.value)
})

const emptyTitle = computed(() => String(t.value.workbench.emptyState.startNew || '开始新的工作区对话'))
const emptyDescription = computed(() => {
  if (isLoadingProjects.value) {
    return String(t.value.workbench.loadingTimeline || '正在加载工作区...')
  }
  return String(t.value.workbench.emptyState.createDesc || '从左侧选择一个项目开始对话。')
})
const workspaceSubtitle = computed(() => {
  const project = currentProject.value
  if (!project) return ''
  const typeLabel = project.project_type === 'chat'
    ? String(t.value.workbench.localProject || '本地项目')
    : project.project_type
  return `${typeLabel} · ${project.id}`
})

async function loadProject(roomId: string | null | undefined) {
  const projectId = String(roomId || '').trim()
  if (!projectId) {
    currentProject.value = null
    return
  }
  try {
    workbenchProjectsStore.ensureSyncListener()
    currentProject.value = await workbenchProjectsStore.ensureProject(projectId)
  } catch (error) {
    logger.error('workbench_v2_load_project_failed', error)
    currentProject.value = null
  }
}

function goToSettings() {
  emit('navigateToSettings', props.selectedRoomId || null)
}

watch(
  () => props.selectedRoomId,
  (roomId) => {
    loadProject(roomId).catch((error) => {
      logger.error('workbench_v2_watch_load_project_failed', error)
    })
  },
  { immediate: true }
)
</script>

<style scoped>
.workbench-view-v2 {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}

.workbench-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-1);
}

.workspace-meta {
  min-width: 0;
}

.workspace-meta h2 {
  margin: 0;
  font-size: 1.1rem;
  color: var(--color-text);
}

.workspace-meta p {
  margin: 0.3rem 0 0;
  font-size: 0.82rem;
  color: var(--color-text-secondary);
}

.settings-button {
  width: 34px;
  height: 34px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-2);
  color: var(--color-text);
  cursor: pointer;
}

.chat-shell-wrap {
  min-height: 0;
  flex: 1 1 auto;
}

.empty-state {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.empty-copy {
  max-width: 420px;
  text-align: center;
}

.empty-copy h2 {
  margin: 0;
  font-size: 1.2rem;
}

.empty-copy p {
  margin: 0.75rem 0 0;
  color: var(--color-text-secondary);
}
</style>
