import { beforeEach, describe, expect, it, vi } from "vitest";

import { subscribeTtsTaskStream } from "../../../../services/tts/ttsClient";

vi.stubGlobal("AudioContext", class {
  destination = {};

  async decodeAudioData() {
    return {};
  }

  createBufferSource() {
    const source = {
      buffer: null as unknown,
      connect: vi.fn(),
      disconnect: vi.fn(),
      onended: null as (() => void) | null,
      start: vi.fn(function start() {
        queueMicrotask(() => {
          if (source.onended) {
            source.onended();
          }
        });
      }),
      stop: vi.fn(),
    };
    return source;
  }
});

vi.mock("@/services/tts/ttsClient", () => ({
  speakTts: vi.fn(async () => ({ task_id: "task-1", status: "accepted", stream_url: "/api/tts/stream/task-1", status_url: "/api/tts/tasks/task-1" })),
  stopTts: vi.fn(async () => ({ stopped: true })),
  getTtsTaskStatus: vi.fn(async () => ({ status: "success", data: { task_id: "task-1" } })),
  subscribeTtsTaskStream: vi.fn(async (_taskId: string, options: { onStatus: (s: "connecting" | "reconnecting" | "streaming" | "closed") => void }) => {
    options.onStatus("streaming");
  }),
}));

describe("useHostTtsPlayback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        arrayBuffer: async () => new ArrayBuffer(8),
      }))
    );
  });

  it("starts speak and updates task id", async () => {
    const { useHostTtsPlayback } = await import("../useHostTtsPlayback");
    const api = useHostTtsPlayback();
    const taskId = await api.startSpeak({ plugin_id: "com.demo", text: "hello" });
    expect(taskId).toBe("task-1");
    expect(api.currentTaskId.value).toBe("task-1");
    await api.dispose();
  });

  it("reuses singleton service and resets state on dispose", async () => {
    const { useHostTtsPlayback } = await import("../useHostTtsPlayback");
    const apiA = useHostTtsPlayback();
    const apiB = useHostTtsPlayback();
    expect(apiA).toBe(apiB);
    await apiA.startSpeak({ plugin_id: "com.demo", text: "hello" });
    expect(apiA.streamStatus.value).toBe("streaming");
    await apiA.dispose();
    expect(apiA.currentTaskId.value).toBe("");
    expect(apiA.streamStatus.value).toBe("idle");
  });

  it("waits for playback completion after done event", async () => {
    const { useHostTtsPlayback } = await import("../useHostTtsPlayback");
    const api = useHostTtsPlayback();
    await api.startSpeak({ plugin_id: "com.demo", text: "hello world" });
    const subscribeMock = vi.mocked(subscribeTtsTaskStream);
    const options = subscribeMock.mock.calls[0]?.[1];
    expect(options).toBeTruthy();
    await options?.onEvent({
      event: "segment_ready",
      data: {
        seq: 1,
        url: "/api/tts/audio/task-1/1.wav",
      },
    });
    await options?.onEvent({
      event: "segment_ready",
      data: {
        seq: 2,
        url: "/api/tts/audio/task-1/2.wav",
      },
    });
    const waitPromise = api.waitForPlaybackCompletion("task-1", 10_000);
    await options?.onEvent({
      event: "done",
      data: {
        task_id: "task-1",
      },
    });
    await expect(waitPromise).resolves.toBeUndefined();
    await api.dispose();
  });
});
