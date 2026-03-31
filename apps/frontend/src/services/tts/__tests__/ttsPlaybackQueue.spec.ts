import { describe, expect, it, vi } from "vitest";

import { TtsPlaybackQueue } from "../ttsPlaybackQueue";

function createAudioContextMock() {
  return {
    destination: {},
    decodeAudioData: vi.fn(async () => ({})),
    createBufferSource: vi.fn(() => {
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
    }),
  } as unknown as AudioContext;
}

describe("TtsPlaybackQueue", () => {
  it("plays queued segments in order", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        arrayBuffer: async () => new ArrayBuffer(8),
      }))
    );
    const queue = new TtsPlaybackQueue(createAudioContextMock());
    await queue.enqueue(1, "/api/tts/audio/task-1/1.wav");
    expect(queue.getState()).toBe("idle");
  });

  it("can finish playback when early segments are missing after done", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        arrayBuffer: async () => new ArrayBuffer(8),
      }))
    );
    const queue = new TtsPlaybackQueue(createAudioContextMock());
    await queue.enqueue(2, "/api/tts/audio/task-1/2.wav");
    expect(queue.getState()).toBe("buffering");
    await queue.markDone();
    expect(queue.getState()).toBe("idle");
  });
});
