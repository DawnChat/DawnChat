import { describe, expect, it, vi } from "vitest";

import { getTtsCapability, getTtsTaskStatus, speakTts, stopTts } from "../ttsClient";

describe("ttsClient", () => {
  it("submits speak request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ status: "accepted", task_id: "task-1", stream_url: "/s", status_url: "/st" }),
      }))
    );
    const payload = await speakTts({ plugin_id: "com.demo", text: "hello" });
    expect(payload.task_id).toBe("task-1");
  });

  it("stops task", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ data: { stopped: true } }),
      }))
    );
    const result = await stopTts("task-1");
    expect(result.stopped).toBe(true);
  });

  it("queries task status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ status: "success", data: { task_id: "task-1" } }),
      }))
    );
    const payload = await getTtsTaskStatus("task-1");
    expect(payload.status).toBe("success");
  });

  it("queries tts capability", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ status: "success", data: { available: true, engine: "python", reason: "", model: {} } }),
      }))
    );
    const payload = await getTtsCapability("com.demo");
    expect(payload.data.available).toBe(true);
  });
});
