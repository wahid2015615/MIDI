/** Lightweight SMF parser for in-studio preview (notes, duration, waveform). */

export type PreviewNote = {
  time: number;
  duration: number;
  midi: number;
  velocity: number;
  channel: number;
};

export type ParsedSmf = {
  duration: number;
  noteCount: number;
  notes: PreviewNote[];
  bpm: number | null;
  timeSignature: string | null;
  trackNames: string[];
};

type RawNote = {
  startTick: number;
  endTick: number;
  midi: number;
  velocity: number;
  channel: number;
};

function readStr(bytes: Uint8Array, offset: number, len: number): string {
  return String.fromCharCode(...bytes.subarray(offset, offset + len));
}

function readU32(bytes: Uint8Array, offset: number): number {
  return (
    ((bytes[offset] << 24) |
      (bytes[offset + 1] << 16) |
      (bytes[offset + 2] << 8) |
      bytes[offset + 3]) >>>
    0
  );
}

function readU16(bytes: Uint8Array, offset: number): number {
  return (bytes[offset] << 8) | bytes[offset + 1];
}

function readVlq(bytes: Uint8Array, offset: number): { value: number; next: number } {
  let value = 0;
  let i = offset;
  while (i < bytes.length) {
    const b = bytes[i++];
    value = (value << 7) | (b & 0x7f);
    if ((b & 0x80) === 0) break;
  }
  return { value, next: i };
}

function ticksToSeconds(
  tick: number,
  ppq: number,
  tempoMap: { tick: number; usPerQn: number }[],
): number {
  let seconds = 0;
  let lastTick = 0;
  let usPerQn = 500_000;
  for (const point of tempoMap) {
    if (point.tick >= tick) break;
    const span = point.tick - lastTick;
    seconds += (span * usPerQn) / 1_000_000 / ppq;
    lastTick = point.tick;
    usPerQn = point.usPerQn;
  }
  seconds += ((tick - lastTick) * usPerQn) / 1_000_000 / ppq;
  return seconds;
}

function closeRawNote(
  rawNotes: RawNote[],
  start: { tick: number; velocity: number },
  endTick: number,
  midi: number,
  channel: number,
) {
  rawNotes.push({
    startTick: start.tick,
    endTick: Math.max(start.tick + 1, endTick),
    midi,
    velocity: start.velocity,
    channel,
  });
}

