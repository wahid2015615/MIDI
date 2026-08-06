"""Regression tests for empty export, instruments, channels, expression, chords."""

from __future__ import annotations

from pathlib import Path

import pytest
from mido import MidiFile

from app.core.engine import MidiEngine
from app.core.expression import apply_expression
from app.core.instruments import get_program
from app.features.generation.composer import composition_to_engine
from app.features.generation.prompts import build_chords_user_prompt, build_text_user_prompt
from app.shared.midi_response import (
    apply_track_mix,
    apply_track_selection,
    ensure_exportable,
)
from app.shared.schemas import TrackMixOptions


def test_ensure_exportable_rejects_all_muted() -> None:
    engine = MidiEngine(bpm=120)
    t = engine.add_track("Melody", "acoustic_grand_piano")
    t.add_note(60, 0, 1)
    t.muted = True
    with pytest.raises(ValueError, match="muted or empty"):
        ensure_exportable(engine)


def test_unknown_instrument_raises_not_piano() -> None:
    with pytest.raises(ValueError, match="Unknown instrument"):
        get_program("rhodes")
    with pytest.raises(ValueError, match="Unknown instrument"):
        MidiEngine().add_track("Melody", "rhodes")
    # Silent piano fallback path must stay removed
    engine = MidiEngine(bpm=120)
    track = engine.add_track("Melody", "acoustic_grand_piano")
    track.instrument = "not_a_real_synth"
    track.add_note(60, 0, 1)
    with pytest.raises(ValueError, match="Unknown instrument"):
        engine.resolve_export_channels()


def test_melodic_channel_9_remapped() -> None:
    engine = MidiEngine(bpm=120)
    mel = engine.add_track("Melody", "acoustic_grand_piano", channel=9)
    assert mel.channel != 9
    bass = engine.add_track("Bass", "electric_bass_finger", channel=9)
    assert bass.channel != 9
    assert bass.channel != mel.channel
    drums = engine.add_track("Drums", "drum_kit", channel=0)
    assert drums.channel == 9


def test_export_resolves_channel_collisions() -> None:
    engine = MidiEngine(bpm=120)
    a = engine.add_track("Melody", "acoustic_grand_piano", channel=1)
    b = engine.add_track("Bass", "electric_bass_finger", channel=1)
    a.add_note(60, 0, 1)
    b.add_note(36, 0, 1)
    engine.resolve_export_channels()
    assert a.channel != b.channel
    assert a.channel != 9 and b.channel != 9


def test_duration_and_expression_ignore_muted() -> None:
    engine = MidiEngine(bpm=120)
    short = engine.add_track("Melody", "acoustic_grand_piano")
    short.add_note(60, 0, 1)
    long_drums = engine.add_track("Drums", "drum_kit")
    long_drums.add_note(36, 0, 32)
    apply_track_selection(engine, include_drums=False)
    assert engine.duration_beats(active_only=True) == pytest.approx(1.0)
    assert engine.duration_beats(active_only=False) == pytest.approx(32.0)
    apply_expression(engine, sustain=True, modulation=False, pitch_bend=False)
    # Expression must not be written onto muted drums
    assert not any(cc.control == 64 for cc in long_drums.cc_events)
    # Sustain on melody should span the active (short) duration, not muted drums
    sustain_offs = [cc.time_beat for cc in short.cc_events if cc.control == 64 and cc.value == 0]
    assert sustain_offs
    assert max(sustain_offs) <= 5.0


def test_text_prompt_rejects_empty_roles() -> None:
    with pytest.raises(ValueError, match="at least one track"):
        build_text_user_prompt(
            prompt="x",
            bpm=120,
            bars=4,
            key="C",
            mood="happy",
            style="pop",
            instrument="acoustic_grand_piano",
            include_melody=False,
            include_chords=False,
            include_bass=False,
            include_drums=False,
        )


def test_chords_prompt_honors_include_chords_off() -> None:
    prompt = build_chords_user_prompt(
        chords=["C", "G"],
        bpm=100,
        bars_per_chord=1,
        key="C Major",
        melody_instrument="flute",
        include_chords=False,
        include_melody=True,
        include_bass=False,
        include_drums=False,
    )
    assert "Required tracks: Melody" in prompt
    assert "Chords instrument" not in prompt


def test_mix_rejects_unknown_instrument() -> None:
    engine = MidiEngine(bpm=120)
    engine.add_track("Melody", "acoustic_grand_piano").add_note(60, 0, 1)
    with pytest.raises(ValueError, match="Unknown instrument"):
        apply_track_mix(engine, TrackMixOptions(instrument_melody="rhodes"))


