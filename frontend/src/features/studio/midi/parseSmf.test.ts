import { describe, expect, it } from "vitest";
import { parseSmf, waveformFromNotes } from "./parseSmf";

function u16(n: number): number[] {
  return [(n >> 8) & 0xff, n & 0xff];
}

function u32(n: number): number[] {
  return [(n >>> 24) & 0xff, (n >>> 16) & 0xff, (n >>> 8) & 0xff, n & 0xff];
}

function bytesOf(...parts: number[][]): Uint8Array {
  return Uint8Array.from(parts.flat());
}

/** Type-0 SMF: one C4 quarter at 120 BPM, PPQ 480. */
function oneNoteSmf(): Uint8Array {
  const track = [
    0x00, 0xff, 0x51, 0x03, 0x07, 0xa1, 0x20, // set_tempo 500000
    0x00, 0x90, 0x3c, 0x40, // note on C4
    0x83, 0x60, 0x80, 0x3c, 0x40, // 480 ticks later note off
    0x00, 0xff, 0x2f, 0x00,
  ];
  return bytesOf(
    [0x4d, 0x54, 0x68, 0x64],
    u32(6),
    u16(0),
    u16(1),
    u16(480),
    [0x4d, 0x54, 0x72, 0x6b],
    u32(track.length),
    track,
  );
}

/** Same pitch re-on before off — both notes must be kept. */
function stackedSameKeySmf(): Uint8Array {
  const track = [
    0x00, 0x90, 0x3c, 0x40,
    0x00, 0x90, 0x3c, 0x50,
    0x78, 0x80, 0x3c, 0x40,
    0x78, 0x80, 0x3c, 0x40,
    0x00, 0xff, 0x2f, 0x00,
  ];
  return bytesOf(
    [0x4d, 0x54, 0x68, 0x64],
    u32(6),
    u16(0),
    u16(1),
    u16(480),
    [0x4d, 0x54, 0x72, 0x6b],
    u32(track.length),
    track,
  );
}

describe("parseSmf", () => {
  it("rejects non-MIDI", () => {
    expect(() => parseSmf(new Uint8Array([1, 2, 3, 4]))).toThrow(/Standard MIDI/);
  });

  it("parses a single note and tempo", () => {
    const parsed = parseSmf(oneNoteSmf());
    expect(parsed.noteCount).toBe(1);
    expect(parsed.notes[0]?.midi).toBe(60);
    expect(parsed.bpm).toBe(120);
    expect(parsed.duration).toBeGreaterThan(0.4);
  });

  it("keeps stacked same-key note-ons", () => {
    const parsed = parseSmf(stackedSameKeySmf());
    expect(parsed.noteCount).toBe(2);
  });
});

describe("waveformFromNotes", () => {
  it("returns bins in 0..1", () => {
    const wave = waveformFromNotes(
      [{ time: 0, duration: 0.5, midi: 60, velocity: 90, channel: 0 }],
      1,
      16,
    );
    expect(wave).toHaveLength(16);
    expect(wave.every((v) => v >= 0 && v <= 1)).toBe(true);
  });
});
