import { computed, ref } from 'vue'
import { useCodingAgentStore } from '@/features/coding-agent/store/codingAgentStore'
import {
  listIwpFiles,
  readIwpFile,
  saveIwpFile,
  type IwpMarkdownFileMeta,
} from '@/services/plugins/iwpWorkbenchApi'
import { createIwpBuildPrompt } from '@/features/plugin-dev-workbench/services/iwpBuildPrompt'
import { OpenCodeSessionBuildExecutor } from '@/features/plugin-dev-workbench/services/iwpBuildExecutor'
import type { InspectorSelectPayload } from '@/types/inspector'

interface BuildUiState {
  status: 'idle' | 'running' | 'success' | 'failed'
  sessionId: string
  stage: string
  message: string
  error: string
}

export const useIwpWorkbenchFlow = (options: { pluginId: () => string; t: any }) => {
  const codingAgentStore = useCodingAgentStore()
  const buildExecutor = new OpenCodeSessionBuildExecutor(codingAgentStore)
  const fileTreeCollapsed = ref(false)
  const centerPaneMode = ref<'markdown' | 'readonly'>('markdown')
  const filesLoading = ref(false)
  const fileList = ref<IwpMarkdownFileMeta[]>([])
  const iwpRoot = ref('InstructWare.iw')
  const activeFilePath = ref('')
  const markdownContent = ref('')
  const markdownContentHash = ref('')
  const fileLoading = ref(false)
  const fileSaving = ref(false)
  const buildState = ref<BuildUiState>({
    status: 'idle',
    sessionId: '',
    stage: '',
    message: '',
    error: '',
  })

  const hasActiveFile = computed(() => Boolean(activeFilePath.value))
  const isDirty = ref(false)
  const canBuild = computed(() => Boolean(hasActiveFile.value && isDirty.value && buildState.value.status !== 'running'))
  const readonlyFilePath = ref('')
  const readonlyFileLine = ref(0)
  const readonlyFileContent = ref('')
  const readonlyLoading = ref(false)
  const readonlyError = ref('')

  const loadFileList = async () => {
    if (!options.pluginId()) return
    filesLoading.value = true
    try {
      const payload = await listIwpFiles(options.pluginId())
      iwpRoot.value = payload.iwp_root
      fileList.value = payload.files
      if (!activeFilePath.value && payload.files.length > 0) {
        await openFile(payload.files[0].path)
      }
    } finally {
      filesLoading.value = false
    }
  }

  const openFile = async (path: string) => {
    if (!options.pluginId() || !path) return
    fileLoading.value = true
    try {
      const payload = await readIwpFile(options.pluginId(), path)
      activeFilePath.value = payload.path
      markdownContent.value = payload.content
      markdownContentHash.value = payload.content_hash
      isDirty.value = false
    } finally {
      fileLoading.value = false
    }
  }

  const saveCurrentFile = async () => {
    if (!options.pluginId() || !activeFilePath.value) return
    fileSaving.value = true
    try {
      const payload = await saveIwpFile(options.pluginId(), {
        path: activeFilePath.value,
        content: markdownContent.value,
        expected_hash: markdownContentHash.value,
      })
      markdownContentHash.value = payload.content_hash
      isDirty.value = false
      buildState.value = {
        ...buildState.value,
        message: options.t.value.apps.iwpSaveSuccess,
      }
      await loadFileList()
    } finally {
      fileSaving.value = false
    }
  }

  const updateContent = (next: string) => {
    markdownContent.value = next
    isDirty.value = true
  }

  const toggleFileTree = () => {
    fileTreeCollapsed.value = !fileTreeCollapsed.value
  }

  const setCenterPaneMode = (mode: 'markdown' | 'readonly') => {
    centerPaneMode.value = mode
  }

  const triggerBuild = async () => {
    if (!options.pluginId() || !canBuild.value) return
    await saveCurrentFile()
    const promptText = createIwpBuildPrompt({
      pluginId: options.pluginId(),
      iwpRoot: iwpRoot.value,
      changedFilePath: activeFilePath.value,
    })
    const sessionTitle = `IWP Build · ${activeFilePath.value || options.pluginId()}`
    const { sessionId } = await buildExecutor.startBuild({
      sessionTitle,
      promptText,
      workspaceOptions: { pluginId: options.pluginId() },
    })
    buildState.value = {
      status: 'running',
      sessionId,
      stage: 'running',
      message: String(options.t.value.apps.iwpBuildRunningSession || options.t.value.apps.iwpBuilding).replace(
        '{id}',
        sessionId
      ),
      error: '',
    }
    const settled = await buildExecutor.waitUntilSettled({ sessionId })
    if (settled.status === 'success') {
      buildState.value = {
        status: 'success',
        sessionId,
        stage: 'completed',
        message: String(options.t.value.apps.iwpBuildSuccessWithSession || options.t.value.apps.iwpBuildSuccess).replace(
          '{id}',
          sessionId
        ),
        error: '',
      }
      return
    }
    buildState.value = {
      status: 'failed',
      sessionId,
      stage: 'failed',
      message: options.t.value.apps.iwpBuildFailed,
      error: settled.reason || '',
    }
  }

  const normalizeInspectorPath = (value: string) => {
    const trimmed = String(value || '').trim()
    if (!trimmed) return ''
    const queryIndex = trimmed.indexOf('?')
    const base = queryIndex >= 0 ? trimmed.slice(0, queryIndex) : trimmed
    return base.replace(/^\/+/, '')
  }

  const openReadonlyByInspector = async (payload: InspectorSelectPayload) => {
    const targetPath = normalizeInspectorPath(payload.fileRelative || payload.file || '')
    readonlyFilePath.value = targetPath || String(payload.file || '')
    readonlyFileLine.value = Number(payload.range?.start?.line || 0)
    readonlyFileContent.value = ''
    readonlyError.value = ''
    centerPaneMode.value = 'readonly'
    if (!targetPath || !targetPath.toLowerCase().endsWith('.md') || !options.pluginId()) {
      readonlyError.value = String(options.t.value.apps.iwpReadonlyUnsupported || '当前文件暂不支持只读浏览')
      return
    }
    readonlyLoading.value = true
    try {
      const filePayload = await readIwpFile(options.pluginId(), targetPath)
      readonlyFileContent.value = filePayload.content
      readonlyError.value = ''
    } catch (error) {
      readonlyError.value = String(options.t.value.apps.iwpReadonlyLoadFailed || '加载源码失败')
    } finally {
      readonlyLoading.value = false
    }
  }

  const backToMarkdown = () => {
    centerPaneMode.value = 'markdown'
  }

  const reset = () => {
    buildState.value = {
      status: 'idle',
      sessionId: '',
      stage: '',
      message: '',
      error: '',
    }
    centerPaneMode.value = 'markdown'
    readonlyFilePath.value = ''
    readonlyFileLine.value = 0
    readonlyFileContent.value = ''
    readonlyError.value = ''
  }

  return {
    iwpRoot,
    fileTreeCollapsed,
    centerPaneMode,
    filesLoading,
    fileList,
    activeFilePath,
    markdownContent,
    fileLoading,
    fileSaving,
    buildState,
    isDirty,
    hasActiveFile,
    canBuild,
    loadFileList,
    openFile,
    saveCurrentFile,
    updateContent,
    toggleFileTree,
    setCenterPaneMode,
    triggerBuild,
    readonlyFilePath,
    readonlyFileLine,
    readonlyFileContent,
    readonlyLoading,
    readonlyError,
    openReadonlyByInspector,
    backToMarkdown,
    reset,
  }
}
