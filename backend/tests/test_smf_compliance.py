"""SMF structure / DAW-compatibility regression tests for MidiEngine export."""

from __future__ import annotations

from pathlib import Path

import pytest
from mido import MidiFile

from app.core.engine import BPM_MIN, MidiEngine, clamp_bpm
from app.core.expression import apply_expression
from app.core.smf_validate import validate_smf_file
from app.core.timing import humanize_track, quantize_track
from app.features.generation.composer import composition_to_engine


def _build_fixture() -> MidiEngine:
    engine = MidiEngine(bpm=120, time_signature=(4, 4), key_signature="C", ppq=480)
    melody = engine.add_track("Melody", "acoustic_grand_piano")
    melody.add_note(60, 0, 1, 90)
    melody.add_note(60, 1, 1, 90)  # same-pitch boundary re-attack
    chords = engine.add_track("Chords", "electric_piano_1")
    for pitch in (60, 64, 67):
        chords.add_note(pitch, 0, 4, 70)
    bass = engine.add_track("Bass", "electric_bass_finger")
    bass.add_note(36, 0, 2, 100)
    bass.add_note(36, 2, 2, 100)
    drums = engine.add_track("Drums", "drum_kit")
    for beat in range(8):
        drums.add_note(36 if beat % 2 == 0 else 42, float(beat), 0.25, 110)
    apply_expression(engine)
    return engine


def test_type1_smf_compliance(tmp_path: Path) -> None:
    path = tmp_path / "type1.mid"
    _build_fixture().export(path, file_type=1)
    mid = validate_smf_file(path, expect_type=1)
    assert len(mid.tracks) == 5
    assert mid.tracks[0].name == "Conductor"


def test_type0_smf_compliance(tmp_path: Path) -> None:
    path = tmp_path / "type0.mid"
    _build_fixture().export(path, file_type=0)
    mid = validate_smf_file(path, expect_type=0)
    assert len(mid.tracks) == 1


def test_min_one_tick_note_duration(tmp_path: Path) -> None:
    engine = MidiEngine(bpm=120, ppq=480)
    track = engine.add_track("Short", "flute")
    track.add_note(72, 0.0, 0.0001, 90)
    path = tmp_path / "short.mid"
    engine.export(path, file_type=1)
    mid = MidiFile(path)
    durations: list[int] = []
    stack: dict[int, int] = {}
    for tr in mid.tracks:
        abs_tick = 0
        for msg in tr:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                stack[msg.note] = abs_tick
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                if msg.note in stack:
                    durations.append(abs_tick - stack.pop(msg.note))
    assert durations
    assert all(d >= 1 for d in durations)


def test_same_pitch_reattack_order(tmp_path: Path) -> None:
    engine = MidiEngine(bpm=120, ppq=480)
    track = engine.add_track("Melody", "acoustic_grand_piano")
    track.add_note(60, 0.0, 1.0, 90)
    track.add_note(60, 1.0, 1.0, 90)
    path = tmp_path / "reattack.mid"
    engine.export(path, file_type=1)
    validate_smf_file(path, 1)


def test_clamp_bpm() -> None:
    assert clamp_bpm(0) == 120.0
    assert clamp_bpm(-1) == 120.0
    assert clamp_bpm(-10) == 120.0
    assert clamp_bpm(500) == 300.0
    assert clamp_bpm(120) == 120.0
    assert clamp_bpm(3) == BPM_MIN
    engine = MidiEngine(bpm=0)
    assert engine.bpm == 120.0


def test_quantize_preserves_sustain_pair_order() -> None:
    engine = MidiEngine(bpm=120)
    track = engine.add_track("Melody")
    track.add_note(60, 0, 4, 90)
    track.add_sustain(1.0, 1.05)
    quantize_track(track, grid="1/4")
    on_t = next(cc.time_beat for cc in track.cc_events if cc.value > 0)
    off_t = next(cc.time_beat for cc in track.cc_events if cc.value == 0)
    assert off_t > on_t


