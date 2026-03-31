<template>
  <div class="navigator-content">
    <!-- 房间列表 -->
    <div class="room-list">
      <div class="list-header">
        
        <div class="header-left">
          <span class="list-title">{{ t.workbench.myProjects }}</span>
          <span class="room-count">{{ stableFilteredRooms.length }}</span>
        </div>
        
        <button 
          class="btn-add-project" 
          @click="handleNewProject"
          :title="t.workbench.newProject"
          :disabled="isCreatingProject"
        >
          <PlusSquare :size="16" />
        </button>
      </div>

      <!-- 加载状态：只在首次加载时显示 -->
      <div v-if="isInitialLoading" class="loading-state">
        <span>{{ t.workbench.loading }}</span>
      </div>

      <!-- 空状态：只在加载完成且无房间时显示 -->
      <div v-else-if="isLoadComplete && stableFilteredRooms.length === 0" class="empty-state">
        <span>{{ t.workbench.noProjectsShort }}</span>
      </div>

      <!-- 房间列表：使用 TransitionGroup 平滑过渡 -->
      <nav v-else class="room-nav" @scroll="handleScroll">
        <TransitionGroup name="room-list">
          <div
            v-for="room in stableFilteredRooms"
            :key="room.id"
            :class="['room-item', { active: props.selectedRoomId === room.id, 'ui-selected': props.selectedRoomId === room.id, 'has-error': room.hasError }]"
            @click="handleRoomClick(room.id)"
          >
            <div class="room-icon">
              <XCircle v-if="room.hasError" :size="16" />
              <Loader2 v-else-if="room.isLoading" :size="16" class="animate-spin" />
              <component v-else :is="room.is_direct ? MessageSquare : Home" :size="16" />
            </div>
            <div class="room-info">
              <div class="room-name">{{ room.displayName }}</div>
              <div v-if="room.hasError" class="room-error">
                {{ room.errorMessage }}
              </div>
              <div v-else-if="room.last_message" class="room-preview">
                {{ truncateMessage(room.last_message) }}
              </div>
            </div>
            <div v-if="room.timestamp" class="room-time">
              {{ formatTime(room.timestamp) }}
            </div>
          </div>
        </TransitionGroup>
        
        <!-- 加载更多指示器 -->
        <div v-if="roomlistLoadingMore" class="loading-more">
          <span>{{ t.workbench.loading }}</span>
        </div>
        <div v-else-if="!roomlistHasMore && stableFilteredRooms.length > 0" class="no-more">
          <span>{{ t.workbench.noMore }}</span>
        </div>
      </nav>
    </div>
  </div>
</template>

<script setup lang="ts">
import { logger } from '@/utils/logger'
import { onMounted, computed, ref, shallowRef, TransitionGroup, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { PlusSquare, XCircle, Loader2, MessageSquare, Home } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'
import { useWorkbenchProjectsStore } from '@/stores/workbenchProjectsStore'

interface Props {
  selectedRoomId?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'select-room': [roomId: string]
  'new-project': []
}>()

const { t } = useI18n()
const workbenchProjectsStore = useWorkbenchProjectsStore()
const { orderedProjects, isLoadingProjects, isCreatingProject } = storeToRefs(workbenchProjectsStore)

interface RoomListItem {
  id: string
  displayName: string
  is_direct: boolean
  roomState?: string
  project_type?: string
  last_message: string
  timestamp: number
  isLoading: boolean
  isReady: boolean
  hasError: boolean
  errorMessage?: string
}

const createRoomListItemFromDto = (dto: {
  id: string
  display_name?: string
  is_direct_message: boolean
  room_state?: string
  last_message_timestamp?: number
  [key: string]: unknown
}) => {
  return {
    id: dto.id,
    displayName: dto.display_name || t.value.room.unnamed,
    is_direct: dto.is_direct_message,
    roomState: dto.room_state,
    last_message: '',
    timestamp: dto.last_message_timestamp || 0,
    isLoading: false,
    isReady: true,
    hasError: false,
  } as RoomListItem
}

const reloadRoomListItem = async (item: RoomListItem) => {
  item.hasError = false
  item.errorMessage = undefined
  item.isReady = true
}

const rooms = ref<RoomListItem[]>([])
const roomlistHasMore = ref(false)
const roomlistLoadingMore = ref(false)
const filteredRooms = computed(() => {
  return rooms.value
    .filter(room => 
      room && 
      room.id && 
      !room.hasError &&
      room.isReady &&
      room.roomState !== 'left'
    )
    .sort((a, b) => b.timestamp - a.timestamp)
})

const loadRoomList = async () => {
  try {
    await workbenchProjectsStore.loadProjects()
  } catch (error) {
    logger.error('❌ 加载项目列表失败:', error)
  }
}

watch(
  orderedProjects,
  (projects) => {
    rooms.value = projects.map(project => {
      const item = createRoomListItemFromDto({
        id: project.id,
        display_name: project.name,
        is_direct_message: false,
        is_public: false,
        is_space: false,
        joined_members_count: 1,
        encryption_state: 'not_encrypted',
        room_state: 'join',
        last_message_timestamp: new Date(project.updated_at || project.created_at || 0).getTime() || 0
      })
      item.project_type = project.project_type
      return item
    })
  },
  { immediate: true }
)

const subscribeRoomlist = async () => {
  await loadRoomList()
  return { 
    success: true, 
    rooms: filteredRooms.value,
    total: filteredRooms.value.length,
    hasMore: false
  }
}

const loadMoreRooms = async () => {
  return
}

// ============ 稳定的房间列表渲染 ============

// 追踪首次加载状态
const hasEverLoaded = ref(false)

// 计算属性：是否为首次加载
const isInitialLoading = computed(() => {
  return isLoadingProjects.value && !hasEverLoaded.value
})

// 计算属性：加载是否完成
const isLoadComplete = computed(() => {
  return hasEverLoaded.value && !isLoadingProjects.value
})

// 稳定的房间列表（避免闪烁）
// 使用 shallowRef 来缓存上一次的有效列表
const cachedRooms = shallowRef<typeof filteredRooms.value>([])

// 计算属性：稳定的过滤后房间列表
const stableFilteredRooms = computed(() => {
  const currentRooms = filteredRooms.value
  
  // 如果当前列表非空，更新缓存
  if (currentRooms.length > 0) {
    cachedRooms.value = currentRooms
    hasEverLoaded.value = true
    return currentRooms
  }
  
  // 如果当前列表为空但有缓存，且正在加载，返回缓存
  if (cachedRooms.value.length > 0 && isLoadingProjects.value) {
    return cachedRooms.value
  }
  
  // 其他情况返回当前列表
  if (currentRooms.length === 0 && !isLoadingProjects.value) {
    hasEverLoaded.value = true
  }
  
  return currentRooms
})

// ============ 生命周期 ============

onMounted(async () => {
  workbenchProjectsStore.ensureSyncListener()
  await subscribeRoomlist()
})

// ============ 事件处理 ============

/**
 * 处理新建项目按钮点击
 */
const handleNewProject = async () => {
  if (isCreatingProject.value) {
    logger.warn('⏳ 正在创建项目，请稍候...')
    return
  }
  
  try {
    logger.info('🆕 点击新建项目按钮')

    logger.info('✨ 创建新的 Workbench 项目...')
    const project = await workbenchProjectsStore.createProject({
      name: t.value.project.defaultName,
      projectType: 'chat'
    })

    logger.info(`✅ Workbench 项目已创建: ${project.id}`)
    await loadRoomList()
    emit('select-room', project.id)
  } catch (error) {
    logger.error('❌ 创建项目失败:', error)
  }
}

const handleRoomClick = (roomId: string) => {
  const room = stableFilteredRooms.value.find(r => r.id === roomId)
  if (room?.hasError) {
    logger.info(`🔄 重试加载房间: ${roomId}`)
    reloadRoomListItem(room)
  } else {
    emit('select-room', roomId)
  }
}

const truncateMessage = (message: string, maxLength = 30) => {
  if (message.length <= maxLength) return message
  return message.substring(0, maxLength) + '...'
}

const formatTime = (timestamp: number) => {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))

  if (days === 0) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } else if (days === 1) {
    return t.value.workbench.time.yesterday
  } else if (days < 7) {
    return t.value.workbench.time.daysAgo.replace('{days}', days.toString())
  } else {
    return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  }
}

