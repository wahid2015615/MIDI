"""AI music generation via local GGUF LLM → structured MIDI JSON."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.catalog import (
    DEFAULT_MOOD,
    DEFAULT_STYLE,
    STYLE_BPM_HINTS,
    STYLE_DEFAULT_MOOD,
    match_mood_in_text,
    match_style_in_text,
    normalize_mood,
    normalize_style,
)
from app.core.engine import (
    BARS_DEFAULT,
    MidiEngine,
    TS_NUMERATOR_MAX,
    TS_NUMERATOR_MIN,
    VALID_TS_DENOMINATORS,
    clamp_bars,
    clamp_bpm,
    normalize_bars,
    normalize_time_signature,
)
from app.features.chords_to_midi.inputs import (
    parse_progression_string,
    validate_progression_chords,
)
from app.features.generation.ai_client import AIMusicError, compose_midi_json
from app.features.generation.ai_client import model_status as ai_model_status
from app.features.generation.composer import composition_to_engine
from app.features.generation.prompts import (
    SYSTEM_PROMPT,
    build_text_user_prompt,
)


def _progress(message: str) -> None:
    print(f"[MIDIgen] {message}", flush=True)


@dataclass
class PromptSpec:
    bars: int = BARS_DEFAULT
    bpm: float = 120.0
    key: str = "C Major"
    mood: str = DEFAULT_MOOD
    style: str = DEFAULT_STYLE
    instrument: str = "acoustic_grand_piano"
    include_chords: bool = True
    include_bass: bool = True
    include_drums: bool = False
    time_signature: tuple[int, int] = (4, 4)


@dataclass
class PromptParseResult:
    """Parsed prompt values plus which fields were explicitly found in the text."""

    spec: PromptSpec
    detected: dict[str, bool]


def parse_text_prompt_detailed(text: str) -> PromptParseResult:
    """Extract fields from a prompt and record which ones were explicitly detected.

    ``detected`` is used by the studio UI to auto-fill only mentioned fields,
    so defaults do not clobber the form when the prompt is silent on a field.
    """
    lower = text.lower()
    spec = PromptSpec()
    detected: dict[str, bool] = {
        "bars": False,
        "bpm": False,
        "key": False,
        "mood": False,
        "style": False,
        "instrument": False,
        "include_chords": False,
        "include_bass": False,
        "include_drums": False,
        "time_signature": False,
    }

    bpm_match = re.search(r"(\d+)\s*bpm", lower)
    if bpm_match:
        spec.bpm = clamp_bpm(float(bpm_match.group(1)))
        detected["bpm"] = True

    bars_match = re.search(r"(\d+)\s*-?\s*bars?", lower)
    if bars_match:
        spec.bars = clamp_bars(int(bars_match.group(1)))
        detected["bars"] = True

    # Numeric meter: "3/4", "in 6/8", "time signature 7/8"
    for ts_match in re.finditer(r"\b(\d{1,2})\s*/\s*(\d{1,2})\b", lower):
        num_i = int(ts_match.group(1))
        den_i = int(ts_match.group(2))
        if (
            TS_NUMERATOR_MIN <= num_i <= TS_NUMERATOR_MAX
            and den_i in VALID_TS_DENOMINATORS
        ):
            spec.time_signature = (num_i, den_i)
            detected["time_signature"] = True
            break
    if not detected["time_signature"]:
        # Word meters (only when no explicit N/D was found)
        if re.search(r"\bwaltz\b", lower):
            spec.time_signature = (3, 4)
            detected["time_signature"] = True
        elif re.search(r"\bcut\s+time\b|\balla\s+breve\b", lower):
            spec.time_signature = (2, 2)
            detected["time_signature"] = True
        elif re.search(r"\bcommon\s+time\b", lower):
            spec.time_signature = (4, 4)
            detected["time_signature"] = True

    # Require Major/Minor so the English article "a" is never parsed as key "A"
    key_match = re.search(
        r"\b([A-G](?:#|b)?)\s*(major|minor|maj|min)\b",
        text,
        flags=re.IGNORECASE,
    )
    if key_match:
        root = key_match.group(1)
        mode = key_match.group(2)
        mode = "Minor" if mode.lower().startswith("min") else "Major"
        # Preserve accidental casing from the match (e.g. Bb / C#)
        root = root[0].upper() + root[1:]
        spec.key = f"{root} {mode}"
        detected["key"] = True

    mood = match_mood_in_text(text)
    if mood is not None:
        spec.mood = mood
        detected["mood"] = True

    style = match_style_in_text(text)
    if style is not None:
        spec.style = style
        detected["style"] = True
        # Style-based BPM/mood are soft hints for generation defaults only —
        # do NOT mark detected so Studio autofill will not overwrite the form.
        if not bpm_match and style in STYLE_BPM_HINTS:
            spec.bpm = float(STYLE_BPM_HINTS[style])
        if mood is None and style in STYLE_DEFAULT_MOOD:
            spec.mood = STYLE_DEFAULT_MOOD[style]

    # Role negations before instrument scan — "no bass" must not pick bass program
    if re.search(r"\b(?:no|without)\s+chords?\b", lower) or "melody only" in lower:
        spec.include_chords = False
        detected["include_chords"] = True
    if re.search(r"\b(?:no|without)\s+bass\b", lower):
        spec.include_bass = False
        detected["include_bass"] = True
    if re.search(r"\b(?:no|without)\s+drums?\b", lower):
        spec.include_drums = False
        detected["include_drums"] = True
    else:
        # Genre "drum and bass" / DnB is not a drum-kit request
        drums_text = re.sub(
            r"\bdrum\s*(?:&|and|n)\s*bass\b|\bdn'?b\b",
            " ",
            lower,
        )
        if re.search(
            r"\b(?:with\s+drums?|add\s+drums?|drum\s*kit|drums?\s+track|and\s+drums?)\b",
            drums_text,
        ) or re.search(r"\bdrums?\b", drums_text):
            spec.include_drums = True
            detected["include_drums"] = True

    instruments = {
        "electric piano": "electric_piano_1",
        "bass guitar": "electric_bass_finger",
        "electric bass": "electric_bass_finger",
        "piano": "acoustic_grand_piano",
        "guitar": "steel_guitar",
        "violin": "violin",
        "flute": "flute",
        "synth": "lead_1_square",
        "strings": "string_ensemble_1",
        "bass": "electric_bass_finger",
    }
    # Arrangement phrases / negations are not melody-instrument cues
    skip_bass_as_instrument = (not spec.include_bass) or bool(
        re.search(r"\bbass\s*lines?\b", lower)
    )
    # Don't treat the genre phrase as an instrument cue either
    instrument_text = re.sub(
        r"\bdrum\s*(?:&|and|n)\s*bass\b|\bdn'?b\b",
        " ",
        lower,
    )
    # Longer phrases first so "electric piano" / "bass guitar" win shorter words
    for name, program in sorted(instruments.items(), key=lambda kv: -len(kv[0])):
        if program == "electric_bass_finger" and skip_bass_as_instrument:
            continue
        if re.search(rf"\b{re.escape(name)}\b", instrument_text):
            spec.instrument = program
            detected["instrument"] = True
            break

    return PromptParseResult(spec=spec, detected=detected)


def parse_text_prompt(text: str) -> PromptSpec:
    """Extract explicit fields from a prompt for UI / constraint overrides."""
    return parse_text_prompt_detailed(text).spec


def generate_from_prompt(
    text: str,
    seed: int | None = 42,
    *,
    bpm: float | None = None,
    bars: int | None = None,
    key: str | None = None,
    time_signature: tuple[int, int] | None = None,
    mood: str | None = None,
    style: str | None = None,
    instrument: str | None = None,
    include_chords: bool | None = None,
    include_bass: bool | None = None,
    include_drums: bool | None = None,
    include_melody: bool | None = None,
    instrument_chords: str | None = None,
    instrument_bass: str | None = None,
    instrument_drums: str | None = None,
    client_request_id: str | None = None,
) -> MidiEngine:
    spec = parse_text_prompt(text)
    if bpm is not None:
        spec.bpm = clamp_bpm(bpm)
    if bars is not None:
        spec.bars = normalize_bars(bars)
    else:
        spec.bars = normalize_bars(spec.bars)
    if key is not None:
        spec.key = key
    if mood is not None:
        spec.mood = normalize_mood(mood)
    else:
        spec.mood = normalize_mood(spec.mood)
    if style is not None:
        spec.style = normalize_style(style)
    else:
        spec.style = normalize_style(spec.style)
    if instrument is not None:
        spec.instrument = instrument
    if include_chords is not None:
        spec.include_chords = include_chords
    if include_bass is not None:
        spec.include_bass = include_bass
    if include_drums is not None:
        spec.include_drums = include_drums

    do_melody = True if include_melody is None else include_melody
    if not (
        do_melody
        or spec.include_chords
        or spec.include_bass
        or spec.include_drums
    ):
        raise ValueError("Enable at least one track role before generating")
    chords_inst = instrument_chords or "electric_piano_1"
    bass_inst = instrument_bass or "electric_bass_finger"
    drums_inst = instrument_drums or "drum_kit"
    ts = normalize_time_signature(
        *(time_signature if time_signature is not None else spec.time_signature)
    )

    user_prompt = build_text_user_prompt(
        prompt=text,
        bpm=spec.bpm,
        bars=spec.bars,
        key=spec.key,
        mood=spec.mood,
        style=spec.style,
        instrument=spec.instrument,
        include_melody=do_melody,
        include_chords=spec.include_chords,
        include_bass=spec.include_bass,
        include_drums=spec.include_drums,
        instrument_chords=chords_inst,
        instrument_bass=bass_inst,
        instrument_drums=drums_inst,
        time_signature=ts,
        seed=seed,
    )

    try:
        data = compose_midi_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            seed=seed,
            client_request_id=client_request_id,
        )
    except AIMusicError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AIMusicError(f"AI generation failed: {exc}") from exc

    data["bpm"] = spec.bpm
    data["key"] = spec.key
    data["time_signature"] = [ts[0], ts[1]]
    _progress("Building MidiEngine from composition JSON...")
    engine = composition_to_engine(data)
    _progress("Composition → engine ready")
    return engine


def generate_from_chords(
    progression: str | list[str],
    bpm: float = 120.0,
    bars_per_chord: float = 1.0,
    add_chords: bool = True,
    add_melody: bool = True,
    add_bass: bool = True,
    add_drums: bool = False,
    key: str = "C Major",
    time_signature: tuple[int, int] | None = None,
    melody_instrument: str = "acoustic_grand_piano",
    instrument_chords: str = "electric_piano_1",
    instrument_bass: str = "electric_bass_finger",
    instrument_drums: str = "drum_kit",
    seed: int | None = 42,
) -> MidiEngine:
    """Generate exact chord arrangement (deterministic; no LLM).

    Chord / bass / melody tones come from ``parse_chord_symbol`` so progression
    qualities (e.g. Am7, E7b9, Bm7b5) appear as real MIDI pitch classes.
    ``seed`` is accepted for API compatibility (humanize/timing applied later).
    """
    from app.features.chords_to_midi.exact import build_exact_chords_engine

    chords = (
        parse_progression_string(progression)
        if isinstance(progression, str)
        else list(progression)
    )
    validate_progression_chords(chords)
    if not any((add_chords, add_melody, add_bass, add_drums)):
        raise ValueError("Enable at least one track role before generating")

    ts = normalize_time_signature(*(time_signature or (4, 4)))
    bpm = clamp_bpm(bpm)
    _ = seed  # reserved for post-pipeline humanize; arrangement is exact

    _progress("Building exact chord arrangement (no AI)...")
    engine = build_exact_chords_engine(
        chords,
        bpm=bpm,
        bars_per_chord=bars_per_chord,
        key=key,
        time_signature=ts,
        add_chords=add_chords,
        add_melody=add_melody,
        add_bass=add_bass,
        add_drums=add_drums,
        melody_instrument=melody_instrument,
        instrument_chords=instrument_chords,
        instrument_bass=instrument_bass,
        instrument_drums=instrument_drums,
    )
    _progress("Exact chords → engine ready")
    return engine


def model_status() -> dict:
    return ai_model_status()
