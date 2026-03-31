<template>
  <div class="general-settings">
    <div class="settings-section">
      <h3 class="section-title">{{ t.settings.theme }}</h3>
      <div class="settings-group">
        <label class="setting-item">
          <span class="setting-label">{{ t.settings.theme }}</span>
          <PluginDevInlineSelect
            :model-value="theme"
            :options="themeOptions"
            :label="t.settings.theme"
            class="setting-select"
            @update:model-value="handleThemeChange"
          />
        </label>
      </div>
    </div>

    <div class="settings-section">
      <h3 class="section-title">{{ t.settings.language }}</h3>
      <div class="settings-group">
        <label class="setting-item">
          <span class="setting-label">{{ t.settings.language }}</span>
          <PluginDevInlineSelect
            :model-value="locale"
            :options="localeOptions"
            :label="t.settings.language"
            class="setting-select"
            @update:model-value="handleLocaleChange"
          />
        </label>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/composables/useI18n'
import { useTheme } from '@/composables/useTheme'
import type { ThemeMode, Locale } from '@/shared/types/common'
import PluginDevInlineSelect from '@/features/coding-agent/components/plugin-dev-chat/PluginDevInlineSelect.vue'

const { t, locale, setLocale } = useI18n()
const { theme, setTheme } = useTheme()

const themeOptions = computed(() => [
  { value: 'dark', label: t.value.theme.dark },
  { value: 'light', label: t.value.theme.light }
])

const localeOptions = computed(() => [
  { value: 'zh', label: t.value.language.zh },
  { value: 'en', label: t.value.language.en }
])

const handleThemeChange = (value: string) => {
  setTheme(value as ThemeMode)
}

const handleLocaleChange = (value: string) => {
  setLocale(value as Locale)
}
</script>

<style scoped>
.general-settings {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  padding: 1.5rem;
}

.settings-section {
  padding-bottom: 2rem;
  border-bottom: 1px solid var(--color-border);
}

.settings-section:last-child {
  border-bottom: none;
}

.section-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 1rem 0;
}

.settings-group {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
}

.setting-item.toggle-item {
  align-items: flex-start;
}

.setting-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.setting-label {
  font-size: 1rem;
  color: var(--color-text-primary);
}

.setting-desc {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.setting-select {
  width: 220px;
  flex-shrink: 0;
}

/* Toggle Switch */
.toggle-switch {
  position: relative;
  width: 48px;
  height: 26px;
  background: var(--color-bg-tertiary, #e0e0e0);
  border: none;
  border-radius: 13px;
  cursor: pointer;
  transition: background-color 0.2s ease;
  flex-shrink: 0;
}

.toggle-switch.active {
  background: var(--color-primary);
}

.toggle-slider {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 20px;
  height: 20px;
  background: white;
  border-radius: 50%;
  transition: transform 0.2s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.toggle-switch.active .toggle-slider {
  transform: translateX(22px);
}

/* Setting Note */
.setting-note {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: var(--color-bg-secondary);
  border-radius: 0.5rem;
  margin-top: 0.5rem;
}

.note-icon {
  flex-shrink: 0;
}

.note-text {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
</style>
