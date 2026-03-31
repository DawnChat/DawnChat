/**
 * @deprecated 请改用 ./modelHubStore；此兼容层将在后续清理阶段移除。
 */
import { REPO_DOWNLOAD_FILENAME, useModelHubStore } from '@/stores/modelHubStore'

export { useModelHubStore, REPO_DOWNLOAD_FILENAME }
export const useModelsStore = useModelHubStore
export type {
  ModelFormat,
  HuggingFaceModel,
  HuggingFaceFileSibling,
  InstalledModel,
  DownloadTask,
  PendingDownload,
  ModelSource
} from '@/stores/modelHubStore'
