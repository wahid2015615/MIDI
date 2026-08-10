export const KEYS = [
  "C Major",
  "G Major",
  "D Major",
  "A Major",
  "E Major",
  "F Major",
  "Bb Major",
  "Eb Major",
  "A Minor",
  "E Minor",
  "D Minor",
  "C Minor",
  "F Minor",
  "G Minor",
  "B Minor",
];

/** Must match backend `app.core.engine.BPM_MIN` / `BPM_MAX`. */
export const BPM_MIN = 4;
export const BPM_MAX = 300;

/**
 * Bars limits.
 * Frontend UI uses 1–128; backend API accepts 1–512 for future compatibility.
 * Both share the same minimum and default.
 */
export const BARS_MIN = 1;
export const BARS_MAX = 128;
export const BARS_MAX_API = 512;
export const BARS_DEFAULT = 16;

/** Default download names — mode prefix so Text / Chords / Notes are obvious. */
export const DEFAULT_FILENAME_BY_MODE = {
  text: "text_output.mid",
  chords: "chords_output.mid",
  notes: "notes_output.mid",
} as const;

/** Stock / preset names that may auto-update when the mode tab changes. */
export const STOCK_FILENAMES = new Set<string>([
  ...Object.values(DEFAULT_FILENAME_BY_MODE),
  // Older defaults / presets (still treated as non-custom)
  "generated.mid",
  "uplifting_piano.mid",
  "chords.mid",
  "notes.mid",
  "progression.mid",
  "note_list.mid",
  "happy_piano.mid",
  "sad_violin.mid",
  "text_happy_piano.mid",
  "text_sad_violin.mid",
  "chords_progression.mid",
  "notes_list.mid",
]);

export function defaultFilenameForMode(
  mode: keyof typeof DEFAULT_FILENAME_BY_MODE,
): string {
  return DEFAULT_FILENAME_BY_MODE[mode];
}

/** Must match backend `app.core.catalog.MOODS` / `STYLES`. */
export const MOODS = [
  "Happy",
  "Sad",
  "Calm",
  "Energetic",
  "Epic",
  "Dark",
  "Romantic",
  "Hopeful",
  "Emotional",
  "Aggressive",
  "Mysterious",
  "Dreamy",
  "Cinematic",
  "Uplifting",
  "Relaxing",
  "Tense",
  "Melancholic",
  "Playful",
  "Nostalgic",
  "Inspirational",
] as const;

export const STYLES = [
  "Pop",
  "Rock",
  "Hip Hop",
  "Trap",
  "EDM",
  "House",
  "Techno",
  "Lo-Fi",
  "Jazz",
  "Blues",
  "Classical",
  "Orchestral",
  "Cinematic",
  "Ambient",
  "Synthwave",
  "Funk",
  "R&B",
  "Country",
  "Folk",
  "Reggae",
] as const;

export type Mood = (typeof MOODS)[number];
export type Style = (typeof STYLES)[number];

export const DEFAULT_MOOD: Mood = "Happy";
export const DEFAULT_STYLE: Style = "Pop";

/** Must match backend `TS_NUMERATOR_*` / `VALID_TS_DENOMINATORS`. */
export const TS_NUMERATOR_MIN = 1;
export const TS_NUMERATOR_MAX = 16;
export const TS_DENOMINATORS = [1, 2, 4, 8, 16, 32] as const;
export type TsDenominator = (typeof TS_DENOMINATORS)[number];

export const DEFAULT_TIME_SIGNATURE = {
  numerator: 4,
  denominator: 4 as TsDenominator,
};

export const DEFAULT_INSTRUMENTS = [
  "acoustic_grand_piano",
  "electric_piano_1",
  "steel_guitar",
  "electric_bass_finger",
  "string_ensemble_1",
  "violin",
  "flute",
  "lead_1_square",
  "drum_kit",
];

export function labelize(id: string) {
  return id.replaceAll("_", " ");
}

/** Align with backend ``is_drum_instrument`` — melodic roles must not pick these. */
export function isDrumInstrument(id: string): boolean {
  const lower = id.trim().toLowerCase();
  const spaced = lower.replaceAll("_", " ").replaceAll("-", " ");
  return (
    spaced === "drums" ||
    spaced === "drum" ||
    spaced === "drum kit" ||
    lower === "drum_kit" ||
    lower === "drums"
  );
}

/**
 * Map notes-mode @track / [Section] labels onto mixer roles.
 * Must stay aligned with backend `composer._canonical_track_name`.
 */
