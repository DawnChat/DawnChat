/**
 * @deprecated 请改用 ./llmSelectionStore；此兼容层将在后续清理阶段移除。
 */
import { useLlmSelectionStore } from '@/stores/llmSelectionStore'

export { useLlmSelectionStore }
export const useModelStore = useLlmSelectionStore
export type {
  ModelInfo,
  AvailableModels,
  ModelConfig
} from '@/stores/llmSelectionStore'
