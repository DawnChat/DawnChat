import type { CodingAgentMessageInfo, CodingAgentPart, CodingAgentQuestionRequest } from '@/services/coding-agent/engineAdapter'

export type RenderItemType = 'text' | 'tool' | 'reasoning' | 'step' | 'unknown'
export type WorkspaceTargetKind = 'plugin-dev' | 'workbench-general'
export type WorkspaceSessionStrategy = 'single' | 'multi'

export interface ModelOption {
  id: string
  label: string
  providerID: string
  modelID: string
}

export interface SessionTodoItem {
  id: string
  content: string
  status: string
  priority: string
}

export interface ToolDisplayMeta {
  kind: 'read' | 'write' | 'search' | 'bash' | 'other'
  renderMode: 'inline' | 'collapsible'
  toolName: string
  argsText: string
  argsPreview: string
  hasDetails: boolean
  title: string
  summary: string
  detailBody: string
  detailsText: string
  command: string
  outputTail: string
  diffStat: string
  patchPreview: string
  languageHint: string
  codeLines: string[]
  previewLineCount: number
  hiddenLineCount: number
}

export interface ChatRenderItem {
  id: string
  type: RenderItemType
  text?: string
  tool?: string
  status?: string
  reason?: string
  messageID: string
  callID?: string
  toolDisplay?: ToolDisplayMeta
  raw: CodingAgentPart
  isStreaming: boolean
}

export interface ChatRenderRow {
  info: CodingAgentMessageInfo
  items: ChatRenderItem[]
}

export interface PermissionCard {
  id: string
  sessionID: string
  messageID: string
  callID: string
  tool: string
  status: 'pending' | 'approved' | 'rejected'
  response?: string
  detail: string
  metadataDiff?: string
}

export interface QuestionCard {
  id: string
  sessionID: string
  messageID: string
  questions: CodingAgentQuestionRequest['questions']
  status: 'pending' | 'answered' | 'rejected'
  toolCallID: string
}

export interface TimelineItemPart {
  id: string
  kind: 'part'
  role: string
  item: ChatRenderItem
}

export interface TimelineItemQuestion {
  id: string
  kind: 'question'
  question: QuestionCard
}

export interface TimelineItemPermission {
  id: string
  kind: 'permission'
  permission: PermissionCard
}

export interface TimelineItemTodo {
  id: string
  kind: 'todo'
  todos: SessionTodoItem[]
}

export type TimelineItem = TimelineItemPart | TimelineItemQuestion | TimelineItemPermission | TimelineItemTodo

export interface SessionMeta {
  id: string
  title: string
  createdAt: string
  updatedAt: string
}

export interface WorkspaceTarget {
  id: string
  kind: WorkspaceTargetKind
  displayName: string
  appType: string
  workspacePath: string
  preferredEntry: string
  preferredDirectories: string[]
  hints: string[]
  defaultAgent: string
  sessionStrategy: WorkspaceSessionStrategy
  pluginId?: string
  projectId?: string
}

export interface WorkspaceResolveOptions {
  pluginId?: string
  workspaceTarget?: WorkspaceTarget | null
  forceRestart?: boolean
}

export interface SessionState {
  messagesById: Record<string, CodingAgentMessageInfo>
  partsByMessageId: Record<string, Record<string, CodingAgentPart>>
  partOrderByMessageId: Record<string, Record<string, number>>
  permissionCardsById: Record<string, PermissionCard>
  questionCardsById: Record<string, QuestionCard>
  partOrderSeq: number
  isStreaming: boolean
  transportStatus: string
  sessionRunStatus: string
  lastError: string | null
  lastErrorRaw: string | null
  transportError: string | null
  runWaitReason: '' | 'generating' | 'waiting_permission' | 'waiting_question' | 'stalled'
  lastNonHeartbeatEventAt: number
  seenEventIDs: Record<string, true>
}