export function canonicalTrackRole(
  name: string,
): "melody" | "chords" | "bass" | "drums" | null {
  const raw = (name || "").trim();
  if (!raw) return null;
  const lower = raw.toLowerCase();
  const aliases: Record<string, "melody" | "chords" | "bass" | "drums"> = {
    melody: "melody",
    lead: "melody",
    chords: "chords",
    chord: "chords",
    harmony: "chords",
    harmonies: "chords",
    pad: "chords",
    pads: "chords",
    keys: "chords",
    comp: "chords",
    accompaniment: "chords",
    bass: "bass",
    drums: "drums",
    drum: "drums",
    percussion: "drums",
    perc: "drums",
  };
  const compounds: Record<string, "melody" | "chords" | "bass" | "drums"> = {
    bassline: "bass",
    basslines: "bass",
    drumkit: "drums",
    drumkits: "drums",
    chordpad: "chords",
    chordpads: "chords",
  };
  if (aliases[lower]) return aliases[lower];
  if (compounds[lower]) return compounds[lower];
  const tokens = lower.split(/[^a-z0-9]+/).filter(Boolean);
  for (const tok of tokens) {
    if (aliases[tok]) return aliases[tok];
  }
  for (const tok of tokens) {
    if (compounds[tok]) return compounds[tok];
  }
  return null;
}

export function clampBpm(value: number): number {
  // Empty/cleared inputs become 0 via Number("") — treat as default, not BPM_MIN (4)
  if (!Number.isFinite(value) || value <= 0) return 120;
  return Math.min(BPM_MAX, Math.max(BPM_MIN, value));
}

export function isValidBars(value: number, maximum: number = BARS_MAX): boolean {
  return Number.isInteger(value) && value >= BARS_MIN && value <= maximum;
}

export function clampBars(value: number, maximum: number = BARS_MAX): number {
  if (!Number.isFinite(value)) return BARS_DEFAULT;
  return Math.min(maximum, Math.max(BARS_MIN, Math.round(value)));
}

export function normalizeBars(value: number, maximum: number = BARS_MAX): number {
  if (!isValidBars(value, maximum)) {
    throw new Error(
      `bars must be between ${BARS_MIN} and ${maximum}, got ${value}`,
    );
  }
  return value;
}

export function isValidMood(value: string): value is Mood {
  return (MOODS as readonly string[]).includes(value);
}

export function isValidStyle(value: string): value is Style {
  return (STYLES as readonly string[]).includes(value);
}

export function normalizeMood(value: string): Mood {
  const found = MOODS.find((m) => m.toLowerCase() === value.trim().toLowerCase());
  if (!found) {
    throw new Error(
      `Unsupported mood "${value}". Allowed values: ${MOODS.join(", ")}`,
    );
  }
  return found;
}

export function normalizeStyle(value: string): Style {
  const raw = value.trim().toLowerCase();
  const key = raw.replace(/[_-]+/g, " ").replace(/&/g, " and ").replace(/\s+/g, " ");
  const aliases: Record<string, Style> = {
    lofi: "Lo-Fi",
    "lo fi": "Lo-Fi",
    hiphop: "Hip Hop",
    "hip hop": "Hip Hop",
    "hip-hop": "Hip Hop",
    rnb: "R&B",
    "r and b": "R&B",
    "r & b": "R&B",
    "synth wave": "Synthwave",
    synthwave: "Synthwave",
  };
  if (aliases[key] || aliases[raw]) {
    return aliases[key] || aliases[raw];
  }
  const found = STYLES.find((s) => {
    const sk = s
      .toLowerCase()
      .replace(/-/g, " ")
      .replace(/&/g, " and ")
      .replace(/\s+/g, " ");
    return sk === key || s.toLowerCase() === raw;
  });
  if (!found) {
    throw new Error(
      `Unsupported style "${value}". Allowed values: ${STYLES.join(", ")}`,
    );
  }
  return found;
}

export function isValidTimeSignature(
  numerator: number,
  denominator: number,
): boolean {
  return (
    Number.isInteger(numerator) &&
    Number.isInteger(denominator) &&
    numerator >= TS_NUMERATOR_MIN &&
    numerator <= TS_NUMERATOR_MAX &&
    (TS_DENOMINATORS as readonly number[]).includes(denominator)
  );
}

export function normalizeTimeSignature(
  numerator: number,
  denominator: number,
): { numerator: number; denominator: TsDenominator } {
  if (!isValidTimeSignature(numerator, denominator)) {
    throw new Error(
      `Invalid time signature ${numerator}/${denominator}. ` +
        `Numerator must be ${TS_NUMERATOR_MIN}–${TS_NUMERATOR_MAX}; ` +
        `denominator must be one of ${TS_DENOMINATORS.join(", ")}.`,
    );
  }
  return {
    numerator,
    denominator: denominator as TsDenominator,
  };
}
