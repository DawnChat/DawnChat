<template>
  <AppsViewFeature v-bind="$props" />
</template>

<script setup lang="ts">
import AppsViewFeature from '@/features/plugin/views/AppsView.vue'

/**
 * @deprecated 请改用 @/features/plugin/views/AppsView.vue。
 * 该文件为迁移期兼容入口，禁止新增业务逻辑。
 */
defineProps<{
  section?: string
  user?: {
    id: string
    email: string
  } | null
}>()
</script>
