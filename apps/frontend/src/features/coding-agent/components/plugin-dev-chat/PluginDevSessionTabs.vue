<template>
  <div class="session-tabs-bar">
    <div ref="tabsScrollerRef" class="tabs-scroller" @wheel="handleWheel">
      <button
        v-for="session in sessions"
        :key="session.id"
        class="session-tab"
        :class="{ active: session.id === activeSessionId }"
        type="button"
        @click="emit('switch-session', session.id)"
      >
        <span class="session-title">{{ session.title }}</span>
      </button>
    </div>

    <div class="tabs-actions">
      <button class="icon-btn create-session-btn" type="button" :title="labels.newSession" @click="emit('create-session')">+</button>
      <div ref="historyWrapRef" class="history-wrap">
        <button class="icon-btn" type="button" :title="labels.historySessions" @click="toggleHistory">
          {{ labels.history }}
        </button>
        <div v-if="historyOpen" class="history-popover">
          <button
            v-for="session in sessions"
            :key="`history-${session.id}`"
            class="history-item"
            :class="{ active: session.id === activeSessionId }"
            type="button"
            @click="handlePickHistory(session.id)"
          >
            <span class="history-title">{{ session.title }}</span>
            <span class="history-time">{{ formatTime(session.updatedAt || session.createdAt) }}</span>
          </button>
          <div v-if="sessions.length === 0" class="history-empty">{{ labels.noSessions }}</div>
        </div>
      </div>
      <div v-if="showSettingsButton" ref="settingsWrapRef" class="settings-wrap">
        <button
          class="icon-btn icon-btn-settings"
          :class="{ active: settingsOpen }"
          type="button"
          :title="labels.runtimeSettings"
          @click="toggleSettings"
        >
          <Settings2 class="settings-icon" aria-hidden="true" />
        </button>
        <div v-if="settingsOpen" class="settings-popover">
          <div v-if="engineSelectOptions.length > 0" class="settings-field settings-field-engine">
            <div class="settings-label">{{ labels.engine }}</div>
            <PluginDevInlineSelect
              :model-value="selectedEngine"
              :options="engineSelectOptions"
              :selected-status="selectedEngineHealthStatus || null"
              :selected-status-title="selectedEngineHealthTitle"
              label="Engine"
              @update:model-value="(value) => emit('select-engine', value)"
            />
          </div>
          <div v-if="agentSelectOptions.length > 0" class="settings-field settings-field-mode">
            <div class="settings-label">{{ labels.mode }}</div>
            <PluginDevInlineSelect
              :model-value="selectedAgent"
              :options="agentSelectOptions"
              label="Mode"
              @update:model-value="(value) => emit('select-agent', value)"
            />
          </div>
          <div v-if="ttsEngineSelectOptions.length > 0" class="settings-field settings-field-tts">
            <div class="settings-label">{{ labels.ttsEngine }}</div>
            <PluginDevInlineSelect
              :model-value="selectedTtsEngine"
              :options="ttsEngineSelectOptions"
              label="TTS"
              @update:model-value="(value) => emit('select-tts-engine', value)"
            />
          </div>
          <div v-if="showTtsControl" class="settings-field settings-field-tts-switch">
            <div class="settings-label">{{ labels.ttsVoiceSwitch || '语音播报' }}</div>
            <PluginDevInlineSelect
              :model-value="ttsEnabled ? 'on' : 'off'"
              :options="[{value: 'on', label: '开启'}, {value: 'off', label: '关闭'}]"
              label="语音播报"
              @update:model-value="(val) => {
                if ((val === 'on') !== ttsEnabled) {
                  emit('toggle-tts-enabled')
                }
              }"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Settings2 } from 'lucide-vue-next'
import { useI18n } from '@/composables/useI18n'
import PluginDevInlineSelect, { type PluginDevInlineSelectOption } from '@/features/coding-agent/components/plugin-dev-chat/PluginDevInlineSelect.vue'

interface SessionMetaLite {
  id: string
  title: string
  createdAt?: string
  updatedAt?: string
}

interface EngineOption {
  id: string
  label: string
}

interface AgentOption {
  id: string
  label?: string
  description?: string
}

interface TtsEngineOption {
  id: string
  label: string
}

const props = withDefaults(defineProps<{
  sessions: SessionMetaLite[]
  activeSessionId: string
  selectedEngine?: string
  selectedEngineHealthStatus?: 'checking' | 'healthy' | 'unhealthy' | null
  selectedEngineHealthTitle?: string
  selectedAgent?: string
  selectedTtsEngine?: string
  engineOptions?: EngineOption[]
  availableAgents?: AgentOption[]
  ttsEngineOptions?: TtsEngineOption[]
  showTtsControl?: boolean
  ttsEnabled?: boolean
  isTtsActive?: boolean
}>(), {
  selectedEngine: '',
  selectedEngineHealthStatus: null,
  selectedEngineHealthTitle: '',
  selectedAgent: '',
  selectedTtsEngine: 'system',
  engineOptions: () => [],
  availableAgents: () => [],
  ttsEngineOptions: () => [],
  showTtsControl: false,
  ttsEnabled: false,
  isTtsActive: false
})

const emit = defineEmits<{
  'switch-session': [sessionId: string]
  'create-session': []
  'select-engine': [value: string]
  'select-agent': [value: string]
  'select-tts-engine': [value: string]
  'toggle-tts-enabled': []
}>()

const tabsScrollerRef = ref<HTMLElement | null>(null)
const historyWrapRef = ref<HTMLElement | null>(null)
const settingsWrapRef = ref<HTMLElement | null>(null)
const historyOpen = ref(false)
const settingsOpen = ref(false)
const { t } = useI18n()

