"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
  cancelGenerationRequest,
  fetchHealth,
  fetchMeta,
  generateFromChords,
  generateFromNotes,
  generateFromText,
  isAbortError,
  parseTextPrompt,
  resolveApiBase,
} from "../api/studioApi";
import { MidiResultCard } from "./MidiResultCard";
import {
  BARS_DEFAULT,
  BARS_MAX,
  BARS_MAX_API,
  BARS_MIN,
  BPM_MAX,
  BPM_MIN,
  clampBars,
  clampBpm,
  canonicalTrackRole,
  DEFAULT_FILENAME_BY_MODE,
  DEFAULT_INSTRUMENTS,
  DEFAULT_MOOD,
  DEFAULT_STYLE,
  DEFAULT_TIME_SIGNATURE,
  defaultFilenameForMode,
  isDrumInstrument,
  isValidBars,
  isValidStyle,
  isValidTimeSignature,
  KEYS,
  labelize,
  MOODS,
  normalizeBars,
  normalizeMood,
  normalizeStyle,
  normalizeTimeSignature,
  STOCK_FILENAMES,
  STYLES,
  TS_DENOMINATORS,
  TS_NUMERATOR_MAX,
  TS_NUMERATOR_MIN,
  type TsDenominator,
} from "../constants";
import type { Mode, StudioMidiResult, TrackRole } from "../types";
import { Field } from "../../../shared/ui/Field";
import { IconSelect } from "../../../shared/ui/IconSelect";
import { TypeIcon } from "../../../shared/ui/TypeIcon";

/** Mirror backend `parse_progression_string` (incl. jazz hyphen repair). */
function splitChordProgression(text: string): string[] {
  const normalized = text
    .replaceAll("→", "->")
    .replaceAll("–", "-")
    .replaceAll("—", "-");

  const expandMixed = (parts: string[]) => {
    const expanded: string[] = [];
    for (const part of parts) {
      const textPart = part.trim();
      if (!textPart) continue;
      if (/\s-\s/.test(textPart)) {
        expanded.push(...textPart.split(/\s+-\s+/));
      } else if (textPart.includes(",")) {
        expanded.push(...textPart.split(","));
      } else {
        expanded.push(textPart);
      }
    }
    return expanded;
  };

  let rawParts: string[];
  if (normalized.includes("|")) {
    rawParts = expandMixed(normalized.split("|"));
  } else if (normalized.includes("->")) {
    rawParts = expandMixed(normalized.split(/\s*->\s*/));
  } else if (/\s-\s/.test(normalized)) {
    // Spaced dashes: safe for jazz C-7 - F-7
    rawParts = normalized.split(/\s+-\s+/);
  } else if (normalized.includes(",")) {
    rawParts = normalized.split(",");
  } else if (normalized.includes("-")) {
    // Unspaced C-G-Am; repair C-7 → C + 7 fragments
    const repaired: string[] = [];
    for (const part of normalized.split("-")) {
      const token = part.trim().replace(/^[,|]+|[,|]+$/g, "").trim();
      if (!token) continue;
      if (repaired.length && !/^[A-Ga-g]/.test(token)) {
        repaired[repaired.length - 1] = `${repaired[repaired.length - 1]}-${token}`;
      } else {
        repaired.push(token);
      }
    }
    return repaired;
  } else {
    rawParts = normalized.split(/\s+/);
  }

  return rawParts
    .map((p) => p.trim().replace(/^[,|]+|[,|]+$/g, "").trim())
    .filter(Boolean);
}

