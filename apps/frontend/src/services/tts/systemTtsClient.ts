export interface SystemTtsSpeakRequest {
  text: string;
  voice?: string;
}

function resolveVoice(voiceName?: string): SpeechSynthesisVoice | null {
  const speechSynthesisApi = window.speechSynthesis;
  const voices = speechSynthesisApi.getVoices();
  const normalized = String(voiceName || "").trim();
  if (!normalized) {
    return null;
  }
  return voices.find((item) => item.name === normalized || item.voiceURI === normalized) || null;
}

export function isSystemTtsSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window && typeof SpeechSynthesisUtterance !== "undefined";
}

export async function speakSystemTts(payload: SystemTtsSpeakRequest): Promise<void> {
  if (!isSystemTtsSupported()) {
    throw new Error("system_tts_not_supported");
  }
  const text = String(payload.text || "").trim();
  if (!text) {
    throw new Error("text is required");
  }
  const speechSynthesisApi = window.speechSynthesis;
  speechSynthesisApi.cancel();
  await new Promise<void>((resolve, reject) => {
    const utterance = new SpeechSynthesisUtterance(text);
    const selectedVoice = resolveVoice(payload.voice);
    if (selectedVoice) {
      utterance.voice = selectedVoice;
    }
    utterance.onend = () => resolve();
    utterance.onerror = () => reject(new Error("system_tts_failed"));
    speechSynthesisApi.speak(utterance);
  });
}

export function stopSystemTts(): void {
  if (!isSystemTtsSupported()) {
    return;
  }
  window.speechSynthesis.cancel();
}