export function parseSmf(bytes: Uint8Array): ParsedSmf {
  if (bytes.length < 14 || readStr(bytes, 0, 4) !== "MThd") {
    throw new Error("Not a Standard MIDI File");
  }
  const headerLen = readU32(bytes, 4);
  if (headerLen !== 6) {
    throw new Error("Invalid MIDI header");
  }
  const ntrks = readU16(bytes, 10);
  const division = readU16(bytes, 12);
  if (division & 0x8000) {
    throw new Error("SMPTE MIDI timing is not supported for preview");
  }
  const ppq = Math.max(1, division);

  const rawNotes: RawNote[] = [];
  const trackNames: string[] = [];
  const tempoMap: { tick: number; usPerQn: number }[] = [{ tick: 0, usPerQn: 500_000 }];
  let timeSignature: string | null = null;
  let pos = 14;

  for (let t = 0; t < ntrks; t += 1) {
    if (pos + 8 > bytes.length || readStr(bytes, pos, 4) !== "MTrk") {
      break;
    }
    const tlen = readU32(bytes, pos + 4);
    pos += 8;
    const end = pos + tlen;
    let tick = 0;
    let running = 0;
    const open = new Map<string, { tick: number; velocity: number }>();

    while (pos < end) {
      const delta = readVlq(bytes, pos);
      pos = delta.next;
      tick += delta.value;
      if (pos >= end) break;

      let status = bytes[pos];
      if (status < 0x80) {
        status = running;
      } else {
        pos += 1;
        running = status;
      }

      if (status === 0xff) {
        const type = bytes[pos++];
        const len = readVlq(bytes, pos);
        pos = len.next;
        const data = bytes.subarray(pos, pos + len.value);
        pos += len.value;
        running = 0;
        if (type === 0x51 && data.length >= 3) {
          const usPerQn = (data[0] << 16) | (data[1] << 8) | data[2];
          if (tick === 0) {
            tempoMap[0] = { tick: 0, usPerQn };
          } else {
            tempoMap.push({ tick, usPerQn });
          }
        } else if (type === 0x58 && data.length >= 2 && !timeSignature) {
          timeSignature = `${data[0]}/${2 ** data[1]}`;
        } else if (type === 0x03 && data.length) {
          const name = Array.from(data)
            .map((c) => (c >= 32 && c < 127 ? String.fromCharCode(c) : " "))
            .join("")
            .trim();
          if (name) trackNames.push(name);
        }
        continue;
      }

      if (status === 0xf0 || status === 0xf7) {
        const len = readVlq(bytes, pos);
        pos = len.next + len.value;
        running = 0;
        continue;
      }

      const cmd = status & 0xf0;
      const channel = status & 0x0f;
      if (cmd === 0xc0 || cmd === 0xd0) {
        pos += 1;
        continue;
      }
      const a = bytes[pos++];
      const b = cmd === 0xf0 ? 0 : bytes[pos++];
      if (cmd === 0x90 || cmd === 0x80) {
        const key = `${channel}:${a}`;
        if (cmd === 0x90 && b > 0) {
          const prev = open.get(key);
          if (prev) closeRawNote(rawNotes, prev, tick, a, channel);
          open.set(key, { tick, velocity: b });
        } else {
          const start = open.get(key);
          if (start) {
            open.delete(key);
            closeRawNote(rawNotes, start, tick, a, channel);
          }
        }
      }
    }
    for (const [key, start] of open) {
      const [chStr, midiStr] = key.split(":");
      closeRawNote(rawNotes, start, tick, Number(midiStr), Number(chStr));
    }
    pos = end;
  }

  tempoMap.sort((x, y) => x.tick - y.tick);
  const notes: PreviewNote[] = rawNotes.map((n) => {
    const startSec = ticksToSeconds(n.startTick, ppq, tempoMap);
    const endSec = Math.max(
      startSec + 0.04,
      ticksToSeconds(n.endTick, ppq, tempoMap),
    );
    return {
      time: startSec,
      duration: endSec - startSec,
      midi: n.midi,
      velocity: n.velocity,
      channel: n.channel,
    };
  });
  const duration = notes.reduce((max, n) => Math.max(max, n.time + n.duration), 0);
  const firstTempo = tempoMap[0]?.usPerQn ?? 500_000;
  const bpm = Math.round(60_000_000 / firstTempo);

  return {
    duration: Math.max(0.2, duration),
    noteCount: notes.length,
    notes: notes.sort((a, b) => a.time - b.time),
    bpm: Number.isFinite(bpm) ? bpm : null,
    timeSignature,
    trackNames,
  };
}

/** Compoxer-style vertical-bar amplitudes (0..1 per bar). */
export function waveformFromNotes(
  notes: PreviewNote[],
  duration: number,
  bins = 96,
): number[] {
  const samples = new Float32Array(bins);
  if (!notes.length || duration <= 0) {
    return Array.from({ length: bins }, (_, i) => 0.12 + 0.08 * Math.sin(i * 0.35));
  }
  for (const note of notes) {
    const start = Math.floor((note.time / duration) * bins);
    const end = Math.max(
      start + 1,
      Math.ceil(((note.time + note.duration) / duration) * bins),
    );
    const amp = 0.22 + (note.velocity / 127) * 0.55 + ((note.midi % 12) / 12) * 0.22;
    for (let i = Math.max(0, start); i < Math.min(bins, end); i += 1) {
      const center = (start + end) / 2;
      const fall = 1 - Math.min(1, Math.abs(i - center) / Math.max(1, (end - start) / 2));
      samples[i] = Math.max(samples[i], amp * (0.45 + 0.55 * fall));
    }
  }
  let peak = 0;
  for (const v of samples) peak = Math.max(peak, v);
  return Array.from(samples, (v, i) => {
    const floor = 0.08 + 0.04 * Math.abs(Math.sin(i * 0.7));
    if (peak <= 0) return floor;
    return Math.min(1, Math.max(floor, (v / peak) * 0.95));
  });
}
