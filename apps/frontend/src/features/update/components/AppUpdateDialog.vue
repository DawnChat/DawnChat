<template>
  <ConfirmDialog
    :visible="visible"
    icon="⬆️"
    :title="dialogTitle"
    :message="dialogMessage"
    :detail="detail"
    :confirm-text="downloadText"
    :cancel-text="laterText"
    :close-on-overlay="mode !== 'forced'"
    :show-cancel="mode !== 'forced'"
    :type="mode === 'forced' ? 'danger' : 'default'"
    @confirm="$emit('download')"
    @cancel="$emit('later')"
    @update:visible="$emit('update:visible', $event)"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import { useI18n } from '@/composables/useI18n'

interface Props {
  visible: boolean
  mode: 'recommended' | 'forced'
  latestVersion: string | null
  detail?: string
}

const props = withDefaults(defineProps<Props>(), {
  detail: ''
})

defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'download'): void
  (e: 'later'): void
}>()

const { t } = useI18n()

const dialogTitle = computed(() =>
  props.mode === 'forced' ? t.value.update.forceTitle : t.value.update.recommendTitle
)

const dialogMessage = computed(() => {
  const latest = props.latestVersion || t.value.common.unknown
  return props.mode === 'forced'
    ? t.value.update.forceMessage.replace('{version}', latest)
    : t.value.update.recommendMessage.replace('{version}', latest)
})

const downloadText = computed(() => t.value.update.downloadNow)
const laterText = computed(() => t.value.update.later)
</script>
