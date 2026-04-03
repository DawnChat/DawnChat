import type { AssistantRuntimeEventPayload } from '@/services/plugin-ui-bridge/messageProtocol'

export interface AssistantSessionRuntimeEvent {
  type: string
  tsMs: number
  source: string
  sessionId?: string
  stepId?: string
  payload: Record<string, unknown>
}

export function toAssistantSessionRuntimeEvent(
  payload: AssistantRuntimeEventPayload
): AssistantSessionRuntimeEvent {
  return {
    type: payload.type,
    tsMs: payload.ts_ms,
    source: payload.source,
    sessionId: payload.session_id,
    stepId: payload.step_id,
    payload: payload.payload,
  }
}

export function toAssistantRuntimeEventResult(
  event: AssistantSessionRuntimeEvent
): AssistantRuntimeEventPayload {
  return {
    type: event.type,
    ts_ms: event.tsMs,
    source: event.source,
    session_id: event.sessionId,
    step_id: event.stepId,
    payload: event.payload,
  }
}