const labels = computed(() => {
  const apps = (t.value as any).apps || {}
  return {
    newSession: String(apps.newSession || '新会话'),
    history: String(apps.history || '历史'),
    historySessions: String(apps.historySessions || '历史会话'),
    noSessions: String(apps.noSessions || '暂无会话'),
    runtimeSettings: String(apps.runtimeSettings || 'Agent 设置'),
    engine: String(apps.engine || '运行引擎'),
    mode: String(apps.mode || '运行模式'),
    ttsEngine: String(apps.ttsEngine || 'TTS 引擎'),
    ttsVoiceSwitch: String(apps.ttsVoiceSwitch || '语音播报')
  }
})
const showSettingsButton = computed(() => props.engineOptions.length > 0 || props.availableAgents.length > 0 || props.ttsEngineOptions.length > 0)
const engineSelectOptions = computed<PluginDevInlineSelectOption[]>(() => {
  return props.engineOptions.map((engine) => ({
    value: engine.id,
    label: engine.label,
    title: engine.label
  }))
})
const agentSelectOptions = computed<PluginDevInlineSelectOption[]>(() => {
  return props.availableAgents.map((agent) => ({
    value: agent.id,
    label: agent.label || agent.id,
    title: agent.description || agent.label || agent.id,
    description: agent.description || ''
  }))
})
const ttsEngineSelectOptions = computed<PluginDevInlineSelectOption[]>(() => {
  return props.ttsEngineOptions.map((engine) => ({
    value: engine.id,
    label: engine.label,
    title: engine.label
  }))
})

const handleWheel = (event: WheelEvent) => {
  const target = tabsScrollerRef.value
  if (!target) return
  if (Math.abs(event.deltaY) < 1) return
  target.scrollLeft += event.deltaY
  event.preventDefault()
}

const handlePickHistory = (sessionId: string) => {
  historyOpen.value = false
  emit('switch-session', sessionId)
}

const toggleHistory = () => {
  historyOpen.value = !historyOpen.value
  if (historyOpen.value) {
    settingsOpen.value = false
  }
}

const toggleSettings = () => {
  settingsOpen.value = !settingsOpen.value
  if (settingsOpen.value) {
    historyOpen.value = false
  }
}

const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as Node | null
  if (!target) return
  if (target instanceof Element && target.closest('.inline-select-menu')) {
    return
  }
  const historyWrap = historyWrapRef.value
  const settingsWrap = settingsWrapRef.value
  if (historyOpen.value && historyWrap && !historyWrap.contains(target)) {
    historyOpen.value = false
  }
  if (settingsOpen.value && settingsWrap && !settingsWrap.contains(target)) {
    settingsOpen.value = false
  }
}

const formatTime = (value?: string) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString()
}

onMounted(() => {
  window.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  window.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.session-tabs-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border-bottom: 1px solid var(--color-border);
  padding: 0.55rem 0.75rem;
}

.tabs-scroller {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.tabs-scroller::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}

.session-tab {
  flex: 0 0 auto;
  max-width: 220px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  border-radius: 8px;
  padding: 0.32rem 0.6rem;
  color: var(--color-text-secondary);
  font-size: 0.78rem;
  cursor: pointer;
}

.session-tab.active {
  color: var(--color-text);
  border-color: color-mix(in srgb, var(--color-primary) 55%, var(--color-border-strong));
  background: color-mix(in srgb, var(--color-primary) 12%, var(--color-surface-2));
}

.session-title {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tabs-actions {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.icon-btn {
  height: 28px;
  min-width: 30px;
  border: 1px solid var(--color-border);
  border-radius: 7px;
  background: var(--color-surface-2);
  color: var(--color-text);
  font-size: 0.76rem;
  padding: 0 0.5rem;
  cursor: pointer;
}

.icon-btn.active {
  border-color: color-mix(in srgb, var(--color-primary) 55%, var(--color-border-strong));
  background: color-mix(in srgb, var(--color-primary) 12%, var(--color-surface-2));
  color: var(--color-primary);
}

.icon-btn-settings {
  padding: 0 0.42rem;
}

.settings-icon {
  width: 14px;
  height: 14px;
}

.settings-wrap,
.history-wrap {
  position: relative;
}

.settings-popover,
.history-popover {
  position: absolute;
  top: calc(100% + 0.35rem);
  right: 0;
  border: 1px solid var(--color-border-strong);
  border-radius: 8px;
  background: var(--color-surface-3);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.28);
  z-index: 20;
}

.settings-popover {
  width: 272px;
  padding: 0.7rem;
  display: flex;
  flex-direction: column;
  gap: 0.68rem;
}

.settings-field {
  display: flex;
  flex-direction: column;
  gap: 0.38rem;
}

.settings-label {
  font-size: 0.72rem;
  color: var(--color-text-secondary);
}

.settings-field :deep(.inline-select-trigger) {
  width: 100%;
}

.settings-field :deep(.inline-select-label) {
  max-width: 10rem;
}

.history-popover {
  width: 320px;
  max-height: 320px;
  overflow: auto;
  padding: 0.35rem;
}

.history-item {
  width: 100%;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 6px;
  text-align: left;
  padding: 0.42rem 0.48rem;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.22rem;
}

.history-item:hover {
  background: color-mix(in srgb, var(--color-surface-2) 85%, var(--color-surface-3));
}

.history-item.active {
  border-color: color-mix(in srgb, var(--color-primary) 45%, var(--color-border-strong));
  background: color-mix(in srgb, var(--color-primary) 14%, var(--color-surface-3));
}

.history-title {
  font-size: 0.82rem;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-time {
  font-size: 0.72rem;
  color: var(--color-text-secondary);
}

.history-empty {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
  padding: 0.45rem;
}


</style>
