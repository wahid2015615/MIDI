"""Unit tests for core theory, filenames, and BPM clamp (no HTTP)."""

from __future__ import annotations

import pytest

from app.core.engine import clamp_bpm, normalize_time_signature
from app.core.theory import note_name_to_midi, parse_chord_symbol, parse_duration
from app.shared.midi_response import safe_filename


def test_note_name_to_midi_middle_c():
    assert note_name_to_midi("C4") == 60
    assert note_name_to_midi("A4") == 69
    assert note_name_to_midi("Bb3") == 58
    assert note_name_to_midi("F#5") == 78


def test_note_name_rejects_garbage():
    with pytest.raises(ValueError):
        note_name_to_midi("H4")
    with pytest.raises(ValueError):
        note_name_to_midi("C")


def test_parse_duration_tokens():
    assert parse_duration("q") == 1.0
    assert parse_duration("h") == 2.0
    assert parse_duration("w") == 4.0
    assert parse_duration("e") == 0.5
    assert parse_duration("s") == 0.25
    assert parse_duration("quarter note") == 1.0


def test_parse_chord_symbol_triads_and_slash():
    c = parse_chord_symbol("C", octave=4)
    assert 60 in c
    am = parse_chord_symbol("Am")
    assert len(am) >= 3
    slash = parse_chord_symbol("C/G", octave=4)
    assert slash  # bass G included
    with pytest.raises(ValueError):
        parse_chord_symbol("Foo")
    with pytest.raises(ValueError):
        parse_chord_symbol("")


def test_clamp_bpm_and_time_signature():
    assert clamp_bpm(0) == 120
    assert clamp_bpm(-9) == 120
    assert clamp_bpm(40) == 40
    assert normalize_time_signature(3, 4) == (3, 4)
    with pytest.raises(ValueError):
        normalize_time_signature(4, 3)


def test_safe_filename_strips_paths_and_forces_mid():
    assert safe_filename("../../etc/passwd") == "passwd.mid"
    assert safe_filename("C:\\Windows\\x.mid") == "x.mid"
    assert safe_filename("a/b/c.mid") == "c.mid"
    assert ".." not in safe_filename("foo/../../bar.mid")
    assert safe_filename("song") == "song.mid"
    assert safe_filename("  ") == "midi_output.mid"
    assert safe_filename("ok.mid") == "ok.mid"
    assert "<" not in safe_filename('"><script>.mid')
