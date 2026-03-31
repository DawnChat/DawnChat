<template>
  <div class="project-settings-view">
    <div class="settings-header">
      <h2>{{ t.project.basicInfo }}</h2>
      <button class="back-button" @click="goBack"><ArrowLeft :size="16" class="mr-1 inline-icon" /> {{ t.common.back }}</button>
    </div>

    <div class="settings-content">
      <!-- 项目基本信息 -->
      <div class="setting-section">
        <h3>{{ t.project.basicInfo }}</h3>
        <div class="setting-item">
          <label>{{ t.project.name }}:</label>
          <div class="project-name-editor">
            <input
              v-model.trim="editingName"
              class="project-name-input"
              type="text"
              :placeholder="t.project.unnamed"
            >
            <button
              class="save-name-button"
              type="button"
              :disabled="!canSaveName"
              @click="handleRenameProject"
            >
              {{ t.common.save || '保存' }}
            </button>
          </div>
        </div>
        <div class="setting-item">
          <label>{{ t.project.roomId }}:</label>
          <div class="setting-value setting-value-mono">{{ roomId }}</div>
        </div>
        <div class="setting-item">
          <label>{{ t.project.createTime }}:</label>
          <div class="setting-value">{{ createdAt }}</div>
        </div>
      </div>

      <!-- 危险操作区域 -->
      <div class="setting-section danger-section">
        <h3>{{ t.project.dangerZone }}</h3>
        <div class="danger-description">
          {{ t.project.deleteDesc }}
        </div>
        <button class="delete-button" @click="showDeleteConfirm">
          {{ t.project.delete }}
        </button>
      </div>
    </div>

    <!-- 删除确认对话框 -->
    <ConfirmDialog
      :visible="deleteConfirmVisible"
      :title="t.project.delete"
      :message="t.project.confirmDelete"
      :detail="t.project.deleteDetail"
      :icon="AlertTriangle"
      :confirm-text="t.common.delete"
      :cancel-text="t.common.cancel"
      type="danger"
      :loading="deleteLoading"
      @confirm="handleDeleteProject"
      @cancel="hideDeleteConfirm"
      @update:visible="hideDeleteConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ArrowLeft, AlertTriangle } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'
import type { WorkbenchProject } from '@/stores/workbenchProjectsApi'
import { useWorkbenchProjectsStore } from '@/stores/workbenchProjectsStore'
import { logger } from '@/utils/logger'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'

interface Props {
  roomId?: string | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  back: []
  projectDeleted: [roomId: string]
}>()

const { t, locale } = useI18n()
const workbenchProjectsStore = useWorkbenchProjectsStore()

const deleteConfirmVisible = ref(false)
const deleteLoading = ref(false)
const renameLoading = ref(false)
const roomInfo = ref<WorkbenchProject | null>(null)
const editingName = ref('')

const projectName = computed(() => roomInfo.value?.name || t.value.project.unnamed)
const canSaveName = computed(() => {
  const nextName = editingName.value.trim()
  return Boolean(nextName) && nextName !== String(roomInfo.value?.name || '').trim() && !renameLoading.value
})
const createdAt = computed(() => {
  if (!roomInfo.value?.created_at) return t.value.project.unknown
  return new Date(roomInfo.value.created_at).toLocaleDateString(locale.value === 'zh' ? 'zh-CN' : 'en-US')
})

const goBack = () => {
  emit('back')
}

const showDeleteConfirm = () => {
  deleteConfirmVisible.value = true
}

const hideDeleteConfirm = () => {
  deleteConfirmVisible.value = false
}

const handleDeleteProject = async () => {
  if (!props.roomId) {
    logger.error('❌ 没有房间ID')
    return
  }

  deleteLoading.value = true
  
  try {
    logger.info('🗑️ 开始删除项目:', props.roomId)

    await workbenchProjectsStore.removeProject(props.roomId)
    logger.info('✅ 项目删除成功')
    hideDeleteConfirm()
    emit('projectDeleted', props.roomId)
  } catch (error) {
    logger.error('❌ 删除项目时出错:', error)
    alert(t.value.project.deleteFailed.replace('{error}', String(error)))
  } finally {
    deleteLoading.value = false
  }
}

const handleRenameProject = async () => {
  if (!props.roomId || !canSaveName.value) return
  renameLoading.value = true
  try {
    const updated = await workbenchProjectsStore.renameProject(props.roomId, editingName.value.trim())
    roomInfo.value = updated
  } catch (error) {
    logger.error('❌ 重命名项目失败:', error)
  } finally {
    renameLoading.value = false
  }
}

const loadRoomInfo = async () => {
  if (!props.roomId) {
    logger.warn('⚠️ 没有房间ID')
    return
  }

  try {
    logger.info('📋 加载房间信息:', props.roomId)
    workbenchProjectsStore.ensureSyncListener()
    const project = await workbenchProjectsStore.ensureProject(props.roomId)
    if (project) {
      roomInfo.value = project
      editingName.value = project.name
      logger.info('✅ 房间信息加载成功')
    } else {
      logger.error('❌ 房间信息加载失败: 未找到项目')
    }
  } catch (error) {
    logger.error('❌ 加载房间信息时出错:', error)
  }
}

onMounted(() => {
  loadRoomInfo()
})

watch(projectName, (value) => {
  if (!renameLoading.value) {
    editingName.value = value
  }
})
</script>

<style scoped>
.project-settings-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}

.settings-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--color-border);
}

.settings-header h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text);
}

.back-button {
  background: none;
  border: 1px solid var(--color-border);
  color: var(--color-text);
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.back-button:hover {
  background: var(--color-hover);
}

.settings-content {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.setting-section {
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: var(--color-bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.setting-section h3 {
  margin: 0 0 1rem 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--color-text);
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--color-border-light);
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: 500;
  color: var(--color-text);
  min-width: 100px;
}

.setting-value {
  color: var(--color-text-secondary);
  font-size: 0.95rem;
}

.project-name-editor {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.project-name-input {
  width: 280px;
  max-width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--color-text);
  padding: 0.5rem 0.75rem;
}

.save-name-button {
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--color-text);
  padding: 0.5rem 0.85rem;
  cursor: pointer;
}

.save-name-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.setting-value-mono {
  font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
  background: var(--color-bg);
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.85rem;
  word-break: break-all;
}

.danger-section {
  border-color: #ff6b6b;
  background: rgba(255, 107, 107, 0.05);
}

.danger-section h3 {
  color: #ff6b6b;
}

.danger-description {
  color: #ff6b6b;
  font-size: 0.9rem;
  margin-bottom: 1rem;
  line-height: 1.5;
}

.delete-button {
  background: #ff6b6b;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.delete-button:hover {
  background: #ff5252;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(255, 107, 107, 0.3);
}

.delete-button:active {
  transform: translateY(0);
}
</style>
