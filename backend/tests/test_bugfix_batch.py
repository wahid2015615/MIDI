"""Regression tests for selection/solo, expression/timing defaults, chords cap, notes instrument."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.engine import BARS_MAX, MidiEngine
from app.features.chords_to_midi.schemas import ChordGenerateRequest
from app.features.notes_to_midi.inputs import add_notes_from_lines
from app.shared.midi_response import (
    apply_expression_options,
    apply_track_mix,
    apply_track_selection,
    ensure_exportable,
)
from app.shared.schemas import ExpressionOptions, TimingOptions, TrackMixOptions


def test_selection_clears_solo_so_disabled_role_stays_out() -> None:
    engine = MidiEngine(bpm=120)
    drums = engine.add_track("Drums", "drum_kit")
    melody = engine.add_track("Melody", "acoustic_grand_piano")
    drums.add_note(36, 0, 1)
    melody.add_note(60, 0, 1)

    apply_track_mix(
        engine,
        TrackMixOptions(solo_drums=True, solo_melody=False),
    )
    apply_track_selection(engine, include_drums=False, include_melody=True)

    assert drums.muted is True
    assert drums.solo is False
    assert [t.name for t in engine._active_tracks()] == ["Melody"]
    ensure_exportable(engine)


def test_expression_none_is_noop() -> None:
    engine = MidiEngine(bpm=120)
    track = engine.add_track("Melody", "acoustic_grand_piano")
    track.add_note(60, 0, 4)
    apply_expression_options(engine, None)
    assert track.cc_events == []
    assert track.pitch_bends == []


def test_expression_object_still_applies_defaults() -> None:
    engine = MidiEngine(bpm=120)
    track = engine.add_track("Melody", "acoustic_grand_piano")
    track.add_note(60, 0, 8)
    apply_expression_options(engine, ExpressionOptions())
    assert any(cc.control == 64 for cc in track.cc_events)


def test_empty_timing_does_not_quantize() -> None:
    opts = TimingOptions.model_validate({})
    assert opts.quantize is None

    engine = MidiEngine(bpm=120)
    track = engine.add_track("Melody", "acoustic_grand_piano")
    track.add_note(60, 0.0, 1.3)
    from app.shared.midi_response import apply_timing

    apply_timing(engine, opts, seed=1)
    assert track.notes[0].duration_beats == pytest.approx(1.3)


def test_chord_progression_total_bars_capped() -> None:
    chords = " | ".join(["C"] * 40)
    with pytest.raises(ValidationError, match="maximum is"):
        ChordGenerateRequest(
            progression=chords,
            bars_per_chord=16,
        )
    # Just under the cap should pass
    n = max(1, BARS_MAX // 16)
    ok = ChordGenerateRequest(
        progression=" | ".join(["C"] * n),
        bars_per_chord=16,
    )
    assert ok.bars_per_chord == 16


def test_notes_retarget_instrument_on_repeated_track_directive() -> None:
    engine = MidiEngine(bpm=120)
    add_notes_from_lines(
        engine,
        [
            "@track Melody acoustic_grand_piano",
            "C4 q",
            "@track Melody flute",
            "E4 q",
        ],
    )
    melody = next(t for t in engine.tracks if t.name == "Melody")
    assert melody.instrument == "flute"
    assert len(melody.notes) == 2


def test_notes_bare_track_preserves_custom_instrument() -> None:
    engine = MidiEngine(bpm=120)
    add_notes_from_lines(
        engine,
        [
            "@track Melody flute",
            "C4 q",
            "@track Melody",
            "E4 q",
        ],
    )
    melody = next(t for t in engine.tracks if t.name == "Melody")
    assert melody.instrument == "flute"
    assert len(melody.notes) == 2


def test_custom_notes_track_follows_melody_mixer_solo() -> None:
    engine = MidiEngine(bpm=120)
    add_notes_from_lines(
        engine,
        [
            "@track Melody acoustic_grand_piano",
            "C4 q",
            "@track Violin violin",
            "E4 q",
        ],
    )
    apply_track_mix(
        engine,
        TrackMixOptions(solo_melody=True, mute_melody=False),
    )
    violin = next(t for t in engine.tracks if t.name == "Violin")
    assert violin.solo is True
    assert violin.instrument == "violin"
    names = [t.name for t in engine._active_tracks()]
    assert names == ["Melody", "Violin"]


def test_custom_notes_track_mutes_with_melody() -> None:
    engine = MidiEngine(bpm=120)
    add_notes_from_lines(
        engine,
        [
            "@track Violin violin",
            "E4 q",
        ],
    )
    apply_track_mix(engine, TrackMixOptions(mute_melody=True))
    violin = next(t for t in engine.tracks if t.name == "Violin")
    assert violin.muted is True
    assert engine._active_tracks() == []


def test_drum_and_bass_genre_does_not_enable_drums() -> None:
    from app.features.generation.service import parse_text_prompt_detailed

    result = parse_text_prompt_detailed("make a drum and bass groove at 170 BPM")
    assert result.spec.include_drums is False
    assert result.detected["include_drums"] is False

