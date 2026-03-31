<template>
  <div class="workbench-header">
    <div class="workbench-left">
      <div class="workbench-meta">
        <span class="workbench-title">{{ activeAppName || pluginId }}</span>
        <span v-if="appTypeLabel" class="workbench-badge">{{ appTypeLabel }}</span>
      </div>
      <div v-if="showModeSwitch" class="mode-switch">
        <button
          class="mode-btn"
          :class="{ active: workbenchMode === 'requirements' }"
          @click="emit('switchMode', 'requirements')"
        >
          {{ requirementsModeLabel }}
        </button>
        <button class="mode-btn" :class="{ active: workbenchMode === 'agent' }" @click="emit('switchMode', 'agent')">
          {{ agentModeLabel }}
        </button>
      </div>
    </div>
    <div class="workbench-actions">
      <span v-if="isBuildRunning" class="build-status">{{ buildRunningLabel }}</span>
      <button
        v-if="hasBuildSession"
        class="secondary-btn ui-btn ui-btn--neutral"
        @click="emit('openBuildSession')"
      >
        {{ openBuildSessionLabel }}
      </button>
      <button
        v-if="isMobileApp"
        class="secondary-btn ui-btn ui-btn--neutral"
        @click="emit('openMobileOffline')"
      >
        {{ mobileOfflineUploadLabel }}
      </button>
      <button v-if="isMobileApp" class="publish-btn ui-btn ui-btn--emphasis" @click="emit('openMobileQr')">
        {{ mobilePreviewQrLabel }}
      </button>
      <button v-if="isWebApp" class="publish-btn ui-btn ui-btn--emphasis" @click="emit('openWebPublish')">
        {{ publishWebLabel }}
      </button>
      <button class="secondary-btn ui-btn ui-btn--danger close-btn" @click="emit('close')">
        {{ closeLabel }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  activeAppName: string
  pluginId: string
  appTypeLabel: string
  isWebApp: boolean
  isMobileApp: boolean
  showModeSwitch: boolean
  workbenchMode: 'requirements' | 'agent'
  requirementsModeLabel: string
  agentModeLabel: string
  buildRunningLabel: string
  openBuildSessionLabel: string
  isBuildRunning: boolean
  hasBuildSession: boolean
  publishWebLabel: string
  mobilePreviewQrLabel: string
  mobileOfflineUploadLabel: string
  closeLabel: string
}>()

const emit = defineEmits<{
  openWebPublish: []
  openMobileQr: []
  openMobileOffline: []
  switchMode: [mode: 'requirements' | 'agent']
  openBuildSession: []
  close: []
}>()
</script>

<style scoped>
.workbench-header {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--wb-border-strong);
  background: var(--wb-pane-side);
  box-shadow: var(--wb-inset-shadow);
}

.workbench-left {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.workbench-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.workbench-title {
  font-weight: 600;
  color: var(--color-text);
}

.workbench-badge {
  border: 1px solid var(--color-primary);
  color: var(--color-primary);
  border-radius: 999px;
  padding: 0.2rem 0.55rem;
  font-size: 0.75rem;
}

.mode-switch {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--wb-border-subtle);
  border-radius: 9px;
  padding: 2px;
  background: var(--wb-pane-chrome);
}

.mode-btn {
  min-height: 28px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--color-text-secondary);
  padding: 0 0.7rem;
  cursor: pointer;
}

.mode-btn.active {
  color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
}

.workbench-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.publish-btn {
  border-radius: 10px;
  padding: 0.55rem 0.95rem;
  min-height: 34px;
  font-weight: 600;
}

.secondary-btn {
  border-radius: 10px;
  padding: 0.55rem 0.95rem;
  min-height: 34px;
  font-weight: 600;
}

.close-btn {
  margin-left: 0.25rem;
}

.build-status {
  font-size: 0.75rem;
  color: var(--color-primary);
  white-space: nowrap;
}
</style>
