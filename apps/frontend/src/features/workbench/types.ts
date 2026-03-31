export interface Project {
  id: string
  name: string
  description?: string
  icon?: string
  createdAt: string
  updatedAt: string
  messageCount: number
  lastMessage?: string
}

export interface Message {
  id: string
  projectId: string
  role: 'user' | 'assistant' | 'system'
  content: string
  modelId?: string
  createdAt: string
}
