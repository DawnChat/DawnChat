import { describe, expect, it, vi } from "vitest";

import {
  getAzureTtsConfigStatus,
  getDawnTtsStatus,
  getTtsCapability,
  getTtsTaskStatus,
  saveAzureTtsConfig,
  saveDawnTtsVoiceConfig,
  speakTts,
  stopTts,
  validateAzureTtsConfig,
} from "../ttsClient";

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

  it("queries azure tts status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          status: "success",
          data: {
            configured: false,
            api_key_configured: true,
            region: "eastasia",
            voice: "zh-CN-XiaoxiaoNeural",
            default_voice_zh: "zh-CN-XiaoxiaoNeural",
            default_voice_en: "en-US-JennyNeural",
          }
        }),
      }))
    );
    const payload = await getAzureTtsConfigStatus();
    expect(payload.data.region).toBe("eastasia");
  });

  it("validates azure tts config", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ status: "success", data: { ok: true } }),
      }))
    );
    const payload = await validateAzureTtsConfig({ api_key: "k", region: "eastasia", voice: "zh-CN-XiaoxiaoNeural" });
    expect(payload.ok).toBe(true);
  });

  it("queries dawn tts status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          status: "success",
          data: {
            available: true,
            reason: "",
            default_voice_zh: "zh-CN-XiaoxiaoNeural",
            default_voice_en: "en-US-JennyNeural",
          },
        }),
      }))
    );
    const payload = await getDawnTtsStatus();
    expect(payload.data.available).toBe(true);
  });

  it("saves dawn tts voice config", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ status: "success", data: { ok: true } }),
      }))
    );
    const payload = await saveDawnTtsVoiceConfig({
      default_voice_zh: "zh-CN-YunxiNeural",
      default_voice_en: "en-US-GuyNeural",
    });
    expect(payload.ok).toBe(true);
  });

  it("saves azure tts config", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ status: "success", data: { ok: true } }),
      }))
    );
    const payload = await saveAzureTtsConfig({ api_key: "k", region: "eastasia", voice: "zh-CN-XiaoxiaoNeural" });
    expect(payload.ok).toBe(true);
  });
});
