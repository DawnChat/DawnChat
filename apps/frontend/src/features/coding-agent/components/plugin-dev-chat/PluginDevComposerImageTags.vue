<template>
  <div v-if="images.length > 0" class="image-tags" role="list" aria-label="已附加图片">
    <div
      v-for="(image, index) in images"
      :key="buildImageKey(image, index)"
      class="image-tag"
      role="listitem"
    >
      <button
        class="image-preview-btn"
        type="button"
        :title="buildPreviewTitle(image, index)"
        @click="handlePreview(index, $event)"
      >
        <img class="image-thumb" :src="image.url" :alt="buildAlt(image, index)" />
        <span class="image-name">{{ displayName(image, index) }}</span>
      </button>
      <button
        class="image-remove-btn"
        type="button"
        :title="`移除 ${displayName(image, index)}`"
        :aria-label="`移除 ${displayName(image, index)}`"
        @click="emit('remove', index)"
      >
        ×
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PromptFilePart } from '@/services/coding-agent/engineAdapter'

defineProps<{
  images: PromptFilePart[]
}>()

const emit = defineEmits<{
  preview: [payload: { index: number; anchorEl: HTMLElement | null }]
  remove: [index: number]
}>()

const displayName = (image: PromptFilePart, index: number): string => {
  const name = String(image.filename || '').trim()
  if (name) return name
  return `image-${index + 1}`
}

const buildImageKey = (image: PromptFilePart, index: number): string => {
  return `${displayName(image, index)}:${String(image.mime || '')}:${index}`
}

const buildPreviewTitle = (image: PromptFilePart, index: number): string => {
  return `预览 ${displayName(image, index)}`
}

const buildAlt = (image: PromptFilePart, index: number): string => {
  return `附件图片 ${displayName(image, index)}`
}

const handlePreview = (index: number, event: MouseEvent) => {
  const target = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  emit('preview', { index, anchorEl: target })
}
</script>

<style scoped>
.image-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-bottom: 0.55rem;
}

.image-tag {
  display: inline-flex;
  align-items: center;
  max-width: min(100%, 19rem);
  border: 1px solid color-mix(in srgb, var(--color-primary) 28%, var(--color-border));
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-primary) 8%, var(--color-surface-2));
  overflow: hidden;
}

.image-preview-btn {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 0.45rem;
  border: none;
  background: transparent;
  color: var(--color-text);
  height: 30px;
  padding: 0 0.5rem 0 0.28rem;
  cursor: pointer;
}

.image-preview-btn:hover {
  background: color-mix(in srgb, var(--color-primary) 12%, transparent);
}

.image-thumb {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--color-border) 80%, transparent);
  object-fit: cover;
  flex: 0 0 auto;
}

.image-name {
  min-width: 0;
  font-size: 0.76rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.image-remove-btn {
  width: 28px;
  height: 30px;
  flex: 0 0 auto;
  border: none;
  border-left: 1px solid color-mix(in srgb, var(--color-border) 84%, transparent);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
  line-height: 1;
  cursor: pointer;
}

.image-remove-btn:hover {
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
}
</style>
