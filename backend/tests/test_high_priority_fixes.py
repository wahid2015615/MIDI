"""Regression tests for the nine High-priority audit fixes."""

from __future__ import annotations

from pathlib import Path

import pytest
from mido import MidiFile

from app.core.engine import MidiEngine
from app.core.theory import parse_chord_symbol
from app.features.chords_to_midi.inputs import (
    parse_progression_string,
    validate_progression_chords,
)
from app.features.generation.composer import _canonical_track_name, composition_to_engine
from app.features.generation.service import parse_text_prompt_detailed
from app.shared.midi_response import apply_track_mix, apply_track_selection
from app.shared.schemas import TrackMixOptions


# --- H1: drum negation -------------------------------------------------


def test_no_drums_does_not_enable_drums() -> None:
    for prompt in (
        "piano melody with no drums please",
        "uplifting song without drums",
        "melody without drum kit",
    ):
        result = parse_text_prompt_detailed(prompt)
        assert result.spec.include_drums is False, prompt
        assert result.detected["include_drums"] is True, prompt


def test_affirmative_drums_still_enable() -> None:
    result = parse_text_prompt_detailed("happy pop song with drums at 120 BPM")
    assert result.spec.include_drums is True
    assert result.detected["include_drums"] is True


# --- H9: style-inferred BPM/mood not detected --------------------------


def test_style_bpm_mood_hints_not_marked_detected() -> None:
    # Style-only prompt (no explicit mood word, no "N BPM")
    result = parse_text_prompt_detailed("synthwave track")
    assert result.detected["style"] is True
    # Soft hints may fill spec for generation defaults, but must not be
    # marked detected so Studio autofill will not overwrite the form.
    assert result.detected["bpm"] is False
    assert result.detected["mood"] is False
    assert result.spec.bpm == 100.0  # STYLE_BPM_HINTS soft fill


def test_explicit_bpm_still_detected() -> None:
    result = parse_text_prompt_detailed("lo-fi at 85 BPM")
    assert result.detected["bpm"] is True
    assert result.spec.bpm == 85


# --- H2 / H3: jazz chord symbols ---------------------------------------


def test_co_is_diminished_not_half_dim() -> None:
    # Co = diminished triad; Co7 = fully diminished seventh
    assert parse_chord_symbol("Co") == [48, 51, 54]
    assert parse_chord_symbol("Co7") == [48, 51, 54, 57]
    # Half-dim still via ø
    assert parse_chord_symbol("Cø") == [48, 51, 54, 58]
    assert parse_chord_symbol("Cø7") == [48, 51, 54, 58]


def test_c_minus_7_is_minor_seventh() -> None:
    assert parse_chord_symbol("C-7") == parse_chord_symbol("Cm7")
    assert parse_chord_symbol("F-7") == parse_chord_symbol("Fm7")


def test_progression_preserves_jazz_hyphen_chords() -> None:
    assert parse_progression_string("C-7 - F-7 - Bbmaj7") == [
        "C-7",
        "F-7",
        "Bbmaj7",
    ]
    validate_progression_chords(parse_progression_string("C-7 - F-7 - Bbmaj7"))
    # Classic unspaced majors still work
    assert parse_progression_string("C-G-Am-F") == ["C", "G", "Am", "F"]
    # Unspaced jazz hyphen repaired
    assert parse_progression_string("C-7-F-7") == ["C-7", "F-7"]


# --- H4: Bassoon must not become Bass ----------------------------------


def test_bassoon_not_aliased_to_bass() -> None:
    assert _canonical_track_name("Bassoon") == "Bassoon"
    assert _canonical_track_name("Bassline") == "Bass"
    assert _canonical_track_name("Electric Bass") == "Bass"
    assert _canonical_track_name("Lead Synth") == "Melody"
    assert _canonical_track_name("Pads") == "Chords"


# --- H5: melodic role cannot use drum_kit ------------------------------


def test_mix_rejects_drum_kit_on_melody() -> None:
    engine = MidiEngine(bpm=120)
    engine.add_track("Melody", "acoustic_grand_piano").add_note(60, 0, 1)
    engine.add_track("Drums", "drum_kit").add_note(36, 0, 1)
    with pytest.raises(ValueError, match="cannot use drum instrument"):
        apply_track_mix(
            engine,
            TrackMixOptions(instrument_melody="drum_kit"),
        )


def test_export_rejects_two_active_drum_kits(tmp_path: Path) -> None:
    engine = MidiEngine(bpm=120)
    engine.add_track("Melody", "drum_kit").add_note(36, 0, 1)
    engine.add_track("Drums", "drum_kit").add_note(38, 0, 1)
    with pytest.raises(ValueError, match="Only one active drum track"):
        engine.export(tmp_path / "dual_drums.mid", file_type=1)


# --- H6: unmapped track names muted by selection -----------------------


def test_selection_mutes_non_role_tracks() -> None:
    data = {
        "bpm": 120,
        "tracks": [
            {
                "name": "Melody",
                "notes": [
                    {"pitch": 60, "start_beat": 0, "duration_beats": 1, "velocity": 90}
                ],
            },
            {
                "name": "Violin Solo",
                "notes": [
                    {"pitch": 72, "start_beat": 0, "duration_beats": 1, "velocity": 80}
                ],
            },
        ],
    }
    engine = composition_to_engine(data)
    assert any(t.name == "Violin Solo" for t in engine.tracks)
    apply_track_selection(
        engine,
        include_melody=True,
        include_chords=False,
        include_bass=False,
        include_drums=False,
    )
    violin = next(t for t in engine.tracks if t.name == "Violin Solo")
    assert violin.muted is True
    assert [t.name for t in engine._active_tracks()] == ["Melody"]


# --- H7: lock around create_completion (structural) --------------------


def test_compose_uses_llm_lock_around_completion() -> None:
    """Guard: create_completion must run under _llm_lock (source contract)."""
    import inspect

    from app.features.generation import ai_client

    src = inspect.getsource(ai_client.compose_midi_json)
    assert "with _llm_lock" in src
    assert "create_completion" in src
    # Completion path must be nested inside the lock block in source order
    lock_at = src.index("with _llm_lock")
    call_at = src.index("create_completion")
    assert lock_at < call_at
