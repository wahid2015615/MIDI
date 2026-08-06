"""End-to-end: UI-shaped payload → score meta / mix / MIDI bytes."""

from __future__ import annotations

from pathlib import Path

from mido import MidiFile

from app.core.engine import MidiEngine
from app.core.instruments import get_program
from app.features.generation.composer import composition_to_engine, key_signature_token
from app.features.notes_to_midi.inputs import add_notes_from_lines
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


def _ui_pipeline_notes(tmp_path: Path) -> tuple[MidiFile, MidiEngine]:
    """Simulate Studio notes submit with explicit UI fields."""
    engine = MidiEngine(bpm=120, time_signature=(4, 4), key_signature="C")
    lines = [
        "@track Melody acoustic_grand_piano",
        "C4 quarter",
        "E4 quarter",
        "@track Chords electric_piano_1",
        "C3 whole",
        "@track Bass electric_bass_finger",
        "C2 half",
        "@track Drums drum_kit",
        "C2 quarter",
    ]
    add_notes_from_lines(engine, lines)

    apply_score_meta(
        engine,
        time_signature=TimeSignatureOptions(numerator=3, denominator=4),
        key="A Minor",
    )
    engine.bpm = 96
    apply_track_mix(
        engine,
        TrackMixOptions(
            volume_melody=110,
            volume_chords=80,
            volume_bass=100,
            pan_melody=20,
            pan_bass=100,
            instrument_melody="violin",
            instrument_chords="electric_piano_1",
            instrument_bass="electric_bass_finger",
            channel_melody=0,
            channel_chords=1,
            channel_bass=2,
            channel_drums=9,
        ),
    )
    # UI asked for melody+chords+bass only (no drums)
    apply_track_selection(
        engine,
        include_melody=True,
        include_chords=True,
        include_bass=True,
        include_drums=False,
    )
    apply_expression_options(
        engine,
        ExpressionOptions(sustain=True, modulation=True, pitch_bend=True),
    )
    apply_timing(
        engine,
        TimingOptions(
            quantize=None,
            swing=0,
            humanize=False,
            ppq=480,
        ),
        seed=1,
    )

    path = tmp_path / "ui_notes.mid"
    engine.export(path, file_type=1)
    return MidiFile(path), engine


def test_ui_payload_reaches_midi_file(tmp_path: Path) -> None:
    mid, engine = _ui_pipeline_notes(tmp_path)

    assert engine.bpm == 96
    assert engine.time_signature == (3, 4)
    assert engine.key_signature == "Am"
    assert [t.name for t in engine._active_tracks()] == ["Melody", "Chords", "Bass"]

    names = [t.name for t in mid.tracks]
    assert names == ["Conductor", "Melody", "Chords", "Bass"]

    conductor = mid.tracks[0]
    assert any(
        m.type == "time_signature" and m.numerator == 3 and m.denominator == 4
        for m in conductor
    )
    assert any(m.type == "key_signature" and m.key == "Am" for m in conductor)
    assert any(m.type == "set_tempo" for m in conductor)

    melody = mid.tracks[1]
    # SMF Type 1 default: tempo map on Conductor only
    assert not any(m.type == "set_tempo" for m in melody)
    assert not any(m.type == "time_signature" for m in melody)
    assert any(
        m.type == "program_change" and m.program == get_program("violin")
        for m in melody
    )
    assert any(
        m.type == "control_change" and m.control == 7 and m.value == 110 for m in melody
    )
    assert any(
        m.type == "control_change" and m.control == 10 and m.value == 20 for m in melody
    )

    # Drums were in the input but muted by track selection → not exported
    assert "Drums" not in names


def test_ui_track_selection_mutes_unrequested_ai_tracks(tmp_path: Path) -> None:
    data = {
        "bpm": 128,
        "key": "C Major",
        "time_signature": [4, 4],
        "tracks": [
            {
                "name": "Melody",
                "notes": [
                    {"pitch": 60, "start_beat": 0, "duration_beats": 1, "velocity": 90}
                ],
            },
            {
                "name": "Chords",
                "notes": [
                    {"pitch": 64, "start_beat": 0, "duration_beats": 2, "velocity": 70}
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
    # UI: only melody + bass
    apply_track_selection(
        engine,
        include_melody=True,
        include_chords=False,
        include_bass=True,
        include_drums=False,
    )
    path = tmp_path / "sel.mid"
    engine.export(path, file_type=1)
    names = [t.name for t in MidiFile(path).tracks]
    assert names == ["Conductor", "Melody", "Bass"]
    assert key_signature_token("C Major") == "C"
