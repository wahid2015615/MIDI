"""Chords + Notes mode: UI payload → MIDI correctness."""

from __future__ import annotations

from pathlib import Path

import pytest
from mido import MidiFile
from pydantic import ValidationError

from app.core.engine import MidiEngine
from app.core.instruments import get_program
from app.features.chords_to_midi.inputs import parse_progression_string
from app.features.chords_to_midi.schemas import ChordGenerateRequest
from app.features.generation.composer import composition_to_engine
from app.features.notes_to_midi.inputs import add_notes_from_lines
from app.features.notes_to_midi.schemas import NotesGenerateRequest
from app.shared.midi_response import (
    apply_expression_options,
    apply_score_meta,
    apply_timing,
    apply_track_mix,
    apply_track_selection,
)
from app.shared.schemas import (
    ExpressionOptions,
    TimeSignatureOptions,
    TimingOptions,
    TrackMixOptions,
)


def test_parse_progression_variants() -> None:
    assert parse_progression_string("C | G | Am | F") == ["C", "G", "Am", "F"]
    assert parse_progression_string("| C | G | Am | F |") == ["C", "G", "Am", "F"]
    assert parse_progression_string("C - G - Am - F") == ["C", "G", "Am", "F"]
    assert parse_progression_string("C, G, Am, F") == ["C", "G", "Am", "F"]
    assert parse_progression_string("C → G → Am") == ["C", "G", "Am"]
    assert parse_progression_string("C -> G -> Am") == ["C", "G", "Am"]
    assert parse_progression_string("C G Am F") == ["C", "G", "Am", "F"]
    assert parse_progression_string("C\nG\nAm\nF") == ["C", "G", "Am", "F"]
    assert parse_progression_string("   ") == []


def test_chord_request_rejects_empty_progression() -> None:
    with pytest.raises(ValidationError):
        ChordGenerateRequest(progression="   -   ,  ")
    with pytest.raises(ValidationError):
        ChordGenerateRequest(progression="")
    ChordGenerateRequest(progression="C - Am")


def test_notes_request_rejects_blank_list() -> None:
    with pytest.raises(ValidationError):
        NotesGenerateRequest(notes=["", "  ", "# comment only"])
    NotesGenerateRequest(notes=["C4 quarter"])


def test_notes_canonical_track_names_and_mixer(tmp_path: Path) -> None:
    engine = MidiEngine(bpm=100)
    add_notes_from_lines(
        engine,
        [
            "@track lead acoustic_grand_piano",
            "C4 quarter",
            "@track harmony electric_piano_1",
            "E3 half",
            "@track bass electric_bass_finger",
            "C2 half",
        ],
    )
    assert [t.name for t in engine.tracks] == ["Melody", "Chords", "Bass"]

    apply_score_meta(
        engine,
        time_signature=TimeSignatureOptions(numerator=6, denominator=8),
        key="E Minor",
    )
    engine.bpm = 110
    apply_track_mix(
        engine,
        TrackMixOptions(
            volume_melody=105,
            instrument_melody="violin",
            mute_chords=True,
            channel_bass=3,
        ),
    )
    apply_expression_options(engine, ExpressionOptions(sustain=False, modulation=False))
    apply_timing(engine, TimingOptions(quantize=None, humanize=False, ppq=480), seed=1)

    path = tmp_path / "notes_mode.mid"
    engine.export(path, file_type=1)
    mid = MidiFile(path)
    names = [t.name for t in mid.tracks]
    # Chords muted → not exported
    assert names == ["Conductor", "Melody", "Bass"]

    conductor = mid.tracks[0]
    assert any(m.type == "time_signature" and m.numerator == 6 for m in conductor)
    assert any(m.type == "key_signature" and m.key == "Em" for m in conductor)

    melody = mid.tracks[1]
    # SMF default: score meta lives on Conductor only
    assert not any(m.type == "set_tempo" for m in melody)
    assert any(
        m.type == "program_change" and m.program == get_program("violin") for m in melody
    )
    assert any(
        m.type == "control_change" and m.control == 7 and m.value == 105 for m in melody
    )


def test_notes_empty_raises() -> None:
    engine = MidiEngine(bpm=120)
    with pytest.raises(ValueError, match="No playable notes"):
        add_notes_from_lines(engine, ["@track Melody", "rest quarter"])


