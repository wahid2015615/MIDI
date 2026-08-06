"""Verify Studio UI payload fields reach FastAPI schemas + timing/expression apply."""

from __future__ import annotations

from pathlib import Path

import mido
import pytest

from app.core.engine import MidiEngine
from app.features.notes_to_midi.inputs import add_notes_from_lines
from app.features.notes_to_midi.schemas import NotesGenerateRequest
from app.features.text_to_midi.schemas import TextGenerateRequest
from app.shared.midi_response import (
    apply_expression_options,
    apply_score_meta,
    apply_timing,
    apply_track_mix,
)
from app.shared.schemas import ExpressionOptions, TimingOptions, TrackMixOptions


def _studio_text_body() -> dict:
    """Mirrors StudioPage onSubmit → generateFromText JSON keys."""
    swing_mpc = 66
    return {
        "prompt": "Generate a 16-bar uplifting piano melody in C Major at 128 BPM.",
        "bpm": 128,
        "bars": 16,
        "key": "C Major",
        "time_signature": {"numerator": 4, "denominator": 4},
        "mood": "Uplifting",
        "style": "Pop",
        "instrument": "acoustic_grand_piano",
        "tracks": {"melody": True, "chords": True, "bass": True, "drums": True},
        "mix": {
            "mute_melody": False,
            "mute_chords": False,
            "mute_bass": False,
            "mute_drums": False,
            "solo_melody": False,
            "solo_chords": False,
            "solo_bass": False,
            "solo_drums": False,
            "volume_melody": 100,
            "volume_chords": 90,
            "volume_bass": 100,
            "volume_drums": 100,
            "pan_melody": 64,
            "pan_chords": 32,
            "pan_bass": 64,
            "pan_drums": 64,
            "instrument_melody": "acoustic_grand_piano",
            "instrument_chords": "electric_piano_1",
            "instrument_bass": "electric_bass_finger",
            "instrument_drums": "drum_kit",
            "channel_melody": None,
            "channel_chords": None,
            "channel_bass": None,
            "channel_drums": 9,
        },
        # UI: (swingMpc - 50) / 50
        "timing": {
            "quantize": "1/16",
            "quantize_duration": True,
            "swing": max(0, min(1, (swing_mpc - 50) / 50)),
            "swing_grid": "1/8",
            "humanize": True,
            "humanize_timing": 0.02,
            "humanize_velocity": 8,
            "humanize_duration": 0.01,
            "humanize_controllers": False,
            "ppq": 480,
        },
        "expression": {
            "sustain": True,
            "modulation": True,
            "pitch_bend": True,
            "sustain_on_value": 127,
            "sustain_off_value": 0,
            "sustain_hold_ratio": 0.92,
            "modulation_value": 24,
            "modulation_interval_bars": 2.0,
            "modulation_accent_ratio": 0.5,
            "pitch_bend_scoop_depth": 400,
            "pitch_bend_interval_bars": 4.0,
            "pitch_bend_scoop_beats": 0.25,
        },
        "file_type": 1,
        "filename": "ui_wire_test.mid",
        "seed": 42,
    }


def test_studio_text_payload_parses_all_ui_fields() -> None:
    body = _studio_text_body()
    req = TextGenerateRequest.model_validate(body)

    assert req.bpm == 128
    assert req.bars == 16
    assert req.key == "C Major"
    assert req.mood == "Uplifting"
    assert req.style == "Pop"
    assert req.instrument == "acoustic_grand_piano"
    assert req.tracks is not None and req.tracks.drums is True
    assert req.time_signature is not None
    assert req.time_signature.as_tuple() == (4, 4)

    assert req.mix is not None
    assert req.mix.pan_chords == 32
    assert req.mix.volume_chords == 90
    assert req.mix.instrument_melody == "acoustic_grand_piano"
    assert req.mix.channel_drums == 9

    assert req.timing is not None
    assert req.timing.quantize == "1/16"
    assert req.timing.swing == pytest.approx(0.32)  # (66-50)/50
    assert req.timing.swing_grid == "1/8"
    assert req.timing.humanize is True
    assert req.timing.humanize_timing == 0.02
    assert req.timing.ppq == 480

    assert req.expression is not None
    assert req.expression.sustain is True
    assert req.expression.modulation is True
    assert req.expression.pitch_bend is True
    assert req.expression.modulation_value == 24
    assert req.expression.sustain_hold_ratio == 0.92


