import { startSseClient, type SseClientEvent } from "@/services/coding-agent/sseClient";
import { buildBackendUrl } from '@/utils/backendUrl';

export interface TtsSpeakRequest {
  plugin_id: string;
  text: string;
  voice?: string;
  sid?: number;
  mode?: "manual";
  interrupt?: boolean;
}

export interface TtsSpeakResponse {
  status: string;
  task_id: string;
  stream_url: string;
  status_url: string;
}

export interface TtsTaskStatusResponse {
  status: string;
  data: Record<string, unknown>;
}

export interface TtsCapabilityResponse {
  status: string;
  data: {
    available: boolean;
    engine: string;
    reason: string;
    model: Record<string, unknown>;
  };
}

export interface TtsStreamMessage {
  event: string;
  data: Record<string, unknown>;
}

const API_BASE = () => buildBackendUrl('/api/tts');

export async function speakTts(payload: TtsSpeakRequest): Promise<TtsSpeakResponse> {
  const response = await fetch(`${API_BASE()}/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`tts speak failed: ${response.status}`);
  }
  return (await response.json()) as TtsSpeakResponse;
}

export async function stopTts(taskId?: string, pluginId?: string): Promise<{ stopped: boolean }> {
  const response = await fetch(`${API_BASE()}/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId, plugin_id: pluginId }),
  });
  if (!response.ok) {
    throw new Error(`tts stop failed: ${response.status}`);
  }
  const payload = (await response.json()) as { data?: { stopped?: boolean } };
  return { stopped: Boolean(payload.data?.stopped) };
}

export async function getTtsTaskStatus(taskId: string): Promise<TtsTaskStatusResponse> {
  const response = await fetch(`${API_BASE()}/tasks/${encodeURIComponent(taskId)}`);
  if (!response.ok) {
    throw new Error(`tts status failed: ${response.status}`);
  }
  return (await response.json()) as TtsTaskStatusResponse;
}

export async function getTtsCapability(pluginId?: string): Promise<TtsCapabilityResponse> {
  const query = pluginId ? `?plugin_id=${encodeURIComponent(pluginId)}` : "";
  const response = await fetch(`${API_BASE()}/capability${query}`);
  if (!response.ok) {
    throw new Error(`tts capability failed: ${response.status}`);
  }
  return (await response.json()) as TtsCapabilityResponse;
}

export function subscribeTtsTaskStream(
  taskId: string,
  options: {
    signal: AbortSignal;
    onEvent: (message: TtsStreamMessage) => void;
    onStatus?: (status: "connecting" | "reconnecting" | "streaming" | "closed") => void;
    onError?: (error: unknown) => void;
  }
): Promise<void> {
  return startSseClient({
    url: `${API_BASE()}/stream/${encodeURIComponent(taskId)}`,
    signal: options.signal,
    onStatus: (status) => options.onStatus?.(status),
    onError: (error) => options.onError?.(error),
    onEvent: (event: SseClientEvent) => {
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(event.data) as Record<string, unknown>;
      } catch {
        data = {};
      }
      options.onEvent({
        event: event.event || "message",
        data,
      });
    },
  });
}