def test_multi_solo_keeps_all_soloed_tracks(tmp_path: Path) -> None:
    """Multiple Solo flags must export together — not only the first match."""
    data = {
        "bpm": 120,
        "tracks": [
            {
                "name": "Melody",
                "instrument": "acoustic_grand_piano",
                "notes": [
                    {"pitch": 72, "start_beat": 0, "duration_beats": 1, "velocity": 90}
                ],
            },
            {
                # Drifted AI label — must still bind to Chords mixer solo
                "name": "Pads",
                "instrument": "electric_piano_1",
                "notes": [
                    {"pitch": 60, "start_beat": 0, "duration_beats": 2, "velocity": 70}
                ],
            },
            {
                # Compound name must map to Bass
                "name": "Bassline",
                "instrument": "electric_bass_finger",
                "notes": [
                    {"pitch": 36, "start_beat": 0, "duration_beats": 1, "velocity": 80}
                ],
            },
            {
                "name": "Percussion",
                "instrument": "drum_kit",
                "notes": [
                    {"pitch": 36, "start_beat": 0, "duration_beats": 0.5, "velocity": 100}
                ],
            },
        ],
    }
    engine = composition_to_engine(data)
    assert [t.name for t in engine.tracks] == ["Melody", "Chords", "Bass", "Drums"]

    apply_track_mix(
        engine,
        TrackMixOptions(
            solo_melody=True,
            solo_chords=True,
            solo_bass=True,
            solo_drums=False,
        ),
    )
    assert [t.name for t in engine._active_tracks()] == ["Melody", "Chords", "Bass"]

    path = tmp_path / "multi_solo.mid"
    engine.export(path, file_type=1)
    mid = MidiFile(path)
    assert [t.name for t in mid.tracks] == ["Conductor", "Melody", "Chords", "Bass"]


def test_solo_overrides_mute() -> None:
    engine = MidiEngine(bpm=120)
    a = engine.add_track("Melody", "acoustic_grand_piano")
    b = engine.add_track("Chords", "electric_piano_1")
    a.add_note(60, 0, 1)
    b.add_note(64, 0, 1)
    apply_track_mix(
        engine,
        TrackMixOptions(
            mute_melody=True,
            mute_chords=True,
            solo_melody=True,
            solo_chords=True,
        ),
    )
    assert [t.name for t in engine._active_tracks()] == ["Melody", "Chords"]


def test_expression_respects_custom_values() -> None:
    from app.core.expression import apply_expression

    engine = MidiEngine(bpm=120, time_signature=(4, 4))
    melody = engine.add_track("Melody", "lead_1_square")
    melody.add_note(60, 0, 8)  # 2 bars
    apply_expression(
        engine,
        sustain=True,
        modulation=True,
        pitch_bend=True,
        sustain_on_value=100,
        sustain_off_value=10,
        sustain_hold_ratio=0.5,
        modulation_value=64,
        modulation_interval_bars=1.0,
        modulation_accent_ratio=0.25,
        pitch_bend_scoop_depth=800,
        pitch_bend_interval_bars=1.0,
        pitch_bend_scoop_beats=0.5,
    )
    sus_on = [cc for cc in melody.cc_events if cc.control == 64 and cc.value == 100]
    sus_off = [cc for cc in melody.cc_events if cc.control == 64 and cc.value == 10]
    assert sus_on and sus_off
    # Hold ratio 0.5 → off at beat 2 in 4/4 (bar = 4 beats)
    assert any(abs(cc.time_beat - 2.0) < 1e-6 for cc in sus_off)

    mod_peaks = [cc for cc in melody.cc_events if cc.control == 1 and cc.value == 64]
    assert mod_peaks

    scoop = [pb for pb in melody.pitch_bends if pb.value == 8192 - 800]
    assert scoop


def test_mpc_swing_maps_triplet() -> None:
    from app.core.timing import apply_swing, mpc_swing_to_delay

    assert mpc_swing_to_delay(0.5) == 0.0
    assert mpc_swing_to_delay(50) == 0.0  # raw percent accidentally
    delay = mpc_swing_to_delay(2 / 3)
    assert delay == pytest.approx(1 / 3, rel=1e-3)
    # Off-beat 1/8 at straight stays; at triplet delay moves toward 2/3 of pair
    assert apply_swing(0.5, grid="1/8", amount=delay) == pytest.approx(
        0.5 + 0.5 * delay
    )


def test_sustain_pairs_custom_off_value() -> None:
    from app.core.timing import partition_sustain_events, quantize_track

    engine = MidiEngine(bpm=120)
    track = engine.add_track("Melody")
    track.add_note(60, 0, 4)
    track.add_sustain(1.0, 1.05, on_value=100, off_value=10)
    pairs, _ = partition_sustain_events(track.cc_events, off_value=10)
    assert len(pairs) == 1
    assert pairs[0][0].value == 100 and pairs[0][1].value == 10
    # Inference without explicit off_value also pairs high→low
    pairs2, _ = partition_sustain_events(track.cc_events)
    assert len(pairs2) == 1
    quantize_track(track, grid="1/4")
    on_t = next(cc.time_beat for cc in track.cc_events if cc.value == 100)
    off_t = next(cc.time_beat for cc in track.cc_events if cc.value == 10)
    assert off_t > on_t


def test_resolve_channels_ignores_muted_tracks() -> None:
    engine = MidiEngine(bpm=120)
    mel = engine.add_track("Melody", "acoustic_grand_piano", channel=0)
    bass = engine.add_track("Bass", "electric_bass_finger", channel=0)
    muted = engine.add_track("Chords", "electric_piano_1", channel=0)
    mel.add_note(60, 0, 1)
    bass.add_note(36, 0, 1)
    muted.add_note(64, 0, 1)
    muted.muted = True
    engine.resolve_export_channels()
    assert mel.channel != bass.channel
    # Muted track may keep its original channel; must not force melodic remaps
    assert mel.channel in (0, 1, 2) and bass.channel in (0, 1, 2)
    assert mel.channel != 9 and bass.channel != 9
