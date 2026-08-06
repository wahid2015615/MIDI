"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
  fetchHealth,
  fetchMeta,
  generateFromChords,
  generateFromNotes,
  generateFromText,
  isAbortError,
  parseTextPrompt,
} from "../api/studioApi";
import {
  BARS_DEFAULT,
  BARS_MAX,
  BARS_MIN,
  BPM_MAX,
  BPM_MIN,
  clampBars,
  clampBpm,
  canonicalTrackRole,
  DEFAULT_INSTRUMENTS,
  DEFAULT_MOOD,
  DEFAULT_STYLE,
  DEFAULT_TIME_SIGNATURE,
  isValidBars,
  isValidMood,
  isValidStyle,
  isValidTimeSignature,
  KEYS,
  labelize,
  MOODS,
  normalizeBars,
  normalizeMood,
  normalizeStyle,
  normalizeTimeSignature,
  STYLES,
  TS_DENOMINATORS,
  TS_NUMERATOR_MAX,
  TS_NUMERATOR_MIN,
  type Mood,
  type Style,
  type TsDenominator,
} from "../constants";
import type { Mode, TrackRole } from "../types";
import { Field } from "../../../shared/ui/Field";

/** Mirror backend `parse_progression_string` separators. */
function splitChordProgression(text: string): string[] {
  const normalized = text.replaceAll("→", "-").replaceAll("->", "-");
  let parts: string[];
  if (normalized.includes("|")) {
    parts = normalized.split("|");
  } else if (normalized.includes("-") || normalized.includes("–")) {
    parts = normalized.split(/[-–]/);
  } else if (normalized.includes(",")) {
    parts = normalized.split(",");
  } else {
    parts = normalized.split(/\s+/);
  }
  return parts.map((p) => p.trim().replace(/^[,|]+|[,|]+$/g, "").trim()).filter(Boolean);
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
  const [aiModel, setAiModel] = useState("");
  const [aiProvider, setAiProvider] = useState("local");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

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
  const [mood, setMood] = useState<Mood>(DEFAULT_MOOD);
  const [style, setStyle] = useState<Style>(DEFAULT_STYLE);
  const [fileType, setFileType] = useState<0 | 1>(1);
  const [filename, setFilename] = useState("uplifting_piano.mid");

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

  useEffect(() => {
    let alive = true;

    async function refreshHealth(probe: boolean) {
      try {
        const health = await fetchHealth({ probe });
        if (!alive) return;
        setApiOk(true);
        setApiVersion(health.version);
        setAiConfigured(Boolean(health.ai?.configured));
        setAiOnline(
          health.ai?.configured ? Boolean(health.ai?.online) : false,
        );
        setAiModel(health.ai?.model || "");
        setAiProvider(health.ai?.provider || "local");
      } catch {
        if (alive) {
          setApiOk(false);
          setAiOnline(false);
        }
      }
    }

    async function refreshMeta() {
      try {
        const meta = await fetchMeta();
        if (!alive) return;
        if (meta.instruments?.instruments?.length) {
          setInstrumentOptions(
            meta.instruments.instruments.map((i: { id: string }) => i.id),
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
      abortRef.current?.abort();
    };
  }, []);

  // Prompt → form auto-fill. Only detected fields; skip anything the user edited.
  useEffect(() => {
    if (mode !== "text") return;
    const trimmed = prompt.trim();
    if (!trimmed) return;

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const parsed = await parseTextPrompt(trimmed);
        if (cancelled) return;
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
          try {
            setMood(normalizeMood(parsed.mood));
          } catch {
            /* ignore unknown mood from parse */
          }
        }
        if (d.style && isUntouched("style") && parsed.style) {
          try {
            setStyle(normalizeStyle(parsed.style));
          } catch {
            /* ignore unknown style from parse */
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
        console.warn("[studio] prompt auto-fill failed:", err);
      }
    }, 400);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [prompt, mode, isUntouched]);

  const notesTrackRoles = useMemo(() => {
    const roles = new Set<TrackRole>();
    const re =
      /^(?:@track|#track)\s+(\S+)|^\[\s*([A-Za-z]\w*)/i;
    for (const raw of notesText.split("\n")) {
      const m = re.exec(raw.trim());
      if (!m) continue;
      const name = m[1] || m[2] || "";
      const role = canonicalTrackRole(name);
      if (role) roles.add(role);
    }
    if (roles.size === 0) roles.add("melody");
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
  const aiReady = !needsAi || (aiConfigured === true && aiOnline === true);
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
            Math.max(0.25, barsPerChord),
        )
      : mode === "notes"
        ? Math.max(
            1,
            Math.ceil(
              notesText
                .split("\n")
                .filter(
                  (l) =>
                    l.trim() &&
                    !l.trim().startsWith("@") &&
                    !l.trim().startsWith("[") &&
                    !(l.trim().startsWith("#") && !l.trim().toLowerCase().startsWith("#track")),
                ).length /
                Math.max(1, notesTrackRoles.size) /
                4,
            ),
          )
        : bars,
    bpm,
    beatsPerBar,
  );

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);
    if (activeTrackCount === 0) {
      setError("Enable at least one track role before generating");
      setLoading(false);
      return;
    }
    if (mode === "text" && !prompt.trim()) {
      setError("Enter a text prompt before generating");
      setLoading(false);
      return;
    }
    if (needsAi && !aiReady) {
      setError(
        aiConfigured === false
          ? "Local GGUF model is missing — place it under backend/models/"
          : "Local model is offline — wait for it to load, or check backend logs",
      );
      setLoading(false);
      return;
    }
    const safeBpm = clampBpm(bpm);
    if (safeBpm !== bpm) setBpm(safeBpm);
    if (mode === "text" && !isValidBars(bars)) {
      setError(`bars must be between ${BARS_MIN} and ${BARS_MAX}, got ${bars}`);
      setLoading(false);
      return;
    }
    const safeBars = mode === "text" ? normalizeBars(bars) : bars;
    if (mode === "text") {
      if (!isValidMood(mood)) {
        setError(
          `Unsupported mood "${mood}". Allowed values: ${MOODS.join(", ")}`,
        );
        setLoading(false);
        return;
      }
      if (!isValidStyle(style)) {
        setError(
          `Unsupported style "${style}". Allowed values: ${STYLES.join(", ")}`,
        );
        setLoading(false);
        return;
      }
    }
    const safeMood = mode === "text" ? normalizeMood(mood) : mood;
    const safeStyle = mode === "text" ? normalizeStyle(style) : style;
    if (!isValidTimeSignature(tsNumerator, tsDenominator)) {
      setError(
        `Invalid time signature ${tsNumerator}/${tsDenominator}. ` +
          `Use numerator ${TS_NUMERATOR_MIN}–${TS_NUMERATOR_MAX} and ` +
          `denominator ${TS_DENOMINATORS.join(", ")}.`,
      );
      setLoading(false);
      return;
    }
    const safeTs = normalizeTimeSignature(tsNumerator, tsDenominator);

    let chordParts: string[] = [];
    let notes: string[] = [];
    if (mode === "chords") {
      chordParts = splitChordProgression(progression);
      if (chordParts.length === 0) {
        setError("Enter at least one chord (e.g. C | G | Am | F)");
        setLoading(false);
        return;
      }
    } else if (mode === "notes") {
      notes = notesText
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean);
      if (notes.length === 0) {
        setError("Enter at least one note line (or @track / [Section] block)");
        setLoading(false);
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
        setLoading(false);
        return;
      }
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
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
            filename,
            seed,
          },
          { signal },
        );
      } else if (mode === "chords") {
        result = await generateFromChords(
          {
            progression,
            bpm: safeBpm,
            bars_per_chord: barsPerChord,
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
            filename: filename || "chords.mid",
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
            filename: filename || "notes.mid",
            seed,
          },
          { signal },
        );
      }
      setSuccess(
        `Downloaded ${result.filename}` +
          (result.bpm ? ` · ${result.bpm} BPM` : "") +
          (result.timeSig ? ` · ${result.timeSig}` : "") +
          (result.key ? ` · ${result.key}` : "") +
          (result.bars ? ` · ${result.bars} bars` : "") +
          (result.tracks ? ` · ${result.tracks} tracks` : ""),
      );
    } catch (err) {
      if (isAbortError(err)) {
        setError("Generation cancelled");
      } else {
        setError(err instanceof Error ? err.message : "Something went wrong");
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
      setLoading(false);
    }
  }

  function cancelGeneration() {
    abortRef.current?.abort();
  }

  function clearSolos() {
    setSolo({ melody: false, chords: false, bass: false, drums: false });
  }

  const anySolo = TRACK_META.some(({ id }) => {
    const included =
      mode === "notes" ? notesTrackRoles.has(id) : tracks[id];
    return included && solo[id];
  });

  return (
    <main className="mx-auto min-h-screen max-w-7xl px-4 pb-28 pt-6 sm:px-6 lg:px-8">
      {/* Top bar */}
      <header className="animate-rise mb-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-[var(--signal)]">
              DAW-ready · Standard MIDI
            </p>
            <h1 className="brand text-4xl leading-none text-[var(--ink)] sm:text-5xl">
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
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${
              apiOk
                ? "border-[#b7e4c7] bg-[#e8f8ef] text-[var(--ok)]"
                : apiOk === false
                  ? "border-[#f3c1bc] bg-[#fdecea] text-[var(--danger)]"
                  : "border-[var(--line)] bg-white text-[var(--muted)]"
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
            {apiOk === false && `API offline · ${API_BASE}`}
          </span>
          <span
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${
              aiConfigured && aiOnline
                ? "border-[var(--signal-soft)] bg-[var(--signal-soft)] text-[var(--accent-deep)]"
                : aiConfigured
                  ? "border-[#fde68a] bg-[#fffbeb] text-[#92400e]"
                  : "border-[var(--line)] bg-white text-[var(--muted)]"
            }`}
          >
            {!aiConfigured && "Local model missing"}
            {aiConfigured && aiOnline && `${aiProvider === "local" ? "Local" : aiProvider} · ${aiModel || "online"}`}
            {aiConfigured && aiOnline === false && `Local offline · ${aiModel || "file"}`}
            {aiConfigured && aiOnline === null && `Local · ${aiModel || "checking"}`}
          </span>
        </div>
      </header>

      <div className="animate-rise-delay grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <form onSubmit={onSubmit} className="space-y-5">
          {/* Mode + input */}
          <section className="section-card p-5 sm:p-6">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-bold uppercase tracking-[0.14em] text-[var(--muted)]">
                01 · Compose
              </h2>
              <div className="flex rounded-xl bg-[var(--glow)] p-1">
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
                    onClick={() => setMode(id)}
                    className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
                      mode === id
                        ? "bg-[var(--ink)] text-white shadow-sm"
                        : "text-[var(--muted)] hover:text-[var(--ink)]"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {mode === "text" && (
              <label className="block">
                <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.08em] text-[var(--muted)]">
                  Prompt — mood · instrument · key · BPM · bars
                </span>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={3}
                  className="field-input resize-y"
                  placeholder="Make a sad violin melody in A Minor, 90 BPM, 8 bars, cinematic mood."
                  required
                />
              </label>
            )}

            {mode === "chords" && (
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
                <p className="mt-2 text-xs text-[var(--muted)]">
                  Exact MIDI from chord symbols (no AI). Formats:{" "}
                  <code>C | G | Am | F</code>, <code>C - G - Am - F</code>, etc.
                  Qualities: maj, m, 7, maj7, m7, sus, dim, 9, m7b5, 7b9, slash{" "}
                  <code>C/G</code>…
                </p>
              </label>
            )}

            {mode === "notes" && (
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
                <p className="mt-2 text-xs text-[var(--muted)]">
                  Format: <code>C4 q</code>, same-beat chord{" "}
                  <code>C4 E4 G4 q</code>, <code>rest q</code>. Durations:{" "}
                  <code>w h q e s</code> (whole / half / quarter / eighth /
                  sixteenth). Optional velocity: <code>C4 q 90</code>. Multi-track:{" "}
                  <code>@track Bass</code>.
                </p>
              </label>
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
                    min={0.25}
                    max={16}
                    step={0.25}
                    value={barsPerChord}
                    onChange={(e) => setBarsPerChord(Number(e.target.value))}
                    onBlur={() =>
                      setBarsPerChord((v) => {
                        if (!Number.isFinite(v) || v <= 0) return 1;
                        return Math.min(16, Math.max(0.25, v));
                      })
                    }
                    className="field-input"
                  />
                </Field>
              )}
              <Field label="Seed" hint="Reproducible AI">
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
                    className="rounded-lg border border-[var(--line)] bg-white px-2 text-xs font-semibold text-[var(--muted)]"
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
                    <select
                      value={mood}
                      onChange={(e) => {
                        markTouched("mood");
                        setMood(e.target.value as Mood);
                      }}
                      className="field-input"
                    >
                      {MOODS.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Style">
                    <select
                      value={style}
                      onChange={(e) => {
                        markTouched("style");
                        setStyle(e.target.value as Style);
                      }}
                      className="field-input"
                    >
                      {STYLES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </Field>
                </>
              )}
              <Field label="MIDI type">
                <select
                  value={fileType}
                  onChange={(e) => setFileType(Number(e.target.value) as 0 | 1)}
                  className="field-input"
                >
                  <option value={1}>Type 1 · multi-track</option>
                  <option value={0}>Type 0 · single track</option>
                </select>
              </Field>
              <Field label="Filename">
                <input
                  value={filename}
                  onChange={(e) => setFilename(e.target.value)}
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
                  className="rounded-lg border border-[var(--warn)] bg-[#fff7ed] px-3 py-1.5 text-xs font-bold text-[var(--warn)]"
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
                    className={`rounded-full px-3.5 py-1.5 text-sm font-semibold transition disabled:cursor-default ${
                      on
                        ? "text-white"
                        : "bg-white text-[var(--muted)] ring-1 ring-[var(--line)]"
                    }`}
                    style={on ? { background: color } : undefined}
                    title={
                      mode === "notes"
                        ? "Controlled by @track / [Name] lines in the notes input"
                        : undefined
                    }
                  >
                    {label}
                  </button>
                );
              })}
            </div>

            <div className="overflow-x-auto rounded-xl border border-[var(--line)]">
              <table className="w-full min-w-[720px] border-collapse text-sm">
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
                        className={`border-t border-[var(--line)] bg-white/80 ${
                          inactive ? "opacity-45" : ""
                        }`}
                      >
                        <td className="px-3 py-3">
                          <div className="flex items-center gap-2 font-semibold">
                            <span
                              className="h-2.5 w-2.5 rounded-full"
                              style={{ background: color }}
                            />
                            {label}
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <select
                            value={trackInstrument[id]}
                            disabled={inactive}
                            onChange={(e) => {
                              if (id === "melody") markTouched("instrument");
                              setTrackInstrument((p) => ({
                                ...p,
                                [id]: e.target.value,
                              }));
                            }}
                            className="field-input py-1.5 text-sm"
                          >
                            {instrumentOptions.map((opt) => (
                              <option key={opt} value={opt}>
                                {labelize(opt)}
                              </option>
                            ))}
                          </select>
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
                  <option value={96}>96</option>
                  <option value={192}>192</option>
                  <option value={240}>240</option>
                  <option value={384}>384</option>
                  <option value={480}>480 default</option>
                  <option value={960}>960</option>
                  <option value={1920}>1920</option>
                </select>
              </Field>
              <Field label="Quantize">
                <select
                  value={quantize}
                  onChange={(e) => setQuantize(e.target.value)}
                  className="field-input"
                >
                  <option value="">Off</option>
                  <option value="1/4">1/4</option>
                  <option value="1/8">1/8</option>
                  <option value="1/16">1/16</option>
                  <option value="1/32">1/32</option>
                </select>
              </Field>
              <Field label="Swing grid">
                <select
                  value={swingGrid}
                  onChange={(e) => setSwingGrid(e.target.value)}
                  className="field-input"
                >
                  <option value="1/4">1/4</option>
                  <option value="1/8">1/8</option>
                  <option value="1/16">1/16</option>
                  <option value="1/32">1/32</option>
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
                    max={0.12}
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
                    max={32}
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
                    max={0.12}
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
                      : "bg-white text-[var(--muted)] ring-1 ring-[var(--line)]"
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
                      max={8}
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
                      max={2}
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
                      max={2000}
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
                      max={16}
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
                      max={2}
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

          {/* Sticky-ish generate */}
          <div className="section-card sticky bottom-4 z-10 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
            <div className="text-sm text-[var(--muted)]">
              <span className="font-bold text-[var(--ink)]">{filename || "out.mid"}</span>
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
                  className="inline-flex min-h-12 min-w-[120px] items-center justify-center rounded-xl border border-[var(--line)] bg-white px-5 text-base font-bold text-[var(--ink)] transition hover:bg-[var(--glow)]"
                >
                  Cancel
                </button>
              )}
              <button
                type="submit"
                disabled={generateBlocked}
                className="generate-btn inline-flex min-h-12 min-w-[220px] items-center justify-center rounded-xl px-6 text-base font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
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
                    : "Waiting for local model…"
                ) : apiOk === false ? (
                  "API offline"
                ) : (
                  "Generate & download .mid"
                )}
              </button>
            </div>
          </div>

          {error && (
            <p className="rounded-xl border border-[#f3c1bc] bg-[#fdecea] px-4 py-3 text-sm text-[var(--danger)]">
              {error}
            </p>
          )}
          {success && (
            <p className="rounded-xl border border-[#b7e4c7] bg-[#e8f8ef] px-4 py-3 text-sm text-[var(--ok)]">
              {success}
            </p>
          )}
        </form>

        {/* Sidebar */}
        <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          <div className="overflow-hidden rounded-2xl bg-[var(--ink)] p-5 text-white shadow-lg">
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[var(--signal)]">
              Session
            </p>
            <h2 className="brand mt-2 text-3xl">Export preview</h2>
            <dl className="mt-5 space-y-3 text-sm text-[#c5d4dc]">
              <div className="flex justify-between gap-3">
                <dt>Mode</dt>
                <dd className="font-semibold text-white capitalize">{mode}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>Tempo</dt>
                <dd className="font-semibold text-white">{bpm} BPM</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>Key</dt>
                <dd className="font-semibold text-white">{key}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>Est. length</dt>
                <dd className="font-semibold text-white">~{durationSec}s</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>Tracks out</dt>
                <dd className="font-semibold text-white">{activeTrackCount}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>File type</dt>
                <dd className="font-semibold text-white">Type {fileType}</dd>
              </div>
            </dl>
            <div className="mt-6 h-16 overflow-hidden rounded-xl bg-[linear-gradient(110deg,#163029_0%,#1a2a38_45%,#0f766e_100%)]">
              <div className="flex h-full items-end gap-1 px-3 pb-2 opacity-80">
                {[40, 70, 55, 90, 60, 80, 45, 75, 95, 50, 65, 85].map((h, i) => (
                  <span
                    key={i}
                    className="flex-1 rounded-sm bg-[#9ee5dc]"
                    style={{ height: `${h}%` }}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="section-card p-5">
            <h3 className="text-sm font-bold uppercase tracking-[0.12em] text-[var(--muted)]">
              Quick presets
            </h3>
            <ul className="mt-4 space-y-2">
              <li>
                <button
                  type="button"
                  className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-3 text-left transition hover:border-[var(--accent)] hover:bg-[var(--signal-soft)]"
                  onClick={() => {
                    lockPresetFields();
                    setMode("text");
                    setPrompt(
                      "Create a happy piano melody in C Major, 120 BPM, 8 bars.",
                    );
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
                    setFilename("happy_piano.mid");
                  }}
                >
                  <span className="block text-sm font-bold text-[var(--ink)]">
                    Happy 8-bar piano
                  </span>
                  <span className="text-xs text-[var(--muted)]">
                    120 BPM · C Major · Pop
                  </span>
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-3 text-left transition hover:border-[var(--accent)] hover:bg-[var(--signal-soft)]"
                  onClick={() => {
                    lockPresetFields();
                    setMode("text");
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
                    setFilename("sad_violin.mid");
                  }}
                >
                  <span className="block text-sm font-bold text-[var(--ink)]">
                    Sad cinematic violin
                  </span>
                  <span className="text-xs text-[var(--muted)]">
                    90 BPM · A Minor · 8 bars
                  </span>
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-3 text-left transition hover:border-[var(--accent)] hover:bg-[var(--signal-soft)]"
                  onClick={() => {
                    setMode("chords");
                    setProgression("C | G | Am | F");
                    setBpm(120);
                    setKey("C Major");
                    setTracks({
                      melody: true,
                      chords: true,
                      bass: true,
                      drums: true,
                    });
                    clearSolos();
                    setFilename("progression.mid");
                  }}
                >
                  <span className="block text-sm font-bold text-[var(--ink)]">
                    C → G → Am → F + drums
                  </span>
                  <span className="text-xs text-[var(--muted)]">
                    Full 4-track arrangement
                  </span>
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-3 text-left transition hover:border-[var(--accent)] hover:bg-[var(--signal-soft)]"
                  onClick={() => {
                    setMode("notes");
                    setBpm(120);
                    setNotesText(
                      ["C4 q", "E4 q", "G4 h", "rest q", "C5 q", "B4 q", "A4 h"].join(
                        "\n",
                      ),
                    );
                    setQuantize("");
                    setHumanize(false);
                    setTrackInstrument((t) => ({
                      ...t,
                      melody: "acoustic_grand_piano",
                    }));
                    clearSolos();
                    setFilename("note_list.mid");
                  }}
                >
                  <span className="block text-sm font-bold text-[var(--ink)]">
                    Sheet-style note list
                  </span>
                  <span className="text-xs text-[var(--muted)]">
                    C4 q · E4 q · G4 h · exact timing
                  </span>
                </button>
              </li>
            </ul>
          </div>
        </aside>
      </div>
    </main>
  );
}