const handleScroll = async (event: Event) => {
  const target = event.target as HTMLElement
  if (!target) return
  
  const scrollBottom = target.scrollHeight - target.scrollTop - target.clientHeight
  
  if (scrollBottom < 100 && roomlistHasMore.value && !roomlistLoadingMore.value) {
    logger.info('📄 滚动到底部，加载更多房间')
    await loadMoreRooms()
  }
}
</script>

<style scoped>
.navigator-content {
  padding: 1rem 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  height: 100%;
}

/* 房间列表 */
.room-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 1rem;
  margin-bottom: 0.5rem;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.list-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.room-count {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
  padding: 0.125rem 0.5rem;
  border-radius: 12px;
}

.btn-add-project {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s ease-in-out;
}

.btn-add-project:hover:not(:disabled) {
  background: var(--color-bg-hover);
  color: var(--color-primary);
}

.btn-add-project:active:not(:disabled) {
  transform: scale(0.95);
}

.btn-add-project:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 状态 */
.loading-state,
.empty-state {
  padding: 2rem 1rem;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
}

/* 房间导航 */
.room-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
  padding: 0 0.5rem;
}

.room-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0.5rem;
  cursor: pointer;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--color-text-secondary);
  transition: all 0.15s ease-in-out;
}

.room-item:not(.ui-selected):not(.has-error):hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.room-item.ui-selected {
  background: var(--color-interactive-selected-bg);
  color: var(--color-interactive-selected-fg);
}

.room-item.ui-selected:hover {
  background: var(--color-interactive-selected-bg-hover);
}

.room-item.ui-selected .room-name,
.room-item.ui-selected .room-preview,
.room-item.ui-selected .room-time {
  color: inherit;
}

.room-item.ui-selected .room-preview,
.room-item.ui-selected .room-time {
  opacity: 0.78;
}

.room-item.has-error {
  opacity: 0.7;
  background: var(--color-error-light, rgba(220, 53, 69, 0.1));
}

.room-item.has-error:hover {
  background: var(--color-error-light, rgba(220, 53, 69, 0.15));
}

.room-icon {
  font-size: 1.5rem;
  flex-shrink: 0;
}

.room-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.room-name {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-preview {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-error {
  font-size: 0.75rem;
  color: var(--color-error, #dc3545);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.room-time {
  font-size: 0.7rem;
  color: var(--color-text-secondary);
  flex-shrink: 0;
  align-self: flex-start;
}

/* 加载更多指示器 */
.loading-more,
.no-more {
  padding: 1rem;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 0.85rem;
}

/* 房间列表过渡动画 */
.room-list-move,
.room-list-enter-active,
.room-list-leave-active {
  transition: all 0.3s ease;
}

.room-list-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}

.room-list-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.room-list-leave-active {
  position: absolute;
}
</style>
