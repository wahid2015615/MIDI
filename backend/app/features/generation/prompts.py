"""Prompts for LLM → structured MIDI JSON."""

from app.core.engine import BARS_MAX, clamp_bars

# Keep schema NOTES-ONLY — expression (sustain/CC/PB) is applied by the backend.
SYSTEM_PROMPT = """
You are a MIDI composer. Output ONLY one valid JSON object. No markdown. No <think>. No text outside JSON.

Schema (exactly these keys):
{
  "bpm": 120,
  "time_signature": [4, 4],
  "key": "C Major",
  "tracks": [
    {
      "name": "Melody",
      "instrument": "acoustic_grand_piano",
      "notes": [
        { "pitch": 60, "start_beat": 0.0, "duration_beats": 1.0, "velocity": 90 }
      ]
    }
  ]
}

Rules:
- pitch: MIDI 0-127 integer. Drums: kick=36, snare=38, hat=42.
- start_beat / duration_beats: quarter-note beats (bar1 beat1 = 0.0)
- velocity: 1-127
- Track name must be Melody, Chords, Bass, or Drums
- instrument must be one of:
  acoustic_grand_piano, electric_piano_1, steel_guitar, electric_bass_finger,
  string_ensemble_1, violin, flute, lead_1_square, drum_kit
- Drums track instrument must be drum_kit
- Do NOT include cc, sustain, pitch_bends, muted, or solo
- Prefer sparse, grid-aligned notes so JSON is short and complete
- Always finish with valid closed braces
""".strip()


def _note_budget(bars: int, track_count: int) -> int:
    """Cap note count so local GGUF can finish one valid JSON response."""
    bars = max(1, int(bars))
    track_count = max(1, int(track_count))
    # ~2–4 notes/bar/track, hard cap to keep response small on CPU
    return min(96, max(8, bars * track_count * 3))


def build_text_user_prompt(
    *,
    prompt: str,
    bpm: float,
    bars: int,
    key: str,
    mood: str,
    style: str,
    instrument: str,
    include_melody: bool,
    include_chords: bool,
    include_bass: bool,
    include_drums: bool,
    instrument_chords: str = "electric_piano_1",
    instrument_bass: str = "electric_bass_finger",
    instrument_drums: str = "drum_kit",
    time_signature: tuple[int, int] = (4, 4),
    seed: int | None = None,
) -> str:
    tracks = []
    instrument_lines: list[str] = []
    if include_melody:
        tracks.append("Melody")
        instrument_lines.append(f"Melody instrument: {instrument}")
    if include_chords:
        tracks.append("Chords")
        instrument_lines.append(f"Chords instrument: {instrument_chords}")
    if include_bass:
        tracks.append("Bass")
        instrument_lines.append(f"Bass instrument: {instrument_bass}")
    if include_drums:
        tracks.append("Drums")
        instrument_lines.append(f"Drums instrument: {instrument_drums}")
    if not tracks:
        raise ValueError("Enable at least one track role before generating")

    instruments_block = "\n".join(f"- {line}" for line in instrument_lines)
    ts_num, ts_den = time_signature
    beats_per_bar = ts_num * (4.0 / ts_den)
    total_beats = bars * beats_per_bar
    seed_line = f"\n- Variation seed: {seed}" if seed is not None else ""
    budget = _note_budget(bars, len(tracks))

    return f"""
Compose MIDI for this request:
User prompt: {prompt}

Constraints:
- BPM: {bpm}
- Bars: {bars}
- Key: {key}
- Mood: {mood}
- Style: {style}
{instruments_block}
- Required tracks only: {", ".join(tracks)}
- Use exactly the instrument ids listed above for each track
- Time signature: {ts_num}/{ts_den}
- Fill {bars} bars (total beats ≈ {total_beats}){seed_line}
- Max ~{budget} notes total across all tracks (keep JSON short)
- Notes only — no cc/sustain/pitch_bends
- Return ONE complete JSON object only
""".strip()


def build_chords_user_prompt(
    *,
    chords: list[str],
    bpm: float,
    bars_per_chord: float,
    key: str,
    melody_instrument: str,
    include_chords: bool,
    include_melody: bool,
    include_bass: bool,
    include_drums: bool,
    instrument_chords: str = "electric_piano_1",
    instrument_bass: str = "electric_bass_finger",
    instrument_drums: str = "drum_kit",
    time_signature: tuple[int, int] = (4, 4),
    seed: int | None = None,
) -> str:
    total_bars = clamp_bars(
        max(1, int(round(len(chords) * bars_per_chord))), maximum=BARS_MAX
    )
    tracks: list[str] = []
    instrument_lines: list[str] = []
    if include_chords:
        tracks.append("Chords")
        instrument_lines.append(f"Chords instrument: {instrument_chords}")
    if include_melody:
        tracks.append("Melody")
        instrument_lines.append(f"Melody instrument: {melody_instrument}")
    if include_bass:
        tracks.append("Bass")
        instrument_lines.append(f"Bass instrument: {instrument_bass}")
    if include_drums:
        tracks.append("Drums")
        instrument_lines.append(f"Drums instrument: {instrument_drums}")
    if not tracks:
        raise ValueError("Enable at least one track role before generating")

    instruments_block = "\n".join(f"- {line}" for line in instrument_lines)
    ts_num, ts_den = time_signature
    seed_line = f"\nVariation seed: {seed}" if seed is not None else ""
    budget = _note_budget(total_bars, len(tracks))

    chords_rule = (
        "\nThe Chords track must follow the given symbols in order."
        if include_chords
        else "\nUse the progression as harmonic context for the requested tracks."
    )

    return f"""
Compose MIDI over this chord progression:
Progression: {" - ".join(chords)}
Bars per chord: {bars_per_chord}
Total bars: {total_bars}
BPM: {bpm}
Key: {key}
{instruments_block}
Required tracks: {", ".join(tracks)}
Use exactly the instrument ids listed above for each track.
Time signature: {ts_num}/{ts_den}{seed_line}
{chords_rule}
Max ~{budget} notes total. Notes only — no cc/sustain/pitch_bends.
Return ONE complete JSON object only.
""".strip()
