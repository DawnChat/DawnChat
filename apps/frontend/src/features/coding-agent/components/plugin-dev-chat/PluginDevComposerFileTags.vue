<template>
  <div v-if="files.length > 0" class="file-tags" role="list" :aria-label="tagsAriaLabel">
    <div
      v-for="(file, index) in files"
      :key="`${file.name}:${file.size}:${index}`"
      class="file-tag"
      role="listitem"
    >
      <span class="file-name" :title="file.name">{{ file.name }}</span>
      <button
        class="file-remove-btn"
        type="button"
        :title="`${removeLabelPrefix} ${file.name}`"
        :aria-label="`${removeLabelPrefix} ${file.name}`"
        @click="emit('remove', index)"
      >
        ×
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface ComposerPendingFileTag {
  name: string
  size: number
}

defineProps<{
  files: ComposerPendingFileTag[]
  tagsAriaLabel: string
  removeLabelPrefix: string
}>()

const emit = defineEmits<{
  remove: [index: number]
}>()
</script>

<style scoped>
.file-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-bottom: 0.55rem;
}

.file-tag {
  display: inline-flex;
  align-items: center;
  max-width: min(100%, 24rem);
  border: 1px solid color-mix(in srgb, var(--color-border-strong) 78%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--color-surface-2) 88%, transparent);
  overflow: hidden;
}

.file-name {
  min-width: 0;
  font-size: 0.76rem;
  line-height: 1.2;
  padding: 0.4rem 0.55rem;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-remove-btn {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  border: none;
  border-left: 1px solid color-mix(in srgb, var(--color-border) 84%, transparent);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
  line-height: 1;
  cursor: pointer;
}

.file-remove-btn:hover {
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
}
</style>
