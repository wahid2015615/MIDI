import type { PreviewNote } from "./parseSmf";

function midiToHz(note: number): number {
  return 440 * 2 ** ((note - 69) / 12);
}

type Voice = {
  stop: () => void;
};

/**
 * In-browser SMF preview using Web Audio (no extra packages).
 * Melodic notes: piano-like decaying partials. Channel 10 drums: noise hits.
 */
export class MidiPreviewPlayer {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private notes: PreviewNote[] = [];
  private duration = 0;
  private playing = false;
  private startedAt = 0;
  private offset = 0;
  private voices: Voice[] = [];
  private raf = 0;
  private onFrame: ((time: number, playing: boolean) => void) | null = null;

  load(notes: PreviewNote[], duration: number) {
    this.stop();
    this.notes = notes;
    this.duration = duration;
    this.offset = 0;
  }

  setListener(cb: ((time: number, playing: boolean) => void) | null) {
    this.onFrame = cb;
  }

  getDuration() {
    return this.duration;
  }

  isPlaying() {
    return this.playing;
  }

  currentTime() {
    if (!this.playing || !this.ctx) return this.offset;
    return Math.min(this.duration, this.offset + (this.ctx.currentTime - this.startedAt));
  }

  async play() {
    if (!this.notes.length) return;
    const ctx = this.ensureCtx();
    if (ctx.state === "suspended") await ctx.resume();
    if (this.offset >= this.duration - 0.04) this.offset = 0;
    this.stopVoices();
    this.playing = true;
    this.startedAt = ctx.currentTime;
    this.scheduleFrom(this.offset);
    this.tick();
  }

  pause() {
    this.offset = this.currentTime();
    this.playing = false;
    this.stopVoices();
    this.cancelTick();
    this.onFrame?.(this.offset, false);
  }

  stop() {
    this.playing = false;
    this.offset = 0;
    this.stopVoices();
    this.cancelTick();
    this.onFrame?.(0, false);
  }

  seek(time: number) {
    const wasPlaying = this.playing;
    this.offset = Math.max(0, Math.min(this.duration, time));
    if (wasPlaying) {
      void this.play();
    } else {
      this.onFrame?.(this.offset, false);
    }
  }

  dispose() {
    this.stop();
    this.onFrame = null;
    void this.ctx?.close();
    this.ctx = null;
    this.master = null;
  }

  private ensureCtx(): AudioContext {
    if (!this.ctx) {
      const ctx = new AudioContext();
      const master = ctx.createGain();
      master.gain.value = 0.85;
      const compressor = ctx.createDynamicsCompressor();
      compressor.threshold.value = -18;
      compressor.ratio.value = 3;
      master.connect(compressor);
      compressor.connect(ctx.destination);
      this.ctx = ctx;
      this.master = master;
    }
    return this.ctx;
  }

  private scheduleFrom(fromTime: number) {
    const ctx = this.ensureCtx();
    const master = this.master;
    if (!master) return;
    const now = ctx.currentTime;
    for (const note of this.notes) {
      const rel = note.time - fromTime;
      if (rel + note.duration < -0.02) continue;
      const start = now + Math.max(0, rel);
      const dur = Math.max(0.05, note.duration - Math.max(0, -rel));
      if (note.channel === 9) {
        this.voices.push(this.playDrum(ctx, master, start, dur, note));
      } else {
        this.voices.push(this.playTone(ctx, master, start, dur, note));
      }
    }
  }

  private playTone(
    ctx: AudioContext,
    dest: GainNode,
    start: number,
    dur: number,
    note: PreviewNote,
  ): Voice {
    const freq = midiToHz(note.midi);
    const vel = Math.max(0.05, note.velocity / 127);
    const gain = ctx.createGain();
    const peak = 0.18 * vel;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(peak, start + 0.012);
    gain.gain.exponentialRampToValueAtTime(peak * 0.55, start + Math.min(0.18, dur * 0.3));
    gain.gain.exponentialRampToValueAtTime(0.0001, start + dur + 0.12);
    gain.connect(dest);

    const sources: Array<OscillatorNode | AudioBufferSourceNode> = [];
    for (const [type, ratio, mix] of [
      ["triangle", 1, 0.7],
      ["sine", 2, 0.22],
      ["sine", 3, 0.08],
    ] as const) {
      const osc = ctx.createOscillator();
      osc.type = type;
      osc.frequency.setValueAtTime(freq * ratio, start);
      const g = ctx.createGain();
      g.gain.value = mix;
      osc.connect(g);
      g.connect(gain);
      osc.start(start);
      osc.stop(start + dur + 0.14);
      sources.push(osc);
    }
    return {
      stop: () => {
        for (const src of sources) {
          try {
            src.stop();
          } catch {
            /* already stopped */
          }
          try {
            src.disconnect();
          } catch {
            /* already gone */
          }
        }
        try {
          gain.disconnect();
        } catch {
          /* already gone */
        }
      },
    };
  }

  private playDrum(
    ctx: AudioContext,
    dest: GainNode,
    start: number,
    dur: number,
    note: PreviewNote,
  ): Voice {
    const vel = Math.max(0.08, note.velocity / 127);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.35 * vel, start + 0.004);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + Math.min(0.28, dur));
    gain.connect(dest);

    const sources: Array<OscillatorNode | AudioBufferSourceNode> = [];
    if (note.midi <= 41) {
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.setValueAtTime(90, start);
      osc.frequency.exponentialRampToValueAtTime(38, start + 0.12);
      osc.connect(gain);
      osc.start(start);
      osc.stop(start + 0.22);
      sources.push(osc);
    } else {
      const frames = Math.floor(ctx.sampleRate * 0.12);
      const buffer = ctx.createBuffer(1, frames, ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < frames; i += 1) data[i] = Math.random() * 2 - 1;
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      const filter = ctx.createBiquadFilter();
      filter.type = note.midi >= 42 && note.midi <= 51 ? "highpass" : "bandpass";
      filter.frequency.value = note.midi >= 42 && note.midi <= 51 ? 6000 : 1800;
      src.connect(filter);
      filter.connect(gain);
      src.start(start);
      src.stop(start + 0.12);
      sources.push(src);
    }
    return {
      stop: () => {
        for (const src of sources) {
          try {
            src.stop();
          } catch {
            /* already stopped */
          }
          try {
            src.disconnect();
          } catch {
            /* already gone */
          }
        }
        try {
          gain.disconnect();
        } catch {
          /* already gone */
        }
      },
    };
  }

  private stopVoices() {
    for (const voice of this.voices) {
      try {
        voice.stop();
      } catch {
        /* already gone */
      }
    }
    this.voices = [];
  }

  private tick = () => {
    if (!this.playing) return;
    const t = this.currentTime();
    this.onFrame?.(t, true);
    if (t >= this.duration) {
      this.playing = false;
      this.offset = 0;
      this.stopVoices();
      this.onFrame?.(0, false);
      return;
    }
    this.raf = window.requestAnimationFrame(this.tick);
  };

  private cancelTick() {
    if (this.raf) window.cancelAnimationFrame(this.raf);
    this.raf = 0;
  }
}
