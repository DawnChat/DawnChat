import { logger } from "@/utils/logger";

export type TtsPlaybackState = "idle" | "buffering" | "playing" | "stopped" | "error";

interface QueueItem {
  seq: number;
  url: string;
}

export class TtsPlaybackQueue {
  private readonly audioContext: AudioContext;

  private readonly queued = new Map<number, QueueItem>();

  private expectedSeq = 1;

  private sourceNode: AudioBufferSourceNode | null = null;

  private state: TtsPlaybackState = "idle";

  private active = true;

  private done = false;

  private playbackLoop: Promise<void> | null = null;

  constructor(audioContext?: AudioContext) {
    this.audioContext = audioContext || new AudioContext();
  }

  getState(): TtsPlaybackState {
    return this.state;
  }

  async enqueue(seq: number, url: string): Promise<void> {
    if (!this.active) {
      return;
    }
    this.queued.set(seq, { seq, url });
    await this.ensurePlaybackLoop();
  }

  async markDone(): Promise<void> {
    this.done = true;
    await this.ensurePlaybackLoop();
  }

  async stop(): Promise<void> {
    this.active = false;
    this.done = true;
    this.expectedSeq = 1;
    this.queued.clear();
    if (this.sourceNode) {
      try {
        this.sourceNode.stop();
      } catch {
      }
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    this.state = "stopped";
    this.playbackLoop = null;
  }

  async reset(): Promise<void> {
    await this.stop();
    this.active = true;
    this.done = false;
    this.state = "idle";
  }

  private async ensurePlaybackLoop(): Promise<void> {
    if (!this.active) {
      return;
    }
    if (this.playbackLoop) {
      return this.playbackLoop;
    }
    this.playbackLoop = this.consumeLoop().finally(() => {
      this.playbackLoop = null;
    });
    return this.playbackLoop;
  }

  private async consumeLoop(): Promise<void> {
    if (!this.active) {
      return;
    }
    while (this.active) {
      let item = this.queued.get(this.expectedSeq);
      if (!item && this.done && this.queued.size > 0) {
        const pendingSeqs = Array.from(this.queued.keys()).sort((a, b) => a - b);
        this.expectedSeq = pendingSeqs[0];
        item = this.queued.get(this.expectedSeq);
      }
      if (!item) {
        if (this.done) {
          this.state = this.sourceNode ? "playing" : "idle";
        } else {
          this.state = this.queued.size > 0 ? "buffering" : "idle";
        }
        return;
      }
      this.queued.delete(this.expectedSeq);
      this.expectedSeq += 1;
      try {
        this.state = "playing";
        if (this.audioContext.state === "suspended") {
          await this.audioContext.resume();
        }
        const response = await fetch(item.url);
        if (!response.ok) {
          throw new Error(`load audio failed: ${response.status}`);
        }
        const buffer = await response.arrayBuffer();
        const audioBuffer = await this.audioContext.decodeAudioData(buffer.slice(0));
        const source = this.audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.audioContext.destination);
        this.sourceNode = source;
        await new Promise<void>((resolve) => {
          source.onended = () => {
            if (this.sourceNode === source) {
              this.sourceNode = null;
            }
            resolve();
          };
          source.start();
        });
      } catch (error) {
        logger.warn("tts_playback_failed", {
          seq: item.seq,
          url: item.url,
          audioContextState: this.audioContext.state,
          error: String(error),
        });
        this.state = "error";
        return;
      }
    }
  }
}
