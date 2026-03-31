import { computed, ref } from "vue";

import {
  getTtsTaskStatus,
  speakTts,
  stopTts,
  subscribeTtsTaskStream,
  type TtsSpeakRequest,
  type TtsStreamMessage,
} from "@/services/tts/ttsClient";
import { TtsPlaybackQueue } from "@/services/tts/ttsPlaybackQueue";
import { logger } from "@/utils/logger";

type TtsStreamStatus = "idle" | "connecting" | "reconnecting" | "streaming" | "closed";
type TtsPlaybackTerminalStatus = "completed" | "cancelled" | "error" | "stopped" | "timeout";

interface PlaybackWaiter {
  promise: Promise<TtsPlaybackTerminalStatus>;
  resolve: (status: TtsPlaybackTerminalStatus) => void;
}

function createHostTtsPlaybackService() {
  const queue = new TtsPlaybackQueue();
  const currentTaskId = ref("");
  const streamStatus = ref<TtsStreamStatus>("idle");
  const playbackState = ref(queue.getState());
  let streamAbortController: AbortController | null = null;
  let initialized = false;
  const playbackWaiters = new Map<string, PlaybackWaiter>();
  const playbackTerminalStatus = new Map<string, TtsPlaybackTerminalStatus>();

  const syncPlaybackState = (): void => {
    playbackState.value = queue.getState();
  };

  const closeCurrentStream = (): void => {
    if (!streamAbortController) {
      return;
    }
    streamAbortController.abort();
    streamAbortController = null;
  };

  const createPlaybackWaiter = (taskId: string): PlaybackWaiter => {
    const existing = playbackWaiters.get(taskId);
    if (existing) {
      return existing;
    }
    let resolve: ((status: TtsPlaybackTerminalStatus) => void) | null = null;
    const promise = new Promise<TtsPlaybackTerminalStatus>((resolvePromise) => {
      resolve = resolvePromise;
    });
    const waiter: PlaybackWaiter = {
      promise,
      resolve: (status) => {
        if (resolve) {
          resolve(status);
          resolve = null;
        }
      },
    };
    playbackWaiters.set(taskId, waiter);
    return waiter;
  };

  const settlePlayback = (taskId: string, status: TtsPlaybackTerminalStatus): void => {
    const normalizedTaskId = String(taskId || "").trim();
    if (!normalizedTaskId) {
      return;
    }
    playbackTerminalStatus.set(normalizedTaskId, status);
    const waiter = playbackWaiters.get(normalizedTaskId);
    if (waiter) {
      waiter.resolve(status);
      playbackWaiters.delete(normalizedTaskId);
    }
  };

  const init = (): void => {
    if (initialized) {
      return;
    }
    initialized = true;
  };

  const dispose = async (): Promise<void> => {
    if (currentTaskId.value) {
      settlePlayback(currentTaskId.value, "stopped");
    }
    closeCurrentStream();
    await queue.stop();
    syncPlaybackState();
    currentTaskId.value = "";
    streamStatus.value = "idle";
    initialized = false;
  };

  const handleStreamEvent = async (taskId: string, message: TtsStreamMessage): Promise<void> => {
    if (currentTaskId.value !== taskId) {
      return;
    }
    logger.debug("host_tts_stream_event", { taskId, event: message.event });
    if (message.event === "segment_ready") {
      const seq = Number(message.data.seq || 0);
      const url = String(message.data.url || "");
      if (seq > 0 && url) {
        await queue.enqueue(seq, url);
        syncPlaybackState();
      }
      return;
    }
    if (message.event === "done") {
      closeCurrentStream();
      await queue.markDone();
      syncPlaybackState();
      streamStatus.value = "closed";
      settlePlayback(taskId, "completed");
      return;
    }
    if (message.event === "cancelled" || message.event === "error") {
      closeCurrentStream();
      await queue.stop();
      syncPlaybackState();
      streamStatus.value = "closed";
      settlePlayback(taskId, message.event === "cancelled" ? "cancelled" : "error");
      return;
    }
    if (message.event === "close") {
      closeCurrentStream();
      streamStatus.value = "closed";
    }
  };

  const isStreaming = computed(() => streamStatus.value === "streaming");

  const bindTaskStream = async (taskId: string): Promise<void> => {
    if (!initialized) {
      init();
    }
    logger.info("host_tts_bind_start", { taskId });
    if (currentTaskId.value && currentTaskId.value !== taskId) {
      settlePlayback(currentTaskId.value, "stopped");
    }
    createPlaybackWaiter(taskId);
    playbackTerminalStatus.delete(taskId);
    await queue.reset();
    syncPlaybackState();
    streamStatus.value = "connecting";
    closeCurrentStream();
    currentTaskId.value = taskId;
    streamAbortController = new AbortController();
    void subscribeTtsTaskStream(taskId, {
      signal: streamAbortController.signal,
      onStatus: (status) => {
        streamStatus.value = status;
        logger.info("host_tts_stream_status", { taskId, status });
      },
      onEvent: (message) => {
        void handleStreamEvent(taskId, message);
      },
      onError: async (error) => {
        if (currentTaskId.value !== taskId) {
          return;
        }
        logger.warn("host_tts_stream_error", { taskId, error: String(error) });
        await queue.stop();
        syncPlaybackState();
        streamStatus.value = "closed";
        settlePlayback(taskId, "error");
      },
    });
  };

  const startSpeak = async (payload: TtsSpeakRequest): Promise<string> => {
    if (!initialized) {
      init();
    }
    const result = await speakTts(payload);
    await bindTaskStream(result.task_id);
    return result.task_id;
  };

  const attachTask = async (taskId: string): Promise<void> => {
    const normalized = String(taskId || "").trim();
    if (!normalized) {
      return;
    }
    if (normalized === currentTaskId.value && streamStatus.value !== "closed") {
      return;
    }
    logger.info("host_tts_attach_task", { taskId: normalized });
    await bindTaskStream(normalized);
  };

  const stopSpeak = async (taskId?: string): Promise<void> => {
    const targetTaskId = taskId || currentTaskId.value;
    if (targetTaskId) {
      settlePlayback(targetTaskId, "stopped");
    }
    closeCurrentStream();
    logger.info("host_tts_stop", { taskId: targetTaskId || "" });
    await stopTts(targetTaskId || undefined, undefined);
    await queue.stop();
    syncPlaybackState();
    currentTaskId.value = "";
    streamStatus.value = "closed";
  };

  const syncStopped = async (taskId?: string): Promise<void> => {
    if (taskId && currentTaskId.value && taskId !== currentTaskId.value) {
      return;
    }
    if (currentTaskId.value) {
      settlePlayback(currentTaskId.value, "stopped");
    }
    closeCurrentStream();
    await queue.stop();
    syncPlaybackState();
    currentTaskId.value = "";
    streamStatus.value = "closed";
  };

  const refreshStatus = async () => {
    if (!currentTaskId.value) {
      return null;
    }
    return getTtsTaskStatus(currentTaskId.value);
  };

  const waitForPlaybackCompletion = async (taskId: string, timeoutMs = 120000): Promise<void> => {
    const normalizedTaskId = String(taskId || "").trim();
    if (!normalizedTaskId) {
      throw new Error("task_id is required");
    }
    const terminalStatus = playbackTerminalStatus.get(normalizedTaskId);
    if (terminalStatus) {
      if (terminalStatus !== "completed") {
        throw new Error(`host tts playback terminal status: ${terminalStatus}`);
      }
      return;
    }
    const waiter = createPlaybackWaiter(normalizedTaskId);
    const timeoutPromise = new Promise<TtsPlaybackTerminalStatus>((resolve) => {
      window.setTimeout(() => {
        resolve("timeout");
      }, Math.max(1000, timeoutMs));
    });
    const status = await Promise.race([waiter.promise, timeoutPromise]);
    if (status !== "completed") {
      throw new Error(`host tts playback terminal status: ${status}`);
    }
  };

  return {
    init,
    dispose,
    currentTaskId,
    streamStatus,
    playbackState,
    isStreaming,
    startSpeak,
    attachTask,
    stopSpeak,
    syncStopped,
    refreshStatus,
    waitForPlaybackCompletion,
  };
}

let hostTtsPlaybackService: ReturnType<typeof createHostTtsPlaybackService> | null = null;

export function useHostTtsPlayback() {
  if (!hostTtsPlaybackService) {
    hostTtsPlaybackService = createHostTtsPlaybackService();
  }
  return hostTtsPlaybackService;
}
