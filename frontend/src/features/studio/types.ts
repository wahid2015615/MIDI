export type Mode = "text" | "chords" | "notes";

export type TrackRole = "melody" | "chords" | "bass" | "drums";

export type TrackOptions = {
  melody: boolean;
  chords: boolean;
  bass: boolean;
  drums: boolean;
};

export type TrackMixOptions = {
  mute_melody?: boolean;
  mute_chords?: boolean;
  mute_bass?: boolean;
  mute_drums?: boolean;
  solo_melody?: boolean;
  solo_chords?: boolean;
  solo_bass?: boolean;
  solo_drums?: boolean;
  volume_melody?: number;
  volume_chords?: number;
  volume_bass?: number;
  volume_drums?: number;
  pan_melody?: number;
  pan_chords?: number;
  pan_bass?: number;
  pan_drums?: number;
  instrument_melody?: string | null;
  instrument_chords?: string | null;
  instrument_bass?: string | null;
  instrument_drums?: string | null;
  channel_melody?: number | null;
  channel_chords?: number | null;
  channel_bass?: number | null;
  channel_drums?: number | null;
};

export type TimeSignatureOptions = {
  numerator: number;
  denominator: 1 | 2 | 4 | 8 | 16 | 32;
};

export type TimingOptions = {
  quantize: string | null;
  quantize_duration?: boolean;
  swing: number;
  swing_grid?: string;
  humanize: boolean;
  humanize_timing?: number;
  humanize_velocity?: number;
  humanize_duration?: number;
  humanize_controllers?: boolean;
  ppq: number;
  seed?: number | null;
};

export type ExpressionOptions = {
  sustain: boolean;
  modulation: boolean;
  pitch_bend: boolean;
  /** CC64 pedal-down value (default 127). */
  sustain_on_value?: number;
  /** CC64 pedal-up value (default 0). */
  sustain_off_value?: number;
  /** Fraction of each bar the pedal stays down (default 0.92). */
  sustain_hold_ratio?: number;
  /** Peak CC1 intensity for melody accents (default 24). */
  modulation_value?: number;
  /** Bars between modulation accents (default 2). */
  modulation_interval_bars?: number;
  /** Accent length as a fraction of one bar (default 0.5). */
  modulation_accent_ratio?: number;
  /** Depth below pitch-bend center for lead scoops (default 400). */
  pitch_bend_scoop_depth?: number;
  /** Bars between pitch-bend scoops (default 4). */
  pitch_bend_interval_bars?: number;
  /** Scoop return duration in beats (default 0.25). */
  pitch_bend_scoop_beats?: number;
};

export type GenerateResult = {
  filename: string;
  blob: Blob;
  url: string;
  bytes: Uint8Array;
  bpm: string | null;
  bars: string | null;
  tracks: string | null;
  ppq?: string | null;
  key?: string | null;
  timeSig?: string | null;
};

export type StudioMidiResult = GenerateResult & {
  mode: Mode;
  quote: string;
  /** Exact form values at generate time — display these, not SMF headers. */
  selectedBpm: number;
  selectedKey: string;
  selectedTimeSig: string;
  selectedBars: number | null;
  style?: string;
  mood?: string;
};
