import { ref, computed } from 'vue'
import type { Locale } from '@/shared/types/common'
import zh from '../locales/zh'
import en from '../locales/en'

const LOCALE_STORAGE_KEY = 'dawnchat-locale'

// 全局语言状态
const locale = ref<Locale>('zh') // 默认中文

// 语言包映射
const messages = {
  zh,
  en
}

// 从 localStorage 加载语言
const loadLocale = (): Locale => {
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY) as Locale | null
  return stored || 'zh'
}

// 初始化语言
const initI18n = () => {
  locale.value = loadLocale()
}

export function useI18n() {
  // 当前翻译
  const t = computed(() => messages[locale.value])

  // 切换语言
  const setLocale = (newLocale: Locale) => {
    locale.value = newLocale
    localStorage.setItem(LOCALE_STORAGE_KEY, newLocale)
  }

  return {
    locale,
    t,
    setLocale,
    initI18n
  }
}

