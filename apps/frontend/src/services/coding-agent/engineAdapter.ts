export interface CodingAgentPart {
  id: string
  type: string
  messageID?: string
  text?: string
  tool?: string
  callID?: string
  command?: string
  path?: string
  reason?: string
  response?: string
  title?: string
  permissionID?: string
  state?: {
    status?: string
    input?: Record<string, unknown>
    output?: string
    error?: string | Record<string, unknown>
    raw?: string
    rawArguments?: string
    [key: string]: unknown
  }
  [key: string]: unknown
}

export interface CodingAgentMessageInfo {
  id: string
  role: 'user' | 'assistant' | string
  error?: {
    message?: string
    [key: string]: unknown
  } | null
  time?: {
    created?: string
    completed?: string
  }
  [key: string]: unknown
}

export interface CodingAgentMessage {
  info: CodingAgentMessageInfo
  parts: CodingAgentPart[]
}

export interface CodingAgentEvent {
  type: string
  sessionID?: string
  messageID?: string | null
  eventID?: number
  seq?: number
  properties?: Record<string, any>
}

export type PermissionDecision = 'once' | 'always' | 'reject' | string

export interface CodingAgentQuestionOption {
  label: string
  description: string
}

export interface CodingAgentQuestionInfo {
  question: string
  header: string
  options: CodingAgentQuestionOption[]
  multiple?: boolean
  custom?: boolean
}

export type CodingAgentQuestionAnswer = string[]

export interface CodingAgentQuestionRequest {
  id: string
  sessionID: string
  questions: CodingAgentQuestionInfo[]
  tool?: {
    messageID: string
    callID: string
  }
}

export interface CodingAgentPermissionRequest {
  id: string
  sessionID: string
  permission: string
  patterns: string[]
  always?: string[]
  metadata?: Record<string, unknown>
  tool?: {
    messageID?: string
    callID?: string
  }
  [key: string]: unknown
}

export interface CodingAgentSession {
  id: string
  title?: string
  directory?: string
  workspace_path?: string
  workspace_kind?: string
  plugin_id?: string
  project_id?: string
  time?: {
    created?: string
    updated?: string
  }
  [key: string]: unknown
}

export interface SessionQueryOptions {
  directory?: string
  workspacePath?: string
  workspaceKind?: string
  pluginId?: string
  projectId?: string
}

export interface PromptPayload {
  parts: PromptPart[]
  agent: string
  plugin_id?: string
  project_id?: string
  workspace_path?: string
  workspace_kind?: string
  system?: string
  model?: {
    providerID: string
    modelID: string
  }
}

export interface PromptTextPart {
  type: 'text'
  text: string
}

export interface PromptFilePart {
  type: 'file'
  mime: string
  url: string
  filename?: string
}

export type PromptPart = PromptTextPart | PromptFilePart

export interface AgentOption {
  id: string
  label?: string
  description?: string
  mode?: string
  hidden?: boolean
  source?: string
}

export interface ModelOption {
  id: string
  label: string
  providerID: string
  modelID: string
}

export interface EngineAdapter {
  listSessions(options?: SessionQueryOptions): Promise<CodingAgentSession[]>
  getSession(sessionId: string): Promise<CodingAgentSession | null>
  createSession(title?: string, options?: SessionQueryOptions): Promise<string>
  updateSession(sessionId: string, patch: { title?: string }): Promise<CodingAgentSession | null>
  deleteSession(sessionId: string): Promise<boolean>
  listMessages(sessionId: string): Promise<CodingAgentMessage[]>
  getSessionTodos?(sessionId: string): Promise<
    Array<{ id?: string; content?: string; status?: string; priority?: string }>
  >
  prompt(sessionId: string, payload: PromptPayload): Promise<CodingAgentMessage | null>
  promptAsync(sessionId: string, payload: PromptPayload): Promise<void>
  interruptSession(sessionId: string): Promise<boolean>
  injectContext(sessionId: string, text: string): Promise<void>
  replyPermission(
    sessionId: string,
    permissionId: string,
    response: PermissionDecision,
    remember?: boolean
  ): Promise<boolean>
  supportsQuestions?(): boolean
  listQuestions?(sessionId?: string): Promise<CodingAgentQuestionRequest[]>
  replyQuestion?(requestId: string, answers: CodingAgentQuestionAnswer[]): Promise<boolean>
  rejectQuestion?(requestId: string): Promise<boolean>
  listPermissions?(sessionId?: string): Promise<CodingAgentPermissionRequest[]>
  listAgents?(): Promise<AgentOption[]>
  listModels?(): Promise<ModelOption[]>
  updateSessionConfig?(
    sessionId: string,
    patch: {
      agent?: string
      model?: {
        providerID: string
        modelID: string
      }
    }
  ): Promise<CodingAgentSession | null>
  subscribeEvents(onEvent: (evt: CodingAgentEvent) => void): Promise<() => void>
}