def test_same_line_chord_shares_beat() -> None:
    engine = MidiEngine(bpm=120)
    track = add_notes_from_lines(
        engine,
        ["C4 E4 G4 q", "C5 q 80"],
    )
    assert len(track.notes) == 4
    chord = track.notes[:3]
    assert all(n.start_beat == 0.0 for n in chord)
    assert all(n.duration_beats == 1.0 for n in chord)
    assert {n.pitch for n in chord} == {60, 64, 67}
    assert track.notes[3].start_beat == 1.0
    assert track.notes[3].velocity == 80


def test_same_line_chord_with_half_note_velocity() -> None:
    from app.features.notes_to_midi.inputs import parse_note_event_line

    pitches, dur, vel = parse_note_event_line("C4 E4 G4 half note 90")
    assert pitches == ["C4", "E4", "G4"]
    assert dur == "half note"
    assert vel == 90


def test_exact_chords_progression_pitch_classes() -> None:
    """Chords mode must emit real symbol tones (no AI drift)."""
    from app.features.generation.service import generate_from_chords

    progression = (
        "| Am7 | Dm7 | G7 | Cmaj7 | Fmaj7 | Bm7b5 | E7b9 | Am7 | F | G | Em7 | Am |"
    )
    engine = generate_from_chords(
        progression,
        bpm=100,
        bars_per_chord=1.0,
        add_chords=True,
        add_melody=False,
        add_bass=False,
        add_drums=False,
    )
    chords_track = next(t for t in engine.tracks if t.name == "Chords")
    expected = [
        {9, 0, 4, 7},   # Am7
        {2, 5, 9, 0},   # Dm7
        {7, 11, 2, 5},  # G7
        {0, 4, 7, 11},  # Cmaj7
        {5, 9, 0, 4},   # Fmaj7
        {11, 2, 5, 9},  # Bm7b5
        {4, 8, 11, 2, 5},  # E7b9 includes G#=8
        {9, 0, 4, 7},   # Am7
        {5, 9, 0},      # F
        {7, 11, 2},     # G
        {4, 7, 11, 2},  # Em7
        {9, 0, 4},      # Am
    ]
    by_start: dict[float, set[int]] = {}
    for n in chords_track.notes:
        by_start.setdefault(n.start_beat, set()).add(n.pitch % 12)
    starts = sorted(by_start)
    assert len(starts) == 12
    for start, pcs in zip(starts, expected):
        assert by_start[start] == pcs, f"beat {start}: {by_start[start]} != {pcs}"
    # E7b9 must include G#
    assert 8 in by_start[starts[6]]


def test_chords_selection_pipeline(tmp_path: Path) -> None:
    """Simulate AI chords JSON + UI add_melody/bass/drums flags."""
    data = {
        "bpm": 120,
        "key": "C Major",
        "time_signature": [4, 4],
        "tracks": [
            {
                "name": "Chords",
                "instrument": "electric_piano_1",
                "notes": [
                    {"pitch": 60, "start_beat": 0, "duration_beats": 4, "velocity": 70},
                    {"pitch": 64, "start_beat": 0, "duration_beats": 4, "velocity": 70},
                ],
            },
            {
                "name": "Melody",
                "notes": [
                    {"pitch": 72, "start_beat": 0, "duration_beats": 1, "velocity": 90}
                ],
            },
            {
                "name": "Bass",
                "notes": [
                    {"pitch": 36, "start_beat": 0, "duration_beats": 2, "velocity": 100}
                ],
            },
            {
                "name": "Drums",
                "instrument": "drum_kit",
                "notes": [
                    {"pitch": 36, "start_beat": 0, "duration_beats": 0.5, "velocity": 110}
                ],
            },
        ],
    }
    engine = composition_to_engine(data)
    apply_score_meta(
        engine,
        time_signature=TimeSignatureOptions(numerator=4, denominator=4),
        key="C Major",
    )
    apply_track_mix(
        engine,
        TrackMixOptions(
            volume_chords=85,
            instrument_chords="electric_piano_1",
            instrument_melody="flute",
        ),
    )
    # UI: melody on, bass off, drums off (chords always on)
    apply_track_selection(
        engine,
        include_melody=True,
        include_chords=True,
        include_bass=False,
        include_drums=False,
    )
    apply_expression_options(engine, ExpressionOptions())
    apply_timing(engine, TimingOptions(quantize="1/16", humanize=False, ppq=480), seed=2)

    path = tmp_path / "chords_mode.mid"
    engine.export(path, file_type=1)
    names = [t.name for t in MidiFile(path).tracks]
    assert names == ["Conductor", "Chords", "Melody"]
    melody = next(t for t in MidiFile(path).tracks if t.name == "Melody")
    assert any(
        m.type == "program_change" and m.program == get_program("flute") for m in melody
    )
