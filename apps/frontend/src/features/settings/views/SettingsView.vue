<template>
  <div class="settings-view">
    <component :is="currentSettingComponent" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import GeneralSettings from './GeneralSettings.vue'
import CloudModelsSettings from './CloudModelsSettings.vue'
import NetworkSettings from './NetworkSettings.vue'
import AboutSettings from './AboutSettings.vue'

interface Props {
  section?: string
}

const props = defineProps<Props>()

const currentSettingComponent = computed(() => {
  switch (props.section) {
    case 'general':
      return GeneralSettings
    case 'cloud-models':
      return CloudModelsSettings
    case 'network':
      return NetworkSettings
    case 'about':
      return AboutSettings
    default:
      return GeneralSettings
  }
})
</script>

<style scoped>
.settings-view {
  height: 100%;
  overflow: auto;
}
</style>
