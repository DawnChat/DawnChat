<template>
  <nav class="the-dock">
    <div class="dock-content">
      <!-- Logo -->
      <div class="dock-logo">
        <div class="logo-icon">
          <img src="/logo.svg" alt="Logo" class="dock-logo-img" width="32" height="32" />
        </div>
      </div>

      <!-- 导航图标 -->
      <div class="dock-nav">
        <button
          v-for="item in navItems"
          :key="item.id"
          :class="['dock-item', { active: currentSpace === item.id, 'ui-selected': currentSpace === item.id }]"
          :title="item.label"
          @click="handleSpaceChange(item.id as SpaceType)"
        >
          <component :is="item.icon" :size="24" :stroke-width="iconStrokeWidth" class="dock-icon" />
          <span class="dock-label">{{ item.label }}</span>
        </button>
      </div>

      <!-- 底部用户区 -->
      <div class="dock-user">
        <!-- 环境管理入口 -->
        <!-- <button
          class="dock-item"
          :class="{ 'has-downloads': activeDownloadCount > 0 }"
          :title="t.nav.environment"
          @click="handleOpenEnvironmentManager"
        >
          <Download :size="24" :stroke-width="iconStrokeWidth" class="dock-icon" />
          <span v-if="activeDownloadCount > 0" class="download-badge">{{ activeDownloadCount }}</span>
          <span class="dock-label">{{ t.nav.environment }}</span>
        </button> -->

        <!-- 主题切换 -->
        <button
          class="dock-item"
          :title="theme === 'dark' ? t.settings.lightMode : t.settings.darkMode"
          @click="toggleTheme"
        >
          <component :is="theme === 'dark' ? Sun : Moon" :size="24" :stroke-width="iconStrokeWidth" class="dock-icon" />
        </button>

        <!-- 用户头像和登出 -->
        <div class="user-menu" ref="userMenuRef">
          <button 
            class="dock-item user-avatar" 
            :title="user?.email || 'User'"
            @click="showUserMenu = !showUserMenu"
          >
            <span class="dock-icon" v-if="user?.avatar_url">
              <img :src="user.avatar_url" alt="User" class="avatar-img" />
            </span>
            <UserIcon v-else :size="24" :stroke-width="iconStrokeWidth" class="dock-icon" />
          </button>
          
          <!-- 用户菜单 -->
          <div v-if="showUserMenu" class="user-dropdown">
            <div class="user-info">
              <div class="user-name">{{ user?.name || user?.email }}</div>
              <div class="user-email">{{ user?.email }}</div>
            </div>
            <button @click="handleLogout" class="logout-btn">
              <LogOut :size="16" style="margin-right: 8px" /> {{ t.auth.logout }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { SpaceType, NavigationItem } from '@/shared/types/common'
import { useI18n } from '@/composables/useI18n'
import { useTheme } from '@/composables/useTheme'
import { useClickOutside } from '@/composables/useClickOutside'
import { 
  Smartphone, 
  Settings, 
  Sun, 
  Moon, 
  User as UserIcon, 
  LogOut 
} from 'lucide-vue-next'

interface User {
  id: string
  email: string
  name?: string
  avatar_url?: string
}

defineProps<{
  currentSpace: SpaceType
  user?: User | null
}>()

const emit = defineEmits<{
  'change-space': [space: SpaceType]
  'logout': []
  'resume-dev': []
}>()

const { t } = useI18n()
const { theme, toggleTheme } = useTheme()
// const environmentStore = useEnvironmentStore()

const iconStrokeWidth = ref(1.5)

// const activeDownloadCount = computed(() => environmentStore.activeDownloadCount)

const showUserMenu = ref(false)
const userMenuRef = ref<HTMLElement | null>(null)

// 点击外部关闭菜单
useClickOutside(userMenuRef, () => {
  showUserMenu.value = false
})

const handleSpaceChange = (space: SpaceType) => {
  emit('change-space', space)
}

const handleLogout = () => {
  showUserMenu.value = false
  emit('logout')
}

// const handleOpenEnvironmentManager = () => {
//   environmentStore.openEnvironmentManager()
// }

const navItems = computed<NavigationItem[]>(() => [
  // { id: 'workbench', icon: Sparkles, label: t.value.nav.workbench },
  // { id: 'agents', icon: Bot, label: t.value.nav.agents },
  // { id: 'workflows', icon: Zap, label: t.value.nav.workflows },
  // { id: 'pipeline', icon: GitBranch, label: t.value.nav.pipeline },
  // { id: 'tools', icon: Wrench, label: t.value.nav.tools },
  // { id: 'models', icon: Package, label: t.value.nav.models },
  { id: 'apps', icon: Smartphone, label: t.value.nav.apps },
  { id: 'settings', icon: Settings, label: t.value.nav.settings }
])
</script>

<style scoped>
.the-dock {
  width: 3.5rem; /* 56px */
  height: 100vh;
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.dock-content {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0.5rem 0;
}

.dock-logo {
  padding: 0.5rem;
  display: flex;
  justify-content: center;
  margin-bottom: 1rem;
}

.dock-logo-img {
  width: 32px;
  height: 32px;
}


.avatar-img {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  object-fit: cover;
}

.logo-icon {
  font-size: 1.75rem;
  cursor: pointer;
  transition: transform 0.15s ease-in-out;
  position: relative;
}

.logo-icon:hover {
  transform: scale(1.1);
}

.dock-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0 0.25rem;
}

.dock-user {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0 0.25rem;
  border-top: 1px solid var(--color-border);
  padding-top: 0.5rem;
}

.dock-item {
  width: 100%;
  height: 2.75rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: 0.5rem;
  transition: all 0.15s ease-in-out;
  position: relative;
  overflow: hidden;
}

.dock-item:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
  transform: translateY(-2px);
}

.dock-icon {
  font-size: 1.5rem;
  line-height: 1;
}

.dock-label {
  display: none;
  position: absolute;
  left: calc(100% + 0.5rem);
  background: var(--color-bg-secondary);
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  white-space: nowrap;
  font-size: 0.875rem;
  box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  pointer-events: none;
  z-index: 1000;
}

.dock-item:hover .dock-label {
  display: block;
}

.user-menu {
  position: relative;
}

.user-avatar {
  position: relative;
}

.user-dropdown {
  position: absolute;
  bottom: 100%;
  left: 100%;
  margin-left: 0.5rem;
  margin-bottom: 0.5rem;
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 200px;
  z-index: 1000;
}

.user-info {
  padding: 1rem;
  border-bottom: 1px solid var(--color-border);
}

.user-name {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--color-text);
  margin-bottom: 0.25rem;
}

.user-email {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.logout-btn {
  width: 100%;
  padding: 0.75rem 1rem;
  border: none;
  background: transparent;
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
  font-size: 0.9rem;
  transition: background 0.2s;
}

.logout-btn:hover {
  background: var(--color-hover);
}

/* 下载按钮样式 */
.dock-item.has-downloads {
  color: var(--color-primary);
}

.download-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: var(--color-danger, #ef4444);
  color: white;
  border-radius: 8px;
  font-size: 0.65rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.avatar-img {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  object-fit: cover;
}
</style>
