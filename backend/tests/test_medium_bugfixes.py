"""Regression tests for medium-severity correctness bugs."""

from __future__ import annotations

import pytest

from app.core.engine import MidiEngine, clamp_bpm
from app.core.theory import parse_chord_symbol
from app.features.chords_to_midi.inputs import (
    parse_progression_string,
    validate_progression_chords,
)
from app.features.generation.composer import _pitch_to_midi, composition_to_engine
from app.features.generation.service import parse_text_prompt
from app.features.notes_to_midi.schemas import NotesGenerateRequest
from pydantic import ValidationError


def test_electric_piano_beats_piano_substring() -> None:
    spec = parse_text_prompt("uplifting electric piano melody")
    assert spec.instrument == "electric_piano_1"
    spec2 = parse_text_prompt("soft piano ballad")
    assert spec2.instrument == "acoustic_grand_piano"


def test_float_pitch_rejected() -> None:
    with pytest.raises(ValueError, match="integer"):
        _pitch_to_midi(60.9)


def test_invalid_chords_rejected() -> None:
    chords = parse_progression_string("C - Foo - Xxx")
    with pytest.raises(ValueError, match="Invalid chord"):
        validate_progression_chords(chords)
    parse_chord_symbol("Csus4")  # supported
    with pytest.raises(ValueError):
        parse_chord_symbol("Csus9xyz")


def test_v2_v3_chord_symbols() -> None:
    # V2
    assert parse_chord_symbol("C5") == [48, 55]
    assert len(parse_chord_symbol("Cadd9")) == 4
    assert len(parse_chord_symbol("C6")) == 4
    assert len(parse_chord_symbol("Am6")) == 4
    assert len(parse_chord_symbol("G9")) == 5
    assert len(parse_chord_symbol("Am9")) == 5
    assert len(parse_chord_symbol("Cmaj9")) == 5
    assert len(parse_chord_symbol("Bdim7")) == 4
    assert len(parse_chord_symbol("Bm7b5")) == 4
    assert len(parse_chord_symbol("Bø")) == 4
    assert len(parse_chord_symbol("G7sus4")) == 4
    # Slash bass
    slash = parse_chord_symbol("C/G")
    assert slash[0] % 12 == 7  # G bass
    assert {p % 12 for p in slash} == {0, 4, 7}  # C major over G
    assert len(slash) == 3  # bass + remaining triad tones
    # V3
    assert len(parse_chord_symbol("C11")) == 6
    assert len(parse_chord_symbol("D13")) == 6
    assert len(parse_chord_symbol("G7b9")) == 5
    assert len(parse_chord_symbol("G7#9")) == 5
    assert len(parse_chord_symbol("G7alt")) == 6
    assert len(parse_chord_symbol("Cadd2")) == 4
    # Progression acceptance
    validate_progression_chords(
        parse_progression_string("Cmaj9 | Am7/E | Bm7b5 | G7b9")
    )

def test_composer_rejects_10pct_invalid() -> None:
    notes = [
        {"pitch": 60, "start_beat": i, "duration_beats": 1, "velocity": 90}
        for i in range(8)
    ]
    notes.append({"pitch": 999, "start_beat": 8, "duration_beats": 1, "velocity": 90})
    notes.append({"pitch": -1, "start_beat": 9, "duration_beats": 1, "velocity": 90})
    data = {
        "bpm": 120,
        "tracks": [{"name": "Melody", "notes": notes}],
    }
    with pytest.raises(ValueError, match="incomplete"):
        composition_to_engine(data)


def test_tick_overlap_clamped_after_rounding() -> None:
    engine = MidiEngine(bpm=120, ppq=480)
    track = engine.add_track("Melody")
    # Beat-space legato leaves end ≈ next start; independent rounding can overlap
    track.add_note(60, 0.0, 1.0 / 3.0)
    track.add_note(60, 1.0 / 3.0, 1.0)
    events = engine._events_for_tracks([track])
    ons = [
        (t, m)
        for t, m in events
        if getattr(m, "type", None) == "note_on" and getattr(m, "velocity", 0) > 0
    ]
    offs = [
        (t, m)
        for t, m in events
        if getattr(m, "type", None) == "note_off"
        or (getattr(m, "type", None) == "note_on" and getattr(m, "velocity", 0) == 0)
    ]
    pitch_offs = sorted(t for t, m in offs if m.note == 60)
    pitch_ons = sorted(t for t, m in ons if m.note == 60)
    assert len(pitch_ons) == 2
    assert pitch_offs[0] <= pitch_ons[1]


def test_clamp_bpm_cleared_is_120() -> None:
    assert clamp_bpm(0) == 120.0


def test_no_bass_does_not_set_bass_instrument() -> None:
    from app.features.generation.service import parse_text_prompt_detailed

    no_bass = parse_text_prompt_detailed("melody with no bass")
    assert no_bass.spec.include_bass is False
    assert no_bass.spec.instrument != "electric_bass_finger"
    assert no_bass.detected["instrument"] is False

    without = parse_text_prompt_detailed("piano without bass")
    assert without.spec.include_bass is False
    assert without.spec.instrument == "acoustic_grand_piano"

    bassline = parse_text_prompt_detailed("catchy bassline over piano chords")
    assert bassline.spec.instrument == "acoustic_grand_piano"

    bass_inst = parse_text_prompt("funky bass guitar groove")
    assert bass_inst.instrument == "electric_bass_finger"


def test_bare_rest_r_advances_cursor() -> None:
    from app.features.notes_to_midi.inputs import add_notes_from_lines

    engine = MidiEngine(bpm=120)
    track = add_notes_from_lines(engine, ["C4 q", "r", "E4 q"])
    assert len(track.notes) == 2
    assert track.notes[0].start_beat == 0.0
    # bare `r` = one quarter rest
    assert track.notes[1].start_beat == pytest.approx(2.0)


def test_rest_only_notes_schema_rejects() -> None:
    with pytest.raises(ValidationError, match="playable"):
        NotesGenerateRequest(notes=["@track Melody", "rest q", "rest h"])
    # bare r alone (no playable notes) also rejected by schema
    with pytest.raises(ValidationError, match="playable"):
        NotesGenerateRequest(notes=["r", "r"])
    # mixed notes + bare r accepted at schema level
    NotesGenerateRequest(notes=["C4 q", "r", "E4 q"])