def test_humanize_preserves_sustain_pair_order() -> None:
    for seed in range(50):
        engine = MidiEngine(bpm=120)
        track = engine.add_track("Melody")
        track.add_note(60, 0, 4, 90)
        track.add_sustain(1.0, 1.02)
        humanize_track(track, timing_beats=0.05, controllers=True, seed=seed)
        on_t = next(cc.time_beat for cc in track.cc_events if cc.value > 0)
        off_t = next(cc.time_beat for cc in track.cc_events if cc.value == 0)
        assert off_t > on_t


def test_same_pitch_overlap_becomes_legato(tmp_path: Path) -> None:
    engine = MidiEngine(bpm=120, ppq=480)
    track = engine.add_track("Melody")
    track.add_note(60, 0.0, 2.0, 90)
    track.add_note(60, 1.0, 2.0, 90)
    path = tmp_path / "overlap.mid"
    engine.export(path, file_type=1)
    validate_smf_file(path, 1)

    events: list[tuple[int, str]] = []
    mid = MidiFile(path)
    for tr in mid.tracks:
        abs_tick = 0
        for msg in tr:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0 and msg.note == 60:
                events.append((abs_tick, "on"))
            elif (
                msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0)
            ) and msg.note == 60:
                events.append((abs_tick, "off"))
    # Expect: on @0, off @480, on @480, off @1440 (legato abutment)
    assert events[0] == (0, "on")
    assert events[1][0] == 480 and events[1][1] == "off"
    assert events[2][0] == 480 and events[2][1] == "on"
    assert events[3][1] == "off"


def test_channel_assignment_reserves_drums() -> None:
    engine = MidiEngine(bpm=120)
    melodic_channels = []
    for i in range(16):
        track = engine.add_track(f"T{i}", "acoustic_grand_piano")
        melodic_channels.append(track.channel)
    drums = engine.add_track("Drums", "drum_kit")
    assert drums.channel == 9
    assert 9 not in melodic_channels
    # After exhausting melodic channels, reuse least-used — never force all onto 0
    assert len(set(melodic_channels)) == 15


