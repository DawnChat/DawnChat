import { ref } from 'vue'
import type { ThemeMode } from '@/shared/types/common'
import { setNativeTheme } from '../adapters/theme'

const THEME_STORAGE_KEY = 'dawnchat-theme'

// 全局主题状态
const theme = ref<ThemeMode>('dark') // 默认深色模式

// 从 localStorage 加载主题
const loadTheme = (): ThemeMode => {
  const stored = localStorage.getItem(THEME_STORAGE_KEY) as ThemeMode | null
  return stored || 'dark'
}

// 应用主题到 DOM
const applyTheme = (mode: ThemeMode) => {
  const root = document.documentElement
  if (mode === 'dark') {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }
}

// 初始化主题
const initTheme = () => {
  theme.value = loadTheme()
  applyTheme(theme.value)
  // 同步原生窗口主题
  setNativeTheme(theme.value)
}

export function useTheme() {
  // 切换主题
  const toggleTheme = () => {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    localStorage.setItem(THEME_STORAGE_KEY, theme.value)
    applyTheme(theme.value)
    // 同步原生窗口主题
    setNativeTheme(theme.value)
  }

  // 设置主题
  const setTheme = (mode: ThemeMode) => {
    theme.value = mode
    localStorage.setItem(THEME_STORAGE_KEY, mode)
    applyTheme(mode)
    // 同步原生窗口主题
    setNativeTheme(mode)
  }

  return {
    theme,
    toggleTheme,
    setTheme,
    initTheme
  }
}