def test_studio_timing_expression_apply_to_midi(tmp_path: Path) -> None:
    """Notes mode: prove mix/timing/expression from UI-shaped body hit the .mid."""
    # Include off-beat eighths so swing=0.33 has something to shift
    lines = [
        "@track Melody acoustic_grand_piano",
    ]
    # 8 bars of eighth notes: on + off beats
    for i in range(64):
        lines.append(f"{'E' if i % 2 else 'C'}4 e")
    lines.extend(
        [
            "@track Chords electric_piano_1",
            "C4 w",
            "E4 w",
            "G4 w",
            "C5 w",
            "F4 w",
            "A4 w",
            "C5 w",
            "F5 w",
        ]
    )
    body = {
        "notes": lines,
        "bpm": 100,
        "key": "C Major",
        "time_signature": {"numerator": 4, "denominator": 4},
        "instrument": "acoustic_grand_piano",
        "mix": {
            "volume_melody": 111,
            "volume_chords": 77,
            "pan_melody": 20,
            "pan_chords": 100,
            "instrument_melody": "acoustic_grand_piano",
            "instrument_chords": "electric_piano_1",
        },
        "timing": {
            "quantize": "1/16",
            "quantize_duration": True,
            "swing": 0.33,
            "swing_grid": "1/8",
            "humanize": False,
            "ppq": 480,
        },
        "expression": {
            "sustain": True,
            "modulation": True,
            "pitch_bend": True,
            "modulation_value": 40,
            "modulation_interval_bars": 1.0,
            "modulation_accent_ratio": 0.25,
            "pitch_bend_scoop_depth": 400,
            "pitch_bend_interval_bars": 1.0,
            "pitch_bend_scoop_beats": 0.25,
        },
        "file_type": 1,
        "filename": "ui_apply_proof.mid",
        "seed": 7,
    }
    req = NotesGenerateRequest.model_validate(body)

    engine = MidiEngine(bpm=req.bpm, time_signature=(4, 4))
    add_notes_from_lines(engine, req.notes, instrument=req.instrument)
    apply_score_meta(engine, time_signature=req.time_signature, key=req.key)
    apply_track_mix(engine, req.mix)
    apply_expression_options(engine, req.expression)
    apply_timing(engine, req.timing, seed=req.seed)

    melody = next(t for t in engine.tracks if t.name.lower() == "melody")
    chords = next(t for t in engine.tracks if t.name.lower() == "chords")

    assert melody.volume == 111
    assert chords.volume == 77
    assert melody.pan == 20
    assert chords.pan == 100

    # Sustain + mod from expression options
    assert any(cc.control == 64 and cc.value == 127 for cc in melody.cc_events)
    mod_peaks = [cc for cc in melody.cc_events if cc.control == 1 and cc.value == 40]
    assert mod_peaks, "UI modulation_value=40 must land as CC1 peaks"

    # Swing must move some off-beats (with 1/8 grid + 0.33 delay)
    offbeat_starts = [n.start_beat for n in melody.notes if abs((n.start_beat % 1.0) - 0.5) < 1e-6]
    # After swing, classic 0.5 eighths shift later — check not all remain exactly 0.5
    swung = [
        n.start_beat
        for n in melody.notes
        if 0.5 < (n.start_beat % 1.0) < 0.95
    ]
    assert swung, "UI swing=0.33 must shift off-beat note starts"

    out = tmp_path / "ui_apply_proof.mid"
    # Export path used by API
    engine.export(out, file_type=1)
    mid = mido.MidiFile(out)
    assert mid.type == 1
    assert mid.ticks_per_beat == 480

    # Volume CC7 written on export from mix
    found_vol_111 = False
    found_mod_40 = False
    found_sus = False
    for track in mid.tracks:
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            if msg.type == "control_change":
                if msg.control == 7 and msg.value == 111:
                    found_vol_111 = True
                if msg.control == 1 and msg.value == 40:
                    found_mod_40 = True
                if msg.control == 64 and msg.value == 127:
                    found_sus = True
    assert found_vol_111
    assert found_mod_40
    assert found_sus


def test_timing_options_reject_unknown_but_accept_studio_defaults() -> None:
    TimingOptions.model_validate(
        {
            "quantize": "1/16",
            "swing": 0.0,
            "swing_grid": "1/8",
            "humanize": False,
            "ppq": 480,
        }
    )
    ExpressionOptions.model_validate(
        {"sustain": True, "modulation": True, "pitch_bend": True}
    )
    TrackMixOptions.model_validate(
        {"volume_melody": 100, "pan_melody": 64, "instrument_melody": "acoustic_grand_piano"}
    )
