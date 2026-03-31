<template>
  <PluginDevPartText v-if="item.type === 'text'" :text="item.text" />
  <PluginDevPartTool
    v-else-if="item.type === 'tool'"
    :tool="item.tool"
    :status="item.status"
    :text="item.text"
    :display="item.toolDisplay"
  />
  <PluginDevPartReasoning
    v-else-if="item.type === 'reasoning'"
    :text="item.text"
    :expanded="reasoningExpanded"
    @toggle="emit('toggle-reasoning')"
  />
  <PluginDevPartStep v-else-if="item.type === 'step'" :text="item.text" />
  <PluginDevPartUnknown v-else :text="item.text" />
</template>

<script setup lang="ts">
import PluginDevPartText from '@/features/coding-agent/components/plugin-dev-chat/PluginDevPartText.vue'
import PluginDevPartTool from '@/features/coding-agent/components/plugin-dev-chat/PluginDevPartTool.vue'
import PluginDevPartReasoning from '@/features/coding-agent/components/plugin-dev-chat/PluginDevPartReasoning.vue'
import PluginDevPartStep from '@/features/coding-agent/components/plugin-dev-chat/PluginDevPartStep.vue'
import PluginDevPartUnknown from '@/features/coding-agent/components/plugin-dev-chat/PluginDevPartUnknown.vue'

interface RenderItem {
  id: string
  type: 'text' | 'tool' | 'reasoning' | 'step' | 'unknown'
  text?: string
  tool?: string
  status?: string
  toolDisplay?: {
    kind: string
    renderMode?: 'inline' | 'collapsible'
    toolName?: string
    argsText?: string
    argsPreview?: string
    hasDetails?: boolean
    title: string
    summary: string
    detailBody?: string
    detailsText?: string
    command: string
    outputTail: string
    diffStat: string
    patchPreview: string
    languageHint?: string
    codeLines?: string[]
    previewLineCount?: number
    hiddenLineCount?: number
  }
}

defineProps<{
  item: RenderItem
  reasoningExpanded: boolean
}>()

const emit = defineEmits<{
  'toggle-reasoning': []
}>()
</script>
