import { startSseClient, type SseClientEvent } from "@/services/coding-agent/sseClient";
import { buildBackendUrl } from '@/utils/backendUrl';

export interface TtsSpeakRequest {
  plugin_id: string;
  text: string;
  voice?: string;
  sid?: number;
  mode?: "manual";
  engine?: "python" | "azure" | "dawn-tts";
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

export interface AzureTtsConfigPayload {
  api_key?: string;
  region: string;
  voice: string;
  default_voice_zh?: string;
  default_voice_en?: string;
}

export interface AzureTtsConfigStatus {
  status: string;
  data: {
    configured: boolean;
    api_key_configured: boolean;
    region: string;
    voice: string;
    default_voice_zh: string;
    default_voice_en: string;
  };
}

export interface DawnTtsProviderStatus {
  status: string;
  data: {
    available: boolean;
    reason: string;
    default_voice_zh: string;
    default_voice_en: string;
  };
}

export interface DawnTtsVoicePayload {
  default_voice_zh?: string;
  default_voice_en?: string;
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

export async function getAzureTtsConfigStatus(): Promise<AzureTtsConfigStatus> {
  const response = await fetch(`${API_BASE()}/providers/azure/status`);
  if (!response.ok) {
    throw new Error(`azure tts status failed: ${response.status}`);
  }
  return (await response.json()) as AzureTtsConfigStatus;
}

export async function getDawnTtsStatus(): Promise<DawnTtsProviderStatus> {
  const response = await fetch(`${API_BASE()}/providers/dawn-tts/status`);
  if (!response.ok) {
    throw new Error(`dawn tts status failed: ${response.status}`);
  }
  return (await response.json()) as DawnTtsProviderStatus;
}

export async function validateDawnTtsVoiceConfig(payload: DawnTtsVoicePayload): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE()}/providers/dawn-tts/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      default_voice_zh: payload.default_voice_zh || "",
      default_voice_en: payload.default_voice_en || "",
    }),
  });
  if (!response.ok) {
    throw new Error(`dawn tts validate failed: ${response.status}`);
  }
  const json = (await response.json()) as { data?: Record<string, unknown> };
  return json.data || {};
}

export async function saveDawnTtsVoiceConfig(payload: DawnTtsVoicePayload): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE()}/providers/dawn-tts/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      default_voice_zh: payload.default_voice_zh || "",
      default_voice_en: payload.default_voice_en || "",
    }),
  });
  if (!response.ok) {
    throw new Error(`dawn tts config save failed: ${response.status}`);
  }
  const json = (await response.json()) as { data?: Record<string, unknown> };
  return json.data || {};
}

export async function validateAzureTtsConfig(payload: AzureTtsConfigPayload): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE()}/providers/azure/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_key: payload.api_key || "",
      region: payload.region,
      voice: payload.voice,
      default_voice_zh: payload.default_voice_zh || "",
      default_voice_en: payload.default_voice_en || "",
    }),
  });
  if (!response.ok) {
    throw new Error(`azure tts validate failed: ${response.status}`);
  }
  const json = (await response.json()) as { data?: Record<string, unknown> };
  return json.data || {};
}

export async function saveAzureTtsConfig(payload: AzureTtsConfigPayload): Promise<Record<string, unknown>> {
  const response = await fetch(`${API_BASE()}/providers/azure/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_key: payload.api_key || "",
      region: payload.region,
      voice: payload.voice,
      default_voice_zh: payload.default_voice_zh || "",
      default_voice_en: payload.default_voice_en || "",
    }),
  });
  if (!response.ok) {
    throw new Error(`azure tts config save failed: ${response.status}`);
  }
  const json = (await response.json()) as { data?: Record<string, unknown> };
  return json.data || {};
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