def test_composer_rejects_mostly_invalid_notes() -> None:
    data = {
        "bpm": 120,
        "key": "C",
        "time_signature": [4, 4],
        "tracks": [
            {
                "name": "Melody",
                "instrument": "acoustic_grand_piano",
                "notes": [
                    {"pitch": 60, "start_beat": 0, "duration_beats": 1, "velocity": 90},
                    {"pitch": 999, "start_beat": 1, "duration_beats": 1, "velocity": 90},
                    {"pitch": -1, "start_beat": 2, "duration_beats": 1, "velocity": 90},
                    {"pitch": "bad", "start_beat": 3, "duration_beats": 1, "velocity": 90},
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="incomplete"):
        composition_to_engine(data)


def test_composer_clamps_bpm() -> None:
    data = {
        "bpm": 0,
        "tracks": [
            {
                "name": "Melody",
                "notes": [
                    {"pitch": 60, "start_beat": 0, "duration_beats": 1, "velocity": 90},
                ],
            }
        ],
    }
    engine = composition_to_engine(data)
    assert engine.bpm == 120.0


def test_normalize_time_signature() -> None:
    from app.core.engine import normalize_time_signature
    from app.shared.schemas import TimeSignatureOptions
    from pydantic import ValidationError

    assert normalize_time_signature(4, 4) == (4, 4)
    assert normalize_time_signature(3, 8) == (3, 8)
    assert normalize_time_signature(16, 16) == (16, 16)

    for bad in [(4, 3), (7, 5), (10, 6), (0, 4), (17, 4), (4.5, 4)]:
        with pytest.raises(ValueError):
            normalize_time_signature(*bad)

    with pytest.raises(ValidationError):
        TimeSignatureOptions(numerator=4, denominator=3)
    with pytest.raises(ValidationError):
        TimeSignatureOptions(numerator=17, denominator=4)
    with pytest.raises(ValidationError):
        TimeSignatureOptions(numerator=4.5, denominator=4)

    opts = TimeSignatureOptions()
    assert opts.as_tuple() == (4, 4)


def test_normalize_bars() -> None:
    from app.core.engine import (
        BARS_DEFAULT,
        BARS_MAX,
        BARS_MIN,
        clamp_bars,
        normalize_bars,
    )
    from app.features.generation.service import parse_text_prompt
    from app.features.text_to_midi.schemas import TextGenerateRequest
    from pydantic import ValidationError

    assert normalize_bars(1) == 1
    assert normalize_bars(16) == 16
    assert normalize_bars(512) == 512
    assert normalize_bars(BARS_DEFAULT) == BARS_DEFAULT

    for bad in [0, -1, 513, 64.5, True]:
        with pytest.raises(ValueError, match="bars must be"):
            normalize_bars(bad)  # type: ignore[arg-type]

    assert clamp_bars(0) == BARS_MIN
    assert clamp_bars(9999) == BARS_MAX
    assert clamp_bars("nope") == BARS_DEFAULT  # type: ignore[arg-type]

    # Prompt parsing clamps into API range
    assert parse_text_prompt("make 999 bars of music").bars == BARS_MAX
    assert parse_text_prompt("8 bars piano").bars == 8
    assert parse_text_prompt("happy piano").bars == BARS_DEFAULT

    # API schema: 1–512
    TextGenerateRequest(prompt="x", bars=128)
    TextGenerateRequest(prompt="x", bars=512)
    with pytest.raises(ValidationError):
        TextGenerateRequest(prompt="x", bars=0)
    with pytest.raises(ValidationError):
        TextGenerateRequest(prompt="x", bars=513)

    # Empty / whitespace-only prompts rejected (avoids wasting LLM cycle)
    with pytest.raises(ValidationError):
        TextGenerateRequest(prompt="")
    with pytest.raises(ValidationError):
        TextGenerateRequest(prompt="   ")
    assert TextGenerateRequest(prompt="  hello piano  ").prompt == "hello piano"


def test_ai_solo_does_not_drop_tracks(tmp_path: Path) -> None:
    data = {
        "bpm": 120,
        "key": "A Minor",
        "time_signature": [3, 4],
        "tracks": [
            {
                "name": "Melody",
                "solo": True,
                "notes": [
                    {"pitch": 60, "start_beat": 0, "duration_beats": 1, "velocity": 90}
                ],
            },
            {
                "name": "Chords",
                "notes": [
                    {"pitch": 60, "start_beat": 0, "duration_beats": 4, "velocity": 70}
                ],
            },
            {
                "name": "Bass",
                "notes": [
                    {"pitch": 36, "start_beat": 0, "duration_beats": 2, "velocity": 100}
                ],
            },
        ],
    }
    engine = composition_to_engine(data)
    assert all(not t.solo for t in engine.tracks)
    path = tmp_path / "multi.mid"
    engine.export(path, file_type=1)
    mid = MidiFile(path)
    names = [t.name for t in mid.tracks]
    assert names == ["Conductor", "Melody", "Chords", "Bass"]
    # SMF Type 1: tempo / TS / key on Conductor (track 0) only by default
    conductor = mid.tracks[0]
    assert any(m.type == "time_signature" and m.numerator == 3 for m in conductor)
    assert any(m.type == "key_signature" and m.key == "Am" for m in conductor)
    assert any(m.type == "set_tempo" for m in conductor)
    melody = mid.tracks[1]
    assert not any(m.type == "set_tempo" for m in melody)

    # Optional web-player compat: duplicate meta onto note tracks
    path_dup = tmp_path / "multi_dup.mid"
    engine.export(path_dup, file_type=1, duplicate_score_meta=True)
    mid_dup = MidiFile(path_dup)
    melody_dup = mid_dup.tracks[1]
    assert any(m.type == "time_signature" and m.numerator == 3 for m in melody_dup)
    assert any(m.type == "key_signature" and m.key == "Am" for m in melody_dup)
    assert any(m.type == "set_tempo" for m in melody_dup)

    from app.core.catalog import (
        DEFAULT_MOOD,
        DEFAULT_STYLE,
        MOODS,
        STYLES,
        match_mood_in_text,
        match_style_in_text,
        normalize_mood,
        normalize_style,
    )
    from app.features.generation.service import parse_text_prompt
    from app.features.text_to_midi.schemas import TextGenerateRequest
    from pydantic import ValidationError

    assert len(MOODS) == 20
    assert len(STYLES) == 20
    assert DEFAULT_MOOD == "Happy"
    assert DEFAULT_STYLE == "Pop"
    assert normalize_mood("happy") == "Happy"
    assert normalize_mood("Uplifting") == "Uplifting"
    assert normalize_style("lo-fi") == "Lo-Fi"
    assert normalize_style("hip hop") == "Hip Hop"
    assert normalize_style("R&B") == "R&B"
    assert normalize_style("rnb") == "R&B"

    for bad in ["groovy", "metal"]:
        with pytest.raises(ValueError, match="Unsupported"):
            normalize_mood(bad)
        with pytest.raises(ValueError, match="Unsupported"):
            normalize_style(bad)
    for empty in ["", "  "]:
        with pytest.raises(ValueError, match="non-empty"):
            normalize_mood(empty)
        with pytest.raises(ValueError, match="non-empty"):
            normalize_style(empty)

    assert match_mood_in_text("an epic dark score") == "Epic"
    assert match_style_in_text("make some lo-fi beats") == "Lo-Fi"
    assert match_style_in_text("popular music today") is None
    assert match_mood_in_text("an intense groove") is None

    spec = parse_text_prompt("relaxing jazz piano")
    assert spec.mood == "Relaxing"
    assert spec.style == "Jazz"
    assert parse_text_prompt("just a melody").mood == DEFAULT_MOOD
    assert parse_text_prompt("just a melody").style == DEFAULT_STYLE

    TextGenerateRequest(prompt="x", mood="Happy", style="Pop")
    TextGenerateRequest(prompt="x", mood="sad", style="edm")  # normalized
    with pytest.raises(ValidationError):
        TextGenerateRequest(prompt="x", mood="groovy")
    with pytest.raises(ValidationError):
        TextGenerateRequest(prompt="x", style="metal")


def test_parse_text_prompt_key_not_article_a() -> None:
    from app.features.generation.service import parse_text_prompt

    spec = parse_text_prompt(
        "Generate a 16-bar uplifting piano melody in C Major at 128 BPM."
    )
    assert spec.key == "C Major"
    assert spec.mood == "Uplifting"
    assert spec.bpm == 128
    assert spec.bars == 16

    spec2 = parse_text_prompt(
        "Make a sad violin melody in A Minor, 90 BPM, 8 bars, cinematic mood."
    )
    assert spec2.key == "A Minor"
    assert spec2.mood == "Cinematic"  # longer label wins when both present
    assert spec2.bpm == 90

    assert parse_text_prompt("just a melody").key == "C Major"


def test_parse_text_prompt_time_signature() -> None:
    from app.features.generation.service import parse_text_prompt_detailed

    result = parse_text_prompt_detailed(
        "Generate a 16-bar waltz piano piece in 3/4 at 120 BPM in C Major."
    )
    assert result.spec.time_signature == (3, 4)
    assert result.detected["time_signature"] is True

    result68 = parse_text_prompt_detailed("uplifting melody in 6/8 time, 8 bars")
    assert result68.spec.time_signature == (6, 8)
    assert result68.detected["time_signature"] is True

    result_word = parse_text_prompt_detailed("a romantic waltz for piano")
    assert result_word.spec.time_signature == (3, 4)
    assert result_word.detected["time_signature"] is True

    silent = parse_text_prompt_detailed("happy piano melody at 128 BPM")
    assert silent.spec.time_signature == (4, 4)
    assert silent.detected["time_signature"] is False
