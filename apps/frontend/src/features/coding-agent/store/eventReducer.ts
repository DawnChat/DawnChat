import type { CodingAgentEvent } from '@/services/coding-agent/engineAdapter'

const TERMINAL_EVENT_TYPES = new Set(['session.idle', 'session.error', 'run.completed', 'run.failed'])

export function isTerminalEventType(eventType: string): boolean {
  return TERMINAL_EVENT_TYPES.has(String(eventType || ''))
}

export function asEventType(evt: CodingAgentEvent): string {
  return String(evt?.type || '').trim()
}

