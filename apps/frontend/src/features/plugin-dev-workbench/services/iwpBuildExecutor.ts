import { ENGINE_OPENCODE } from '@/services/coding-agent/adapterRegistry'
import type { WorkspaceResolveOptions } from '@/features/coding-agent/store/types'
import type { useCodingAgentStore } from '@/features/coding-agent/store/codingAgentStore'

type CodingAgentStoreInstance = ReturnType<typeof useCodingAgentStore>

export interface BuildSessionStateSnapshot {
  sessionId: string
  isStreaming: boolean
  sessionRunStatus: string
  transportStatus: string
  lastError: string | null
}

export interface IwpBuildStartOptions {
  sessionTitle: string
  promptText: string
  workspaceOptions: WorkspaceResolveOptions
}

export interface IwpBuildWaitOptions {
  sessionId: string
  timeoutMs?: number
  pollIntervalMs?: number
}

export class OpenCodeSessionBuildExecutor {
  constructor(private readonly codingAgentStore: CodingAgentStoreInstance) {}

  async startBuild(options: IwpBuildStartOptions): Promise<{ sessionId: string }> {
    if (this.codingAgentStore.selectedEngine !== ENGINE_OPENCODE) {
      this.codingAgentStore.selectEngine(ENGINE_OPENCODE)
    }
    this.codingAgentStore.selectAgent('build')
    await this.codingAgentStore.ensureReadyWithWorkspace(options.workspaceOptions)
    const sessionId = await this.codingAgentStore.createBuildSession(options.sessionTitle, options.workspaceOptions)
    await this.codingAgentStore.sendTextToSession(sessionId, options.promptText, options.workspaceOptions)
    return { sessionId }
  }

  async waitUntilSettled(options: IwpBuildWaitOptions): Promise<{ status: 'success' | 'failed'; reason?: string }> {
    const timeoutMs = Number(options.timeoutMs || 15 * 60 * 1000)
    const pollIntervalMs = Number(options.pollIntervalMs || 1200)
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      const snapshot = this.codingAgentStore.getSessionStateSnapshot(options.sessionId)
      if (snapshot) {
        const result = this.resolveState(snapshot)
        if (result) return result
      }
      await this.sleep(pollIntervalMs)
    }
    return { status: 'failed', reason: 'build timeout' }
  }

  private resolveState(snapshot: BuildSessionStateSnapshot): { status: 'success' | 'failed'; reason?: string } | null {
    const runStatus = String(snapshot.sessionRunStatus || '').toLowerCase()
    if (snapshot.lastError) {
      return { status: 'failed', reason: snapshot.lastError }
    }
    if (snapshot.isStreaming) {
      return null
    }
    if (['failed', 'error', 'interrupted'].includes(runStatus)) {
      return { status: 'failed', reason: snapshot.sessionRunStatus || 'build failed' }
    }
    if (['idle', 'completed', 'stopped', ''].includes(runStatus)) {
      return { status: 'success' }
    }
    return null
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms)
    })
  }
}
