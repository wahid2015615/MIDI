"""Regression tests for the final audit bugfix batch."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.engine import MidiEngine, NoteEvent, require_finite_beat
from app.core.expression import apply_expression
from app.core.theory import parse_duration
from app.features.chords_to_midi.inputs import parse_progression_string
from app.features.chords_to_midi.schemas import ChordGenerateRequest
from app.features.generation.ai_client import (
    begin_generation,
    end_generation,
    request_generation_cancel,
)
from app.features.notes_to_midi.inputs import add_notes_from_lines
from app.features.notes_to_midi.schemas import NotesGenerateRequest
from app.features.text_to_midi.schemas import TextGenerateRequest
from app.shared.schemas import ExpressionOptions, TrackOptions


def test_note_event_rejects_non_finite_duration() -> None:
    with pytest.raises(ValueError, match="finite"):
        NoteEvent(60, 0.0, float("inf"))
    with pytest.raises(ValueError, match="finite"):
        NoteEvent(60, 0.0, float("nan"))
    with pytest.raises(ValueError, match="duration"):
        require_finite_beat(1e309, name="duration", allow_zero=False)


def test_parse_duration_rejects_huge_numeric() -> None:
    with pytest.raises(ValueError):
        parse_duration("1e309")
    with pytest.raises(ValueError):
        parse_duration("inf")


def test_notes_rejects_infinite_duration_at_parse() -> None:
    engine = MidiEngine()
    with pytest.raises(ValueError):
        add_notes_from_lines(engine, ["C4 1e309"])


def test_notes_instrument_overwrite_validates() -> None:
    engine = MidiEngine()
    with pytest.raises(ValueError, match="Unknown instrument"):
        add_notes_from_lines(
            engine,
            [
                "@track Melody acoustic_grand_piano",
                "C4 q",
                "@track Melody not_a_real_synth",
                "E4 q",
            ],
        )


def test_notes_multiword_track_name_parses_instrument_suffix() -> None:
    engine = MidiEngine()
    add_notes_from_lines(
        engine,
        [
            # "Electric Bass" tokens map to mixer Bass; flute is the instrument.
            "@track Electric Bass flute",
            "C3 q",
            "@track Celesta",
            "E4 q",
        ],
    )
    by_name = {t.name: t for t in engine.tracks}
    assert by_name["Bass"].instrument == "flute"
    assert "Celesta" in by_name
    assert by_name["Celesta"].instrument == "acoustic_grand_piano"


def test_partial_tracks_object_defaults_omitted_to_false() -> None:
    opts = TrackOptions.model_validate({"melody": True})
    assert opts.melody is True
    assert opts.chords is False
    assert opts.bass is False
    assert opts.drums is False


def test_http_bpm_zero_coerces_to_120() -> None:
    notes = NotesGenerateRequest(notes=["C4 q"], bpm=0)
    assert notes.bpm == 120.0
    chords = ChordGenerateRequest(progression="C | G", bpm=0)
    assert chords.bpm == 120.0
    text = TextGenerateRequest(prompt="happy piano", bpm=0)
    assert text.bpm == 120.0


def test_mixed_progression_separators() -> None:
    assert parse_progression_string("C | G - Am | F") == ["C", "G", "Am", "F"]


def test_expression_sustain_on_off_must_differ() -> None:
    with pytest.raises(ValidationError, match="sustain_on_value"):
        ExpressionOptions(sustain=True, sustain_on_value=64, sustain_off_value=64)


def test_invalid_key_raises_on_export(tmp_path: Path) -> None:
    engine = MidiEngine(key_signature="NotAKey")
    engine.add_track("Melody").add_note(60, 0, 1)
    with pytest.raises(ValueError, match="Unsupported key"):
        engine.export(tmp_path / "bad_key.mid")


def test_ppq_zero_rejected() -> None:
    with pytest.raises(ValueError, match="ppq"):
        MidiEngine(ppq=0)


def test_cancel_is_scoped_to_client_request_id() -> None:
    a = begin_generation("req-a")
    b = begin_generation("req-b")
    request_generation_cancel("req-a")
    from app.features.generation import ai_client

    assert ai_client._generation_cancelled[a] is True
    assert ai_client._generation_cancelled[b] is False
    end_generation(a, "req-a")
    end_generation(b, "req-b")


def test_expression_guards_finite_end() -> None:
    engine = MidiEngine()
    track = engine.add_track("Melody")
    track.add_note(60, 0, 1)
    # Should not hang
    apply_expression(engine, sustain=True, modulation=True, pitch_bend=True)
    assert any(cc.control == 64 for cc in track.cc_events)


def test_notes_duration_math_is_finite() -> None:
    assert math.isfinite(parse_duration("q"))
    assert parse_duration("half") == 2.0