function looksLikeChordSymbol(token: string): boolean {
  return /^[A-Ga-g](?:#|b|♯|♭)?/.test(token.trim());
}

/** Rough Notes duration in bars from rest/note duration tokens. */
function estimateNotesBars(notesText: string, beatsPerBar: number): number {
  const tokenBeats: Record<string, number> = {
    w: 4,
    whole: 4,
    h: 2,
    half: 2,
    q: 1,
    quarter: 1,
    e: 0.5,
    eighth: 0.5,
    "8th": 0.5,
    s: 0.25,
    sixteenth: 0.25,
    "16th": 0.25,
  };
  const perTrack = new Map<string, number>();
  let current = "melody";
  perTrack.set(current, 0);
  for (const raw of notesText.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const lower = line.toLowerCase();
    if (lower.startsWith("#") && !lower.startsWith("#track")) continue;
    const trackMatch = /^(?:@track|#track)\s+(\S+)/i.exec(line);
    const sectionMatch = /^\[\s*([A-Za-z]\w*)/i.exec(line);
    if (trackMatch || sectionMatch) {
      const name = (trackMatch?.[1] || sectionMatch?.[1] || "melody").toLowerCase();
      current = name;
      if (!perTrack.has(current)) perTrack.set(current, 0);
      continue;
    }
    if (lower.startsWith("[")) continue;
    const parts = line.split(/\s+/);
    let beats = 1;
    if (lower === "r" || lower.startsWith("rest") || lower.startsWith("r ")) {
      const durTok = parts.slice(1).join(" ").toLowerCase() || "quarter";
      const first = durTok.split(/\s+/)[0] || "quarter";
      beats = (tokenBeats[first] ?? Number(first)) || 1;
    } else {
      // duration is after pitches
      let i = 0;
      while (i < parts.length && /^[A-Ga-g]/.test(parts[i])) i += 1;
      const durTok = (parts[i] || "q").toLowerCase();
      beats = (tokenBeats[durTok] ?? Number(durTok)) || 1;
    }
    if (!Number.isFinite(beats) || beats <= 0) beats = 1;
    perTrack.set(current, (perTrack.get(current) || 0) + beats);
  }
  const maxBeats = Math.max(0, ...perTrack.values());
  return Math.max(1, Math.ceil(maxBeats / Math.max(0.25, beatsPerBar)));
}

const TRACK_META: {
  id: TrackRole;
  label: string;
  color: string;
}[] = [
  { id: "melody", label: "Melody", color: "var(--track-melody)" },
  { id: "chords", label: "Chords", color: "var(--track-chords)" },
  { id: "bass", label: "Bass", color: "var(--track-bass)" },
  { id: "drums", label: "Drums", color: "var(--track-drums)" },
];

/** Form fields that prompt auto-fill may update (unless user has edited them). */
type PromptFillField =
  | "bpm"
  | "bars"
  | "key"
  | "mood"
  | "style"
  | "instrument"
  | "time_signature"
  | "tracks_chords"
  | "tracks_bass"
  | "tracks_drums";

function estimateSeconds(bars: number, bpm: number, beatsPerBar = 4) {
  if (!bpm || bpm < BPM_MIN) return 0;
  return Math.round((bars * beatsPerBar * 60) / bpm);
}

export default function StudioPage() {
  const [mode, setMode] = useState<Mode>("text");
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [apiVersion, setApiVersion] = useState("");
  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null);
  const [aiOnline, setAiOnline] = useState<boolean | null>(null);
  const [aiLoaded, setAiLoaded] = useState<boolean | null>(null);
  const [aiModel, setAiModel] = useState("");
  const [aiProvider, setAiProvider] = useState("local");
  const [apiDisplayBase, setApiDisplayBase] = useState(API_BASE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [midiResult, setMidiResult] = useState<StudioMidiResult | null>(null);
  const midiUrlRef = useRef<string | null>(null);
  const resultCardRef = useRef<HTMLDivElement | null>(null);

  function replaceMidiResult(next: StudioMidiResult | null) {
    if (midiUrlRef.current) {
      URL.revokeObjectURL(midiUrlRef.current);
      midiUrlRef.current = null;
    }
    if (next) midiUrlRef.current = next.url;
    setMidiResult(next);
  }

  const [prompt, setPrompt] = useState(
    "Generate a 16-bar uplifting piano melody in C Major at 128 BPM.",
  );
  const [progression, setProgression] = useState("C | G | Am | F");
  const [notesText, setNotesText] = useState(
    ["C4 q", "E4 q", "G4 h", "rest q", "C5 q", "B4 q", "A4 h"].join("\n"),
  );

  const [bpm, setBpm] = useState(128);
  const [bars, setBars] = useState(BARS_DEFAULT);
  const [barsPerChord, setBarsPerChord] = useState(1);
  const [seed, setSeed] = useState(42);
  const [key, setKey] = useState("C Major");
  const [keyOptions, setKeyOptions] = useState<string[]>(KEYS);
  const [tsNumerator, setTsNumerator] = useState(DEFAULT_TIME_SIGNATURE.numerator);
  const [tsDenominator, setTsDenominator] = useState<TsDenominator>(
    DEFAULT_TIME_SIGNATURE.denominator,
  );
  const [moodOptions, setMoodOptions] = useState<string[]>([...MOODS]);
  const [styleOptions, setStyleOptions] = useState<string[]>([...STYLES]);
  const [quantizeOptions, setQuantizeOptions] = useState<string[]>([
    "1/4",
    "1/8",
    "1/16",
    "1/32",
  ]);
  const [swingGridOptions, setSwingGridOptions] = useState<string[]>([
    "1/4",
    "1/8",
    "1/16",
    "1/32",
  ]);
  const [ppqOptions, setPpqOptions] = useState<number[]>([
    96, 192, 240, 384, 480, 960, 1920,
  ]);
  const [mood, setMood] = useState<string>(DEFAULT_MOOD);
  const [style, setStyle] = useState<string>(DEFAULT_STYLE);
  const [fileType, setFileType] = useState<0 | 1>(1);
  const [filename, setFilename] = useState<string>(DEFAULT_FILENAME_BY_MODE.text);
  /** When false, switching Text/Chords/Notes can refresh a stock default name. */
  const filenameCustomRef = useRef(false);

  function applyStockFilename(name: string) {
    filenameCustomRef.current = false;
    setFilename(name);
  }

  function setModeAndMaybeFilename(next: Mode) {
    setMode(next);
    const current = filename.trim();
    if (!filenameCustomRef.current || !current || STOCK_FILENAMES.has(current)) {
      applyStockFilename(defaultFilenameForMode(next));
    }
  }

  /** Fields the user edited manually — prompt auto-fill must not overwrite these. */
  const touchedRef = useRef<Set<PromptFillField>>(new Set());
  const markTouched = useCallback((field: PromptFillField) => {
    touchedRef.current.add(field);
  }, []);
  const clearTouched = useCallback(() => {
    touchedRef.current.clear();
  }, []);
  const isUntouched = useCallback(
    (field: PromptFillField) => !touchedRef.current.has(field),
    [],
  );
  /** After a Quick Preset, lock fields so prompt auto-fill cannot overwrite them. */
  const lockPresetFields = useCallback(() => {
    clearTouched();
    (
      [
        "bpm",
        "bars",
        "key",
        "mood",
        "style",
        "instrument",
        "time_signature",
        "tracks_chords",
        "tracks_bass",
        "tracks_drums",
      ] as PromptFillField[]
    ).forEach(markTouched);
  }, [clearTouched, markTouched]);

  const [tracks, setTracks] = useState({
    melody: true,
    chords: true,
    bass: true,
    drums: false,
  });
  const [mute, setMute] = useState({
    melody: false,
    chords: false,
    bass: false,
    drums: false,
  });
  const [solo, setSolo] = useState({
    melody: false,
    chords: false,
    bass: false,
    drums: false,
  });
  const [volume, setVolume] = useState({
    melody: 100,
    chords: 90,
    bass: 100,
    drums: 100,
  });
  const [pan, setPan] = useState({
    melody: 64,
    chords: 64,
    bass: 64,
    drums: 64,
  });
  const [trackInstrument, setTrackInstrument] = useState({
    melody: "acoustic_grand_piano",
    chords: "electric_piano_1",
    bass: "electric_bass_finger",
    drums: "drum_kit",
  });
  const [trackChannel, setTrackChannel] = useState<{
    melody: number | null;
    chords: number | null;
    bass: number | null;
    drums: number | null;
  }>({
    melody: null,
    chords: null,
    bass: null,
    drums: 9,
  });

  const [quantize, setQuantize] = useState("1/16");
  const [quantizeDuration, setQuantizeDuration] = useState(true);
  const [swingMpc, setSwingMpc] = useState(50); // MPC-style: 50=straight, ~66=triplet
  const [swingGrid, setSwingGrid] = useState("1/8");
  const [humanize, setHumanize] = useState(false);
  const [humanizeTiming, setHumanizeTiming] = useState(0.02);
  const [humanizeVelocity, setHumanizeVelocity] = useState(8);
  const [humanizeDuration, setHumanizeDuration] = useState(0.01);
  const [humanizeControllers, setHumanizeControllers] = useState(false);
  const [ppq, setPpq] = useState(480);
  const [sustain, setSustain] = useState(true);
  const [modulation, setModulation] = useState(true);
  const [pitchBend, setPitchBend] = useState(true);
  // Advanced expression — defaults match backend hardcoded legacy values
  const [exprAdvancedOpen, setExprAdvancedOpen] = useState(false);
  const [sustainOnValue, setSustainOnValue] = useState(127);
  const [sustainOffValue, setSustainOffValue] = useState(0);
  const [sustainHoldRatio, setSustainHoldRatio] = useState(0.92);
  const [modulationValue, setModulationValue] = useState(24);
  const [modulationIntervalBars, setModulationIntervalBars] = useState(2);
  const [modulationAccentRatio, setModulationAccentRatio] = useState(0.5);
  const [pitchBendScoopDepth, setPitchBendScoopDepth] = useState(400);
  const [pitchBendIntervalBars, setPitchBendIntervalBars] = useState(4);
  const [pitchBendScoopBeats, setPitchBendScoopBeats] = useState(0.25);

  const [instrumentOptions, setInstrumentOptions] = useState(DEFAULT_INSTRUMENTS);
  const abortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const healthFailStreakRef = useRef(0);
  const healthSeqRef = useRef(0);

  useEffect(() => {
    let alive = true;
    setApiDisplayBase(resolveApiBase());

    async function refreshHealth(probe: boolean) {
      const seq = ++healthSeqRef.current;
      try {
        const health = await fetchHealth({ probe });
        if (!alive || seq !== healthSeqRef.current) return;
        healthFailStreakRef.current = 0;
        setApiOk(true);
        setApiVersion(health.version);
        setAiConfigured(Boolean(health.ai?.configured));
        setAiOnline(
          health.ai?.configured ? Boolean(health.ai?.online) : false,
        );
        setAiLoaded(
          health.ai?.configured
            ? Boolean(
                health.ai?.loaded ??
                  (probe ? health.ai?.online : false),
              )
            : false,
        );
        setAiModel(health.ai?.model || "");
        setAiProvider(health.ai?.provider || "local");
      } catch {
        if (!alive || seq !== healthSeqRef.current) return;
        healthFailStreakRef.current += 1;
        // Ignore a single transient failure; mark offline after 2 consecutive misses.
        if (healthFailStreakRef.current >= 2) {
          setApiOk(false);
          setAiOnline(false);
          setAiLoaded(false);
        }
      }
    }

    async function refreshMeta() {
      try {
        const meta = await fetchMeta();
        if (!alive) return;
        setApiDisplayBase(meta.apiBase || resolveApiBase());
        if (meta.instruments?.instruments?.length) {
          setInstrumentOptions(
            meta.instruments.instruments.map((i: { id: string }) => i.id),
          );
        }
        const stylesMeta = meta.styles;
        if (stylesMeta?.moods?.length) {
          setMoodOptions(stylesMeta.moods.map(String));
        }
        if (stylesMeta?.styles?.length) {
          setStyleOptions(stylesMeta.styles.map(String));
        }
        if (stylesMeta?.quantize_grids?.length) {
          setQuantizeOptions(stylesMeta.quantize_grids.map(String));
        }
        if (stylesMeta?.swing_grids?.length) {
          setSwingGridOptions(stylesMeta.swing_grids.map(String));
        }
        if (stylesMeta?.ppq_options?.length) {
          setPpqOptions(
            stylesMeta.ppq_options.map(Number).filter((n) => Number.isFinite(n)),
          );
        }
      } catch {
        // Meta failure must not mark the whole API offline
        console.warn("[studio] meta endpoints failed");
      }
    }

    void refreshHealth(true);
    void refreshMeta();

    // Light polls: no probe (avoids spamming logs during local generation)
    const interval = window.setInterval(() => {
      void refreshHealth(false);
    }, 60000);

    const onVisible = () => {
      if (document.visibilityState === "visible") void refreshHealth(false);
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      alive = false;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
      const pendingId = requestIdRef.current;
      void cancelGenerationRequest(String(pendingId));
      abortRef.current?.abort();
      if (midiUrlRef.current) {
        URL.revokeObjectURL(midiUrlRef.current);
        midiUrlRef.current = null;
      }
    };
  }, []);

  // Prompt → form auto-fill. Only detected fields; skip anything the user edited.
  useEffect(() => {
    if (mode !== "text") return;
    const trimmed = prompt.trim();
    if (!trimmed) return;

    const abort = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const parsed = await parseTextPrompt(trimmed, { signal: abort.signal });
        if (abort.signal.aborted) return;
        const d = parsed.detected ?? {
          bars: true,
          bpm: true,
          key: true,
          mood: true,
          style: true,
          instrument: true,
          include_chords: true,
          include_bass: true,
          include_drums: true,
          time_signature: true,
        };

        if (d.bpm && isUntouched("bpm") && parsed.bpm != null) {
          setBpm(clampBpm(Number(parsed.bpm)));
        }
        if (d.bars && isUntouched("bars") && parsed.bars != null) {
          setBars(clampBars(Number(parsed.bars)));
        }
        if (
          d.time_signature &&
          isUntouched("time_signature") &&
          parsed.time_signature
        ) {
          const num = Number(parsed.time_signature.numerator);
          const den = Number(parsed.time_signature.denominator);
          if (isValidTimeSignature(num, den)) {
            const safe = normalizeTimeSignature(num, den);
            setTsNumerator(safe.numerator);
            setTsDenominator(safe.denominator);
          }
        }
        if (d.key && isUntouched("key") && parsed.key) {
          setKeyOptions((prev) =>
            prev.includes(parsed.key) ? prev : [...prev, parsed.key],
          );
          setKey(parsed.key);
        }
        if (d.mood && isUntouched("mood") && parsed.mood) {
          const match = moodOptions.find(
            (m) => m.toLowerCase() === parsed.mood.trim().toLowerCase(),
          );
          if (match) setMood(match);
          else {
            try {
              setMood(normalizeMood(parsed.mood));
            } catch {
              /* ignore unknown mood from parse */
            }
          }
        }
        if (d.style && isUntouched("style") && parsed.style) {
          try {
            setStyle(normalizeStyle(parsed.style));
          } catch {
            const match = styleOptions.find(
              (s) => s.toLowerCase() === parsed.style.trim().toLowerCase(),
            );
            if (match) setStyle(match);
          }
        }
        if (d.instrument && isUntouched("instrument") && parsed.instrument) {
          setTrackInstrument((t) => ({
            ...t,
            melody: parsed.instrument,
          }));
          setInstrumentOptions((opts) =>
            opts.includes(parsed.instrument)
              ? opts
              : [...opts, parsed.instrument],
          );
        }
        if (d.include_chords && isUntouched("tracks_chords")) {
          setTracks((t) => ({ ...t, chords: parsed.include_chords }));
        }
        if (d.include_bass && isUntouched("tracks_bass")) {
          setTracks((t) => ({ ...t, bass: parsed.include_bass }));
        }
        if (d.include_drums && isUntouched("tracks_drums")) {
          setTracks((t) => ({ ...t, drums: parsed.include_drums }));
        }
      } catch (err) {
        if (isAbortError(err)) return;
        console.warn("[studio] prompt auto-fill failed:", err);
      }
    }, 400);

    return () => {
      abort.abort();
      window.clearTimeout(timer);
    };
  }, [prompt, mode, isUntouched, moodOptions, styleOptions]);

  const notesTrackRoles = useMemo(() => {
    const roles = new Set<TrackRole>();
    let hasUnmapped = false;
    const re =
      /^(?:@track|#track)\s+(\S+)|^\[\s*([A-Za-z][\w\s]*?)(?:\s+[^\]]+)?\s*\]/i;
    for (const raw of notesText.split("\n")) {
      const m = re.exec(raw.trim());
      if (!m) continue;
      const name = (m[1] || m[2] || "").trim();
      if (!name) continue;
      const role = canonicalTrackRole(name);
      if (role) roles.add(role);
      else hasUnmapped = true;
    }
    // Custom labels (Violin, …) follow Melody mix on the backend — keep Melody
    // active whenever an unmapped track exists (even alongside Bass/Drums).
    if (roles.size === 0 || hasUnmapped) roles.add("melody");
    return roles;
  }, [notesText]);

  const mix = useMemo(() => {
    const roleOn = (id: TrackRole) =>
      mode === "notes" ? notesTrackRoles.has(id) : tracks[id];
    return {
      mute_melody: roleOn("melody") && mute.melody,
      mute_chords: roleOn("chords") && mute.chords,
      mute_bass: roleOn("bass") && mute.bass,
      mute_drums: roleOn("drums") && mute.drums,
      solo_melody: roleOn("melody") && solo.melody,
      solo_chords: roleOn("chords") && solo.chords,
      solo_bass: roleOn("bass") && solo.bass,
      solo_drums: roleOn("drums") && solo.drums,
      volume_melody: volume.melody,
      volume_chords: volume.chords,
      volume_bass: volume.bass,
      volume_drums: volume.drums,
      pan_melody: pan.melody,
      pan_chords: pan.chords,
      pan_bass: pan.bass,
      pan_drums: pan.drums,
      instrument_melody: trackInstrument.melody,
      instrument_chords: trackInstrument.chords,
      instrument_bass: trackInstrument.bass,
      instrument_drums: trackInstrument.drums,
      // Melodic roles never send channel 9 (GM drums); Auto (null) lets backend assign
      channel_melody:
        trackChannel.melody === 9 ? null : trackChannel.melody,
      channel_chords:
        trackChannel.chords === 9 ? null : trackChannel.chords,
      channel_bass: trackChannel.bass === 9 ? null : trackChannel.bass,
      channel_drums: trackChannel.drums,
    };
  }, [
    mute,
    solo,
    volume,
    pan,
    trackInstrument,
    trackChannel,
    tracks,
    mode,
    notesTrackRoles,
  ]);

  // Melodic roles must never keep a drum kit selected (backend rejects it).
  useEffect(() => {
    setTrackInstrument((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const role of ["melody", "chords", "bass"] as const) {
        if (isDrumInstrument(next[role])) {
          next[role] =
            role === "chords"
              ? "electric_piano_1"
              : role === "bass"
                ? "electric_bass_finger"
                : "acoustic_grand_piano";
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [trackInstrument.melody, trackInstrument.chords, trackInstrument.bass]);

  const timing = useMemo(
    () => ({
      quantize: quantize || null,
      quantize_duration: quantizeDuration,
      // API expects delay fraction; UI uses MPC % (50=straight → 0 delay)
      swing: Math.max(0, Math.min(1, (swingMpc - 50) / 50)),
      swing_grid: swingGrid,
      humanize,
      humanize_timing: humanizeTiming,
      humanize_velocity: humanizeVelocity,
      humanize_duration: humanizeDuration,
      humanize_controllers: humanizeControllers,
      ppq,
    }),
    [
      quantize,
      quantizeDuration,
      swingMpc,
      swingGrid,
      humanize,
      humanizeTiming,
      humanizeVelocity,
      humanizeDuration,
      humanizeControllers,
      ppq,
    ],
  );

  const expression = useMemo(
    () => ({
      sustain,
      modulation,
      pitch_bend: pitchBend,
      sustain_on_value: sustainOnValue,
      sustain_off_value: sustainOffValue,
      sustain_hold_ratio: sustainHoldRatio,
      modulation_value: modulationValue,
      modulation_interval_bars: modulationIntervalBars,
      modulation_accent_ratio: modulationAccentRatio,
      pitch_bend_scoop_depth: pitchBendScoopDepth,
      pitch_bend_interval_bars: pitchBendIntervalBars,
      pitch_bend_scoop_beats: pitchBendScoopBeats,
    }),
    [
      sustain,
      modulation,
      pitchBend,
      sustainOnValue,
      sustainOffValue,
      sustainHoldRatio,
      modulationValue,
      modulationIntervalBars,
      modulationAccentRatio,
      pitchBendScoopDepth,
      pitchBendIntervalBars,
      pitchBendScoopBeats,
    ],
  );

  const activeTrackCount = useMemo(() => {
    const roleIncluded = (id: TrackRole) => {
      if (mode === "notes") return notesTrackRoles.has(id);
      return tracks[id];
    };
    // Solo only counts among enabled roles (matches backend _active_tracks).
    // Solo overrides mute so every soloed role exports together.
    const anySoloOn = TRACK_META.some(
      ({ id }) => roleIncluded(id) && solo[id],
    );
    return TRACK_META.filter(({ id }) => {
      if (!roleIncluded(id)) return false;
      if (anySoloOn) return solo[id];
      if (mute[id]) return false;
      return true;
    }).length;
  }, [tracks, mute, solo, mode, notesTrackRoles]);

  /** Text mode needs the local GGUF; chords + notes are deterministic. */
  const needsAi = mode === "text";
  // Configured file is enough — idle unload may clear RAM; generate will reload.
  const aiReady = !needsAi || aiConfigured === true;
  const promptReady = mode !== "text" || prompt.trim().length > 0;
  const generateBlocked =
    loading ||
    apiOk === false ||
    activeTrackCount === 0 ||
    !aiReady ||
    !promptReady;

  const beatsPerBar = tsNumerator * (4 / tsDenominator);
  const durationSec = estimateSeconds(
    mode === "chords"
      ? Math.max(
          1,
          splitChordProgression(progression).length *
            Math.max(0.0625, Number.isFinite(barsPerChord) ? barsPerChord : 1),
        )
      : mode === "notes"
        ? estimateNotesBars(notesText, beatsPerBar)
        : bars,
    bpm,
    beatsPerBar,
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (activeTrackCount === 0) {
      setError("Enable at least one track role before generating");
      return;
    }
    if (mode === "text" && !prompt.trim()) {
      setError("Enter a text prompt before generating");
      return;
    }
    if (needsAi && !aiReady) {
      setError(
        aiConfigured === false
          ? "Local GGUF model is missing — place it under backend/models/"
          : "Local model status unknown — wait for API health check",
      );
      return;
    }
    const safeBpm = clampBpm(bpm);
    if (safeBpm !== bpm) setBpm(safeBpm);
    if (mode === "text" && !isValidBars(bars)) {
      setError(`bars must be between ${BARS_MIN} and ${BARS_MAX}, got ${bars}`);
      return;
    }
    const safeBars = mode === "text" ? normalizeBars(bars) : bars;
    if (mode === "text") {
      if (!moodOptions.some((m) => m.toLowerCase() === mood.trim().toLowerCase())) {
        setError(
          `Unsupported mood "${mood}". Allowed values: ${moodOptions.join(", ")}`,
        );
        return;
      }
      if (
        !styleOptions.some((s) => s.toLowerCase() === style.trim().toLowerCase()) &&
        !isValidStyle(style)
      ) {
        setError(
          `Unsupported style "${style}". Allowed values: ${styleOptions.join(", ")}`,
        );
        return;
      }
    }
    const safeMood =
      mode === "text"
        ? moodOptions.find((m) => m.toLowerCase() === mood.trim().toLowerCase()) ||
          normalizeMood(mood)
        : mood;
    const safeStyle =
      mode === "text"
        ? (() => {
            try {
              return normalizeStyle(style);
            } catch {
              return (
                styleOptions.find(
                  (s) => s.toLowerCase() === style.trim().toLowerCase(),
                ) || style
              );
            }
          })()
        : style;
    if (!isValidTimeSignature(tsNumerator, tsDenominator)) {
      setError(
        `Invalid time signature ${tsNumerator}/${tsDenominator}. ` +
          `Use numerator ${TS_NUMERATOR_MIN}–${TS_NUMERATOR_MAX} and ` +
          `denominator ${TS_DENOMINATORS.join(", ")}.`,
      );
      return;
    }
    const safeTs = normalizeTimeSignature(tsNumerator, tsDenominator);

    if (sustain && sustainOnValue === sustainOffValue) {
      setError("Sustain on and off CC64 values must differ");
      return;
    }

    let chordParts: string[] = [];
    let notes: string[] = [];
    let safeBarsPerChord = 1;
    if (mode === "chords") {
      chordParts = splitChordProgression(progression);
      if (chordParts.length === 0) {
        setError("Enter at least one chord (e.g. C | G | Am | F)");
        return;
      }
      const bad = chordParts.filter((t) => !looksLikeChordSymbol(t));
      if (bad.length) {
        setError(
          `Invalid chord(s): ${bad.slice(0, 6).join(", ")}. Use symbols like C, Am, G7, Dm7.`,
        );
        return;
      }
      safeBarsPerChord = Number(barsPerChord);
      if (!Number.isFinite(safeBarsPerChord) || safeBarsPerChord <= 0) {
        setError("Bars per chord must be greater than 0");
        return;
      }
      safeBarsPerChord = Math.min(16, Math.max(0.0625, safeBarsPerChord));
      const totalBars = chordParts.length * safeBarsPerChord;
      if (totalBars > BARS_MAX_API) {
        setError(
          `Chord progression spans ${totalBars.toFixed(2)} bars ` +
            `(${chordParts.length} × ${safeBarsPerChord}); maximum is ${BARS_MAX_API}`,
        );
        return;
      }
    } else if (mode === "notes") {
      notes = notesText
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean);
      if (notes.length === 0) {
        setError("Enter at least one note line (or @track / [Section] block)");
        return;
      }
        const hasNoteToken = notes.some((line) => {
          const lower = line.toLowerCase();
          if (lower.startsWith("@track") || lower.startsWith("#track")) return false;
          if (lower.startsWith("[")) return false;
          if (lower === "r" || lower.startsWith("rest") || lower.startsWith("r "))
            return false;
          if (lower.startsWith("#")) return false;
          return true;
        });
      if (!hasNoteToken) {
        setError("Note list has no playable notes — add lines like: C4 q");
        return;
      }
    }

    // Abort any previous in-flight request and cancel matching AI work.
    if (abortRef.current) {
      void cancelGenerationRequest(String(requestIdRef.current));
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;
    const requestId = ++requestIdRef.current;
    const clientRequestId = String(requestId);
    setLoading(true);
    const { signal } = controller;
    try {
      let result;
      if (mode === "text") {
        result = await generateFromText(
          {
            prompt: prompt.trim(),
            bpm: safeBpm,
            bars: safeBars,
            key,
            time_signature: safeTs,
            mood: safeMood,
            style: safeStyle,
            instrument: trackInstrument.melody,
            tracks,
            mix,
            timing,
            expression,
            file_type: fileType,
            filename: filename.trim() || defaultFilenameForMode("text"),
            seed,
            client_request_id: clientRequestId,
          },
          { signal },
        );
      } else if (mode === "chords") {
        result = await generateFromChords(
          {
            progression,
            bpm: safeBpm,
            bars_per_chord: safeBarsPerChord,
            key,
            time_signature: safeTs,
            instrument: trackInstrument.melody,
            add_chords: tracks.chords,
            add_melody: tracks.melody,
            add_bass: tracks.bass,
            add_drums: tracks.drums,
            mix,
            timing,
            expression,
            file_type: fileType,
            filename: filename.trim() || defaultFilenameForMode("chords"),
            seed,
          },
          { signal },
        );
      } else {
        result = await generateFromNotes(
          {
            notes,
            bpm: safeBpm,
            key,
            time_signature: safeTs,
            instrument: trackInstrument.melody,
            mix,
            timing,
            expression,
            file_type: fileType,
            filename: filename.trim() || defaultFilenameForMode("notes"),
            seed,
          },
          { signal },
        );
      }
      if (requestId !== requestIdRef.current) {
        URL.revokeObjectURL(result.url);
        return;
      }
      const quote =
        mode === "text"
          ? prompt.trim()
          : mode === "chords"
            ? progression.trim()
            : notesText
                .split("\n")
                .map((line) => line.trim())
                .filter(Boolean)
                .slice(0, 4)
                .join(" · ");
      const selectedBars =
        mode === "text"
          ? safeBars
          : mode === "chords"
            ? chordParts.length * safeBarsPerChord
            : estimateNotesBars(notesText, beatsPerBar);
      replaceMidiResult({
        ...result,
        mode,
        quote,
        selectedBpm: safeBpm,
        selectedKey: key,
        selectedTimeSig: `${safeTs.numerator}/${safeTs.denominator}`,
        selectedBars,
        style: mode === "text" ? safeStyle : undefined,
        mood: mode === "text" ? safeMood : undefined,
      });
      setSuccess(null);
      if (needsAi) setAiLoaded(true);
      window.requestAnimationFrame(() => {
        resultCardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      if (isAbortError(err)) {
        setError("Generation cancelled");
      } else {
        setError(err instanceof Error ? err.message : "Something went wrong");
      }
    } finally {
      if (requestId === requestIdRef.current) {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
        setLoading(false);
      }
    }
  }

  function cancelGeneration() {
    void cancelGenerationRequest(String(requestIdRef.current));
    abortRef.current?.abort();
  }

  function clearSolos() {
    setSolo({ melody: false, chords: false, bass: false, drums: false });
  }

  function applyTextHappyPiano() {
    lockPresetFields();
    setPrompt("Create a happy piano melody in C Major, 120 BPM, 8 bars.");
    setBpm(120);
    setBars(8);
    setKey("C Major");
    setMood("Happy");
    setStyle("Pop");
    setTrackInstrument((t) => ({
      ...t,
      melody: "acoustic_grand_piano",
    }));
    setTracks({
      melody: true,
      chords: true,
      bass: true,
      drums: false,
    });
    clearSolos();
    applyStockFilename("text_happy_piano.mid");
  }

  function applyTextSadViolin() {
    lockPresetFields();
    setPrompt(
      "Make a sad violin melody in A Minor, 90 BPM, 8 bars, cinematic mood.",
    );
    setBpm(90);
    setBars(8);
    setKey("A Minor");
    setMood("Sad");
    setStyle("Classical");
    setTrackInstrument((t) => ({
      ...t,
      melody: "violin",
      chords: "string_ensemble_1",
    }));
    setTracks({
      melody: true,
      chords: true,
      bass: false,
      drums: false,
    });
    clearSolos();
    applyStockFilename("text_sad_violin.mid");
  }

  function applyTextLofiTags() {
    lockPresetFields();
    setPrompt("lo-fi hip hop, 80 BPM, dusty electric piano, 16 bars");
    setBpm(80);
    setBars(16);
    setKey("F Major");
    setMood("Calm");
    setStyle("Lo-Fi");
    setTrackInstrument((t) => ({
      ...t,
      melody: "electric_piano_1",
      chords: "electric_piano_1",
    }));
    setTracks({
      melody: true,
      chords: true,
      bass: true,
      drums: true,
    });
    clearSolos();
    applyStockFilename("text_output.mid");
  }

  function applyTextEdmStructured() {
    lockPresetFields();
    setPrompt(
      "Genre: EDM. Key: F Minor. 16 bars at 128 BPM. Big drop, then breakdown.",
    );
    setBpm(128);
    setBars(16);
    setKey("F Minor");
    setMood("Energetic");
    setStyle("EDM");
    setTrackInstrument((t) => ({
      ...t,
      melody: "lead_1_square",
      chords: "string_ensemble_1",
      bass: "electric_bass_finger",
    }));
    setTracks({
      melody: true,
      chords: true,
      bass: true,
      drums: true,
    });
    clearSolos();
    applyStockFilename("text_output.mid");
  }

  function applyChordsPipe() {
    setProgression("C | G | Am | F");
    setBpm(120);
    setKey("C Major");
    setBarsPerChord(1);
    setTracks({
      melody: true,
      chords: true,
      bass: true,
      drums: true,
    });
    clearSolos();
    applyStockFilename("chords_progression.mid");
  }

  function applyChordsDash() {
    setProgression("Am - F - C - G");
    setBpm(100);
    setKey("A Minor");
    setBarsPerChord(1);
    setTracks({
      melody: true,
      chords: true,
      bass: true,
      drums: false,
    });
    clearSolos();
    applyStockFilename("chords_progression.mid");
  }

  function applyChordsArrow() {
    setProgression("D -> A -> Bm -> G");
    setBpm(118);
    setKey("D Major");
    setBarsPerChord(2);
    setTracks({
      melody: true,
      chords: true,
      bass: true,
      drums: false,
    });
    clearSolos();
    applyStockFilename("chords_progression.mid");
  }

  function applyChordsJazz() {
    setProgression("Cmaj7, Am7, Dm7, G7");
    setBpm(92);
    setKey("C Major");
    setBarsPerChord(1);
    setTracks({
      melody: true,
      chords: true,
      bass: true,
      drums: false,
    });
    clearSolos();
    applyStockFilename("chords_progression.mid");
  }

  function applyNotesMelody() {
    setBpm(120);
    setKey("C Major");
    setNotesText(
      ["C4 q", "E4 q", "G4 h", "rest q", "C5 q", "B4 q", "A4 h"].join("\n"),
    );
    setQuantize("");
    setHumanize(false);
    setTrackInstrument((t) => ({
      ...t,
      melody: "acoustic_grand_piano",
    }));
    clearSolos();
    applyStockFilename("notes_list.mid");
  }

  function applyNotesChordTones() {
    setBpm(96);
    setKey("C Major");
    setNotesText(
      ["C4 E4 G4 q", "F4 A4 C5 q", "G3 B3 D4 q", "C4 E4 G4 h"].join("\n"),
    );
    setQuantize("");
    setHumanize(false);
    setTrackInstrument((t) => ({
      ...t,
      melody: "electric_piano_1",
    }));
    clearSolos();
    applyStockFilename("notes_list.mid");
  }

  function applyNotesVelocity() {
    setBpm(110);
    setKey("A Minor");
    setNotesText(
      [
        "A3 q 70",
        "C4 e 90",
        "E4 e 110",
        "rest q",
        "A4 h 80",
      ].join("\n"),
    );
    setQuantize("");
    setHumanize(false);
    setTrackInstrument((t) => ({
      ...t,
      melody: "violin",
    }));
    clearSolos();
    applyStockFilename("notes_list.mid");
  }

  function applyNotesMultiTrack() {
    setBpm(100);
    setKey("C Major");
    setNotesText(
      [
        "@track Chords electric_piano_1",
        "C4 E4 G4 q",
        "F4 A4 C5 q",
        "@track Melody flute",
        "G5 e",
        "A5 e",
        "G5 q",
        "@track Bass acoustic_bass",
        "C2 q",
        "F2 q",
      ].join("\n"),
    );
    setQuantize("");
    setHumanize(false);
    clearSolos();
    applyStockFilename("notes_list.mid");
  }

  const anySolo = TRACK_META.some(({ id }) => {
    const included =
      mode === "notes" ? notesTrackRoles.has(id) : tracks[id];
    return included && solo[id];
  });

  return (
    <main className="studio-shell mx-auto min-h-screen max-w-7xl px-4 pb-28 pt-6 sm:px-6 lg:px-8">
      <div className="studio-ambient" aria-hidden>
        <span className="orb orb-a" />
        <span className="orb orb-b" />
        <span className="orb orb-c" />
      </div>
      {/* Top bar */}
      <header className="animate-rise mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-[var(--signal)]">
              DAW-ready · Standard MIDI
            </p>
            <h1 className="brand text-4xl leading-none sm:text-5xl">
              MIDIgen
            </h1>
          </div>
          <div className="hidden h-10 w-px bg-[var(--line)] sm:block" />
          <p className="hidden max-w-sm text-sm text-[var(--muted)] md:block">
            Pro studio for text, chords, and note lists → clean multi-track{" "}
            <strong className="text-[var(--ink)]">.mid</strong>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`status-chip ${
              apiOk
                ? "status-chip-ok"
                : apiOk === false
                  ? "status-chip-bad"
                  : ""
            }`}
          >
            <span
              className="status-dot"
              style={{
                background: apiOk
                  ? "var(--ok)"
                  : apiOk === false
                    ? "var(--danger)"
                    : "var(--muted)",
              }}
            />
            {apiOk === null && "Checking API"}
            {apiOk === true && `API v${apiVersion || "0.1"}`}
            {apiOk === false && `API offline · ${apiDisplayBase}`}
          </span>
          <span
            className={`status-chip ${
              aiConfigured && aiLoaded
                ? "status-chip-ok"
                : aiConfigured && aiOnline !== false
                  ? "status-chip-warn"
                  : ""
            }`}
          >
            {aiConfigured === null && "Checking model"}
            {aiConfigured === false && "Local model missing"}
            {aiConfigured === true &&
              aiOnline === false &&
              `Local offline · ${aiModel || "file"}`}
            {aiConfigured === true &&
              aiOnline !== false &&
              aiLoaded &&
              `${aiProvider === "local" ? "Local" : aiProvider} · ${aiModel || "loaded"}`}
            {aiConfigured === true &&
              aiOnline !== false &&
              aiLoaded === false &&
              `Local idle · ${aiModel || "file"} (loads on generate)`}
            {aiConfigured === true &&
              aiOnline !== false &&
              aiLoaded === null &&
              `Local · ${aiModel || "checking"}`}
          </span>
        </div>
      </header>

      {midiResult ? (
        <div ref={resultCardRef} className="mb-8 mt-2">
          <MidiResultCard
            result={midiResult}
            onCreateAnother={() => {
              replaceMidiResult(null);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        </div>
      ) : (
      <div className="animate-rise-delay">
        <form onSubmit={onSubmit} className="studio-form space-y-5">
          {/* Mode + input */}
          <section className="section-card p-5 sm:p-6">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-bold uppercase tracking-[0.14em] text-[var(--muted)]">
                01 · Compose
              </h2>
              <div
                className="flex rounded-xl bg-[var(--glow)] p-1"
                role="radiogroup"
                aria-label="Generation mode"
              >
                {(
                  [
                    ["text", "Text"],
                    ["chords", "Chords"],
                    ["notes", "Notes"],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    role="radio"
                    aria-checked={mode === id}
                    onClick={() => setModeAndMaybeFilename(id)}
                    className={`mode-tab rounded-lg px-4 py-2 text-sm font-semibold transition ${
                      mode === id
                        ? "bg-[var(--accent)] text-white shadow-sm"
                        : "text-[var(--muted)] hover:text-[var(--ink)]"
                    }`}
                  >
                    <TypeIcon kind="mode" name={id} />
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {mode === "text" && (
              <div className="mode-swap">
                <label className="block">
                  <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">
                    Prompt — mood · instrument · key · BPM · bars
                  </span>
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    rows={3}
                    maxLength={8000}
                    className="field-input resize-y"
                    placeholder="Make a sad violin melody in A Minor, 90 BPM, 8 bars, cinematic mood."
                    required
                  />
                </label>
                <div className="preset-examples">
                  <p className="preset-examples-label">Text examples</p>
                  <div className="preset-examples-grid">
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyTextHappyPiano}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="mood" name="Happy" />
                        Sentence prompt
                      </span>
                      <span className="mt-1 block text-xs text-[var(--muted)]">
                        “Create a happy piano melody in C Major…”
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyTextSadViolin}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="mood" name="Sad" />
                        Mood + instrument
                      </span>
                      <span className="mt-1 block text-xs text-[var(--muted)]">
                        Sad violin · A Minor · cinematic
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyTextLofiTags}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="style" name="Lo-Fi" />
                        Short tags
                      </span>
                      <span className="mt-1 block text-xs text-[var(--muted)]">
                        lo-fi hip hop, 80 BPM, dusty piano
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyTextEdmStructured}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="style" name="EDM" />
                        Structured fields
                      </span>
                      <span className="mt-1 block text-xs text-[var(--muted)]">
                        Genre: EDM. Key: F Minor. 16 bars.
                      </span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {mode === "chords" && (
              <div className="mode-swap">
                <label className="block">
                  <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">
                    Progression
                  </span>
                  <input
                    value={progression}
                    onChange={(e) => setProgression(e.target.value)}
                    className="field-input text-lg tracking-wide"
                    placeholder="C | G | Am | F"
                    required
                  />
                </label>
                <div className="preset-examples">
                  <p className="preset-examples-label">Chord examples</p>
                  <div className="preset-examples-grid">
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyChordsPipe}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="mode" name="chords" />
                        Pipe bars
                      </span>
                      <span className="mt-1 block font-mono text-xs text-[var(--muted)]">
                        C | G | Am | F
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyChordsDash}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="mode" name="chords" />
                        Dashes
                      </span>
                      <span className="mt-1 block font-mono text-xs text-[var(--muted)]">
                        Am - F - C - G
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyChordsArrow}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="mode" name="chords" />
                        Arrows
                      </span>
                      <span className="mt-1 block font-mono text-xs text-[var(--muted)]">
                        D -&gt; A -&gt; Bm -&gt; G
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyChordsJazz}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="style" name="Jazz" />
                        Comma jazz
                      </span>
                      <span className="mt-1 block font-mono text-xs text-[var(--muted)]">
                        Cmaj7, Am7, Dm7, G7
                      </span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {mode === "notes" && (
              <div className="mode-swap">
                <label className="block">
                  <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">
                    Sheet Music / Note Data Input
                  </span>
                  <textarea
                    value={notesText}
                    onChange={(e) => setNotesText(e.target.value)}
                    rows={8}
                    className="field-input resize-y font-mono text-sm"
                    placeholder={"C4 q\nE4 q\nG4 h\nrest q\nC5 q\nB4 q\nA4 h"}
                    required
                  />
                </label>
                <div className="preset-examples">
                  <p className="preset-examples-label">Notes examples</p>
                  <div className="preset-examples-grid">
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyNotesMelody}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="mode" name="notes" />
                        One note / line
                      </span>
                      <span className="mt-1 block font-mono text-xs text-[var(--muted)]">
                        C4 q · E4 q · G4 h · rest q
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyNotesChordTones}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="mode" name="notes" />
                        Same-beat chord
                      </span>
                      <span className="mt-1 block font-mono text-xs text-[var(--muted)]">
                        C4 E4 G4 q
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyNotesVelocity}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="mode" name="notes" />
                        Velocity + rest
                      </span>
                      <span className="mt-1 block font-mono text-xs text-[var(--muted)]">
                        A3 q 70 · C4 e 90 · rest q
                      </span>
                    </button>
                    <button
                      type="button"
                      className="btn-ghost rounded-xl px-3 py-3 text-left"
                      onClick={applyNotesMultiTrack}
                    >
                      <span className="flex items-center gap-2 text-sm font-bold text-[var(--ink)]">
                        <TypeIcon kind="mode" name="notes" />
                        @track multi
                      </span>
                      <span className="mt-1 block font-mono text-xs text-[var(--muted)]">
                        @track Chords · Melody · Bass
                      </span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="BPM" hint={`${BPM_MIN}–${BPM_MAX} · ${durationSec}s est.`}>
                <input
                  type="number"
                  min={BPM_MIN}
                  max={BPM_MAX}
                  step={1}
                  value={bpm}
                  onChange={(e) => {
                    markTouched("bpm");
                    setBpm(Number(e.target.value));
                  }}
                  onBlur={() => setBpm((v) => clampBpm(v))}
                  className="field-input"
                />
              </Field>
              {mode === "text" && (
                <Field label="Bars" hint={`${BARS_MIN}–${BARS_MAX}`}>
                  <input
                    type="number"
                    min={BARS_MIN}
                    max={BARS_MAX}
                    step={1}
                    value={bars}
                    onChange={(e) => {
                      markTouched("bars");
                      setBars(Number(e.target.value));
                    }}
                    onBlur={() => setBars((v) => clampBars(v))}
                    className="field-input"
                  />
                </Field>
              )}
              {mode === "chords" && (
                <Field label="Bars / chord" hint="1–16">
                  <input
                    type="number"
                    min={0.0625}
                    max={16}
                    step={0.0625}
                    value={barsPerChord}
                    onChange={(e) => setBarsPerChord(Number(e.target.value))}
                    onBlur={() =>
                      setBarsPerChord((v) => {
                        if (!Number.isFinite(v) || v <= 0) return 1;
                        return Math.min(16, Math.max(0.0625, v));
                      })
                    }
                    className="field-input"
                  />
                </Field>
              )}
              <Field
                label="Seed"
                hint={
                  mode === "text"
                    ? "Reproducible AI"
                    : "Humanize RNG (optional)"
                }
              >
                <div className="flex gap-2">
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={seed}
                    onChange={(e) => setSeed(Number(e.target.value) || 0)}
                    className="field-input"
                  />
                  <button
                    type="button"
                    title="New random seed"
                    onClick={() => setSeed(Math.floor(Math.random() * 100000))}
                    className="btn-ghost rounded-lg px-2 text-xs font-semibold"
                  >
                    Rnd
                  </button>
                </div>
              </Field>
              <Field label="Key">
                <select
                  value={key}
                  onChange={(e) => {
                    markTouched("key");
                    setKey(e.target.value);
                  }}
                  className="field-input"
                >
                  {keyOptions.map((k) => (
                    <option key={k}>{k}</option>
                  ))}
                </select>
              </Field>
              <Field
                label="Time sig"
                hint={`${TS_NUMERATOR_MIN}–${TS_NUMERATOR_MAX} / power of 2`}
              >
                <div className="flex items-center gap-2">
                  <select
                    value={tsNumerator}
                    onChange={(e) => {
                      markTouched("time_signature");
                      setTsNumerator(Number(e.target.value));
                    }}
                    className="field-input"
                    aria-label="Time signature numerator"
                  >
                    {Array.from(
                      { length: TS_NUMERATOR_MAX - TS_NUMERATOR_MIN + 1 },
                      (_, i) => TS_NUMERATOR_MIN + i,
                    ).map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                  <span className="text-[var(--muted)]">/</span>
                  <select
                    value={tsDenominator}
                    onChange={(e) => {
                      markTouched("time_signature");
                      setTsDenominator(Number(e.target.value) as TsDenominator);
                    }}
                    className="field-input"
                    aria-label="Time signature denominator"
                  >
                    {TS_DENOMINATORS.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                </div>
              </Field>
              {mode === "text" && (
                <>
                  <Field label="Mood">
                    <IconSelect
                      kind="mood"
                      value={mood}
                      options={moodOptions}
                      ariaLabel="Mood"
                      onChange={(next) => {
                        markTouched("mood");
                        setMood(next);
                      }}
                    />
                  </Field>
                  <Field label="Style">
                    <IconSelect
                      kind="style"
                      value={style}
                      options={styleOptions}
                      ariaLabel="Style"
                      onChange={(next) => {
                        markTouched("style");
                        setStyle(next);
                      }}
                    />
                  </Field>
                </>
              )}
              <Field label="MIDI type">
                <IconSelect
                  kind="midiType"
                  value={String(fileType)}
                  options={["1", "0"]}
                  ariaLabel="MIDI type"
                  getLabel={(v) =>
                    v === "0" ? "Type 0 · single track" : "Type 1 · multi-track"
                  }
                  onChange={(next) => setFileType(Number(next) as 0 | 1)}
                />
              </Field>
              <Field label="Filename">
                <input
                  value={filename}
                  onChange={(e) => {
                    filenameCustomRef.current = true;
                    setFilename(e.target.value);
                  }}
                  placeholder={defaultFilenameForMode(mode)}
                  className="field-input"
                />
              </Field>
            </div>
            {mode === "text" && (
              <p className="mt-3 text-xs text-[var(--muted)]">
                Prompt auto-fills BPM, bars, key, mood, style, and tracks. After you
                change a field, that value wins — prompt will not overwrite it.
              </p>
            )}
          </section>

          {/* Mixer */}
          <section className="section-card p-5 sm:p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-bold uppercase tracking-[0.14em] text-[var(--muted)]">
                  02 · Track mixer
                </h2>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Enable roles · set instrument / channel · volume & pan
                </p>
              </div>
              {anySolo && (
                <button
                  type="button"
                  onClick={clearSolos}
                  className="rounded-lg border border-[var(--warn)] bg-[rgba(251,191,36,0.12)] px-3 py-1.5 text-xs font-bold text-[var(--warn)]"
                >
                  Clear solos ({activeTrackCount} exporting)
                </button>
              )}
            </div>

            <div className="mb-4 flex flex-wrap gap-2">
              {TRACK_META.map(({ id, label, color }) => {
                const on =
                  mode === "notes" ? notesTrackRoles.has(id) : tracks[id];
                const disabled = mode === "notes";
                return (
                  <button
                    key={id}
                    type="button"
                    disabled={disabled}
                    onClick={() => {
                      if (id === "chords") markTouched("tracks_chords");
                      if (id === "bass") markTouched("tracks_bass");
                      if (id === "drums") markTouched("tracks_drums");
                      setTracks((t) => {
                        const nextOn = !t[id];
                        if (!nextOn) {
                          // Keep UI/backend solo logic aligned when a role is disabled
                          setMute((m) => ({ ...m, [id]: false }));
                          setSolo((s) => ({ ...s, [id]: false }));
                        }
                        return { ...t, [id]: nextOn };
                      });
                    }}
                    className={`track-pill rounded-full px-3.5 py-1.5 text-sm font-semibold transition disabled:cursor-default ${
                      on
                        ? "text-white"
                        : "bg-[var(--field)] text-[var(--muted)] ring-1 ring-[var(--line)]"
                    }`}
                    style={on ? { background: color } : undefined}
                    title={
                      mode === "notes"
                        ? "Controlled by @track / [Name] lines in the notes input"
                        : undefined
                    }
                  >
                    <TypeIcon kind="track" name={id} />
                    {label}
                  </button>
                );
              })}
            </div>

            <div className="overflow-x-auto rounded-xl border border-[var(--line)]">
              <table className="mixer-table w-full min-w-[720px] border-collapse text-sm">
                <thead>
                  <tr className="bg-[var(--glow)] text-left text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--muted)]">
                    <th className="px-3 py-2.5">Track</th>
                    <th className="px-3 py-2.5">Instrument</th>
                    <th className="px-3 py-2.5">Ch</th>
                    <th className="px-3 py-2.5">M / S</th>
                    <th className="px-3 py-2.5">Vol</th>
                    <th className="px-3 py-2.5">Pan</th>
                  </tr>
                </thead>
                <tbody>
                  {TRACK_META.map(({ id, label, color }) => {
                    const notesInactive =
                      mode === "notes" && !notesTrackRoles.has(id);
                    const inactive =
                      notesInactive || (mode !== "notes" && !tracks[id]);
                    return (
                      <tr
                        key={id}
                        className={`border-t border-[var(--line)] bg-[var(--field)]/60 ${
                          inactive ? "opacity-45" : ""
                        }`}
                      >
                        <td className="px-3 py-3">
                          <div className="flex items-center gap-2 font-semibold">
                            <span
                              className="h-2.5 w-2.5 rounded-full"
                              style={{ background: color }}
                            />
                            <TypeIcon kind="track" name={id} />
                            {label}
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <IconSelect
                            kind="instrument"
                            value={trackInstrument[id]}
                            disabled={inactive}
                            ariaLabel={`${label} instrument`}
                            getLabel={labelize}
                            options={
                              id === "drums"
                                ? instrumentOptions
                                : instrumentOptions.filter((opt) => !isDrumInstrument(opt))
                            }
                            onChange={(next) => {
                              if (id === "melody") markTouched("instrument");
                              setTrackInstrument((p) => ({
                                ...p,
                                [id]: next,
                              }));
                            }}
                          />
                        </td>
                        <td className="px-3 py-2">
                          <select
                            value={
                              trackChannel[id] === null ||
                              (id !== "drums" && trackChannel[id] === 9)
                                ? ""
                                : String(trackChannel[id])
                            }
                            disabled={inactive}
                            onChange={(e) => {
                              const raw = e.target.value;
                              let next: number | null =
                                raw === "" ? null : Number(raw);
                              if (id !== "drums" && next === 9) next = null;
                              setTrackChannel((p) => ({
                                ...p,
                                [id]: next,
                              }));
                            }}
                            className="field-input py-1.5 text-sm"
                          >
                            <option value="">Auto</option>
                            {Array.from({ length: 16 }, (_, i) => {
                              // Melodic roles cannot use GM drum channel 10 (index 9)
                              if (id !== "drums" && i === 9) return null;
                              return (
                                <option key={i} value={i}>
                                  {i + 1}
                                  {i === 9 ? " D" : ""}
                                </option>
                              );
                            })}
                          </select>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex gap-2">
                            <label className="flex items-center gap-1 text-xs font-semibold">
                              <input
                                type="checkbox"
                                checked={mute[id]}
                                disabled={inactive}
                                aria-label={`Mute ${label}`}
                                onChange={(e) =>
                                  setMute((m) => ({
                                    ...m,
                                    [id]: e.target.checked,
                                  }))
                                }
                              />
                              M
                            </label>
                            <label className="flex items-center gap-1 text-xs font-semibold">
                              <input
                                type="checkbox"
                                checked={solo[id]}
                                disabled={inactive}
                                aria-label={`Solo ${label}`}
                                onChange={(e) =>
                                  setSolo((s) => ({
                                    ...s,
                                    [id]: e.target.checked,
                                  }))
                                }
                              />
                              S
                            </label>
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            <input
                              type="range"
                              min={0}
                              max={127}
                              value={volume[id]}
                              disabled={inactive}
                              onChange={(e) =>
                                setVolume((v) => ({
                                  ...v,
                                  [id]: Number(e.target.value),
                                }))
                              }
                              className="mixer-range"
                            />
                            <span className="w-8 text-right text-xs tabular-nums text-[var(--muted)]">
                              {volume[id]}
                            </span>
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            <input
                              type="range"
                              min={0}
                              max={127}
                              value={pan[id]}
                              disabled={inactive}
                              onChange={(e) =>
                                setPan((p) => ({
                                  ...p,
                                  [id]: Number(e.target.value),
                                }))
                              }
                              className="mixer-range"
                            />
                            <span className="w-8 text-right text-xs tabular-nums text-[var(--muted)]">
                              {pan[id]}
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* Timing + expression */}
          <section className="section-card p-5 sm:p-6">
            <h2 className="mb-4 text-sm font-bold uppercase tracking-[0.14em] text-[var(--muted)]">
              03 · Timing & expression
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="PPQ">
                <select
                  value={ppq}
                  onChange={(e) => setPpq(Number(e.target.value))}
                  className="field-input"
                >
                  {ppqOptions.map((value) => (
                    <option key={value} value={value}>
                      {value === 480 ? "480 default" : value}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Quantize">
                <select
                  value={quantize}
                  onChange={(e) => setQuantize(e.target.value)}
                  className="field-input"
                >
                  <option value="">Off</option>
                  {quantizeOptions.map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Swing grid">
                <select
                  value={swingGrid}
                  onChange={(e) => setSwingGrid(e.target.value)}
                  className="field-input"
                >
                  {swingGridOptions.map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </select>
              </Field>
              <Field
                label={`Swing ${swingMpc}%${
                  swingMpc <= 50
                    ? " · straight"
                    : swingMpc >= 65 && swingMpc <= 68
                      ? " · triplet"
                      : ""
                }`}
              >
                <input
                  type="range"
                  min={50}
                  max={75}
                  step={1}
                  value={swingMpc}
                  onChange={(e) => setSwingMpc(Number(e.target.value))}
                  className="mixer-range mt-3"
                  title="MPC-style: 50 = straight, ~66 = triplet"
                />
              </Field>
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
              <label className="flex items-center gap-2 text-sm font-semibold text-[var(--muted)]">
                <input
                  type="checkbox"
                  checked={quantizeDuration}
                  onChange={(e) => setQuantizeDuration(e.target.checked)}
                  disabled={!quantize}
                />
                Quantize durations
              </label>
              <label className="flex items-center gap-2 text-sm font-semibold text-[var(--muted)]">
                <input
                  type="checkbox"
                  checked={humanize}
                  onChange={(e) => setHumanize(e.target.checked)}
                />
                Humanize
              </label>
              <label className="flex items-center gap-2 text-sm font-semibold text-[var(--muted)]">
                <input
                  type="checkbox"
                  checked={humanizeControllers}
                  onChange={(e) => setHumanizeControllers(e.target.checked)}
                  disabled={!humanize}
                />
                Humanize CC / pitch bend
              </label>
            </div>

            {humanize && (
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <Field label={`Timing ±${humanizeTiming.toFixed(3)} beats`}>
                  <input
                    type="range"
                    min={0}
                    max={0.25}
                    step={0.005}
                    value={humanizeTiming}
                    onChange={(e) => setHumanizeTiming(Number(e.target.value))}
                    className="mixer-range mt-3"
                  />
                </Field>
                <Field label={`Velocity ±${humanizeVelocity}`}>
                  <input
                    type="range"
                    min={0}
                    max={64}
                    step={1}
                    value={humanizeVelocity}
                    onChange={(e) => setHumanizeVelocity(Number(e.target.value))}
                    className="mixer-range mt-3"
                  />
                </Field>
                <Field label={`Duration ±${humanizeDuration.toFixed(3)}`}>
                  <input
                    type="range"
                    min={0}
                    max={0.25}
                    step={0.005}
                    value={humanizeDuration}
                    onChange={(e) => setHumanizeDuration(Number(e.target.value))}
                    className="mixer-range mt-3"
                  />
                </Field>
              </div>
            )}

            <div className="mt-5 flex flex-wrap items-center gap-2">
              {(
                [
                  ["sustain", sustain, setSustain, "Sustain CC64"],
                  ["mod", modulation, setModulation, "Modulation CC1"],
                  ["pb", pitchBend, setPitchBend, "Pitch bend"],
                ] as const
              ).map(([keyId, value, setter, label]) => (
                <button
                  key={keyId}
                  type="button"
                  onClick={() => setter(!value)}
                  className={`rounded-full px-3.5 py-1.5 text-xs font-bold transition ${
                    value
                      ? "bg-[var(--signal-soft)] text-[var(--accent-deep)]"
                      : "bg-[var(--field)] text-[var(--muted)] ring-1 ring-[var(--line)]"
                  }`}
                >
                  {label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setExprAdvancedOpen((o) => !o)}
                className="rounded-full px-3.5 py-1.5 text-xs font-bold text-[var(--muted)] ring-1 ring-[var(--line)] transition hover:text-[var(--ink)]"
              >
                {exprAdvancedOpen ? "Hide advanced" : "Advanced expression"}
              </button>
            </div>

            {exprAdvancedOpen && (
              <div className="mt-4 space-y-4 rounded-xl border border-[var(--line)] bg-[var(--glow)]/40 p-4">
                <p className="text-xs text-[var(--muted)]">
                  Customize automation written into the .mid. Defaults match the
                  previous fixed behaviour. Toggles above still enable/disable
                  each feature.
                </p>

                <div
                  className={`grid gap-4 sm:grid-cols-3 ${sustain ? "" : "opacity-45"}`}
                >
                  <Field label={`Sustain on ${sustainOnValue}`} hint="CC64">
                    <input
                      type="range"
                      min={0}
                      max={127}
                      value={sustainOnValue}
                      disabled={!sustain}
                      onChange={(e) => setSustainOnValue(Number(e.target.value))}
                      className="mixer-range mt-3"
                    />
                  </Field>
                  <Field label={`Sustain off ${sustainOffValue}`} hint="CC64">
                    <input
                      type="range"
                      min={0}
                      max={127}
                      value={sustainOffValue}
                      disabled={!sustain}
                      onChange={(e) =>
                        setSustainOffValue(Number(e.target.value))
                      }
                      className="mixer-range mt-3"
                    />
                  </Field>
                  <Field
                    label={`Hold ${(sustainHoldRatio * 100).toFixed(0)}% of bar`}
                  >
                    <input
                      type="range"
                      min={0.05}
                      max={1}
                      step={0.01}
                      value={sustainHoldRatio}
                      disabled={!sustain}
                      onChange={(e) =>
                        setSustainHoldRatio(Number(e.target.value))
                      }
                      className="mixer-range mt-3"
                    />
                  </Field>
                </div>

                <div
                  className={`grid gap-4 sm:grid-cols-3 ${modulation ? "" : "opacity-45"}`}
                >
                  <Field label={`Mod intensity ${modulationValue}`} hint="CC1">
                    <input
                      type="range"
                      min={0}
                      max={127}
                      value={modulationValue}
                      disabled={!modulation}
                      onChange={(e) =>
                        setModulationValue(Number(e.target.value))
                      }
                      className="mixer-range mt-3"
                    />
                  </Field>
                  <Field label={`Every ${modulationIntervalBars} bars`}>
                    <input
                      type="range"
                      min={0.25}
                      max={32}
                      step={0.25}
                      value={modulationIntervalBars}
                      disabled={!modulation}
                      onChange={(e) =>
                        setModulationIntervalBars(Number(e.target.value))
                      }
                      className="mixer-range mt-3"
                    />
                  </Field>
                  <Field
                    label={`Accent ${(modulationAccentRatio * 100).toFixed(0)}% bar`}
                  >
                    <input
                      type="range"
                      min={0.05}
                      max={4}
                      step={0.05}
                      value={modulationAccentRatio}
                      disabled={!modulation}
                      onChange={(e) =>
                        setModulationAccentRatio(Number(e.target.value))
                      }
                      className="mixer-range mt-3"
                    />
                  </Field>
                </div>

                <div
                  className={`grid gap-4 sm:grid-cols-3 ${pitchBend ? "" : "opacity-45"}`}
                >
                  <Field label={`Scoop depth ${pitchBendScoopDepth}`} hint="PB">
                    <input
                      type="range"
                      min={0}
                      max={8191}
                      step={25}
                      value={pitchBendScoopDepth}
                      disabled={!pitchBend}
                      onChange={(e) =>
                        setPitchBendScoopDepth(Number(e.target.value))
                      }
                      className="mixer-range mt-3"
                    />
                  </Field>
                  <Field label={`Every ${pitchBendIntervalBars} bars`}>
                    <input
                      type="range"
                      min={0.25}
                      max={32}
                      step={0.25}
                      value={pitchBendIntervalBars}
                      disabled={!pitchBend}
                      onChange={(e) =>
                        setPitchBendIntervalBars(Number(e.target.value))
                      }
                      className="mixer-range mt-3"
                    />
                  </Field>
                  <Field
                    label={`Scoop ${pitchBendScoopBeats.toFixed(2)} beats`}
                  >
                    <input
                      type="range"
                      min={0.05}
                      max={4}
                      step={0.05}
                      value={pitchBendScoopBeats}
                      disabled={!pitchBend}
                      onChange={(e) =>
                        setPitchBendScoopBeats(Number(e.target.value))
                      }
                      className="mixer-range mt-3"
                    />
                  </Field>
                </div>
              </div>
            )}
          </section>

          {error && (
            <p
              role="alert"
              aria-live="assertive"
              className="anim-alert rounded-xl border border-[rgba(248,113,113,0.4)] bg-[rgba(248,113,113,0.1)] px-4 py-3 text-sm text-[var(--danger)]"
            >
              {error}
            </p>
          )}
          {success && (
            <p
              role="status"
              aria-live="polite"
              className="anim-alert rounded-xl border border-[rgba(52,211,153,0.35)] bg-[rgba(52,211,153,0.1)] px-4 py-3 text-sm text-[var(--ok)]"
            >
              {success}
            </p>
          )}

          {/* Sticky-ish generate */}
          <div className="generate-dock section-card sticky bottom-4 z-10 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
            <div className="text-sm text-[var(--muted)]">
              <span className="font-bold text-[var(--ink)]">
                {filename.trim() || defaultFilenameForMode(mode)}
              </span>
              <span className="mx-2">·</span>
              {bpm} BPM · ~{durationSec}s · Type {fileType} · {activeTrackCount} tracks
              {loading && needsAi && (
                <span className="mt-1 block text-xs text-[var(--muted)]">
                  Local model can take several minutes on CPU — you can cancel anytime.
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {loading && (
                <button
                  type="button"
                  onClick={cancelGeneration}
                  className="btn-ghost inline-flex min-h-12 min-w-[120px] items-center justify-center rounded-xl px-5 text-base font-bold"
                >
                  Cancel
                </button>
              )}
              <button
                type="submit"
                disabled={generateBlocked}
                className={`generate-btn inline-flex min-h-12 min-w-[220px] items-center justify-center rounded-xl px-6 text-base font-bold disabled:cursor-not-allowed disabled:opacity-50${
                  loading ? " is-loading" : ""
                }`}
              >
                {loading ? (
                  <span className="animate-pulse-soft">Generating MIDI…</span>
                ) : activeTrackCount === 0 ? (
                  "Enable a track to generate"
                ) : !promptReady ? (
                  "Enter a prompt"
                ) : !aiReady ? (
                  aiConfigured === false
                    ? "Model missing"
                    : "Checking local model…"
                ) : apiOk === false ? (
                  "API offline"
                ) : (
                  "Generate MIDI"
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
      )}
    </main>
  );
}
