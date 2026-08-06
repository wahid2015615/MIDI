"""Deterministic chord progression → MidiEngine (no LLM)."""

from __future__ import annotations

from app.core.engine import MidiEngine, normalize_time_signature
from app.core.theory import parse_chord_symbol
from app.features.generation.composer import key_signature_token

# GM drum map
_KICK = 36
_SNARE = 38
_HAT = 42


def _beats_per_bar(numerator: int, denominator: int) -> float:
    return float(numerator) * (4.0 / float(denominator))


def _bass_midi(symbol: str) -> int:
    """Root (or slash bass) in a low register."""
    pitches = parse_chord_symbol(symbol, octave=3)
    if "/" in symbol:
        return max(0, min(127, pitches[0]))
    root_pc = pitches[0] % 12
    return 36 + root_pc  # octave 2


def _add_drum_groove(
    track,
    *,
    start: float,
    duration: float,
    beats_per_bar: float,
) -> None:
    """Simple 4/4-oriented groove across ``duration`` beats from ``start``."""
    end = start + duration
    bar = start
    while bar < end - 1e-9:
        bar_end = min(bar + beats_per_bar, end)
        # Kick on beat 1
        track.add_note(_KICK, bar, min(0.25, bar_end - bar), 100)
        # Snare mid-bar if there is room (beat 3 in 4/4)
        snare_at = bar + beats_per_bar * 0.5
        if snare_at < bar_end - 1e-9:
            track.add_note(_SNARE, snare_at, min(0.25, bar_end - snare_at), 95)
        # Hats on eighths
        t = bar
        while t < bar_end - 1e-9:
            hat_dur = min(0.2, bar_end - t)
            track.add_note(_HAT, t, hat_dur, 70)
            t += 0.5
        bar += beats_per_bar


def build_exact_chords_engine(
    chords: list[str],
    *,
    bpm: float = 120.0,
    bars_per_chord: float = 1.0,
    key: str = "C Major",
    time_signature: tuple[int, int] = (4, 4),
    add_chords: bool = True,
    add_melody: bool = True,
    add_bass: bool = True,
    add_drums: bool = False,
    melody_instrument: str = "acoustic_grand_piano",
    instrument_chords: str = "electric_piano_1",
    instrument_bass: str = "electric_bass_finger",
    instrument_drums: str = "drum_kit",
) -> MidiEngine:
    """Build MIDI with chord tones taken directly from ``parse_chord_symbol``.

    - Chords track: block voicing for each symbol (exact quality notes)
    - Bass track: root / slash bass
    - Melody track: arpeggio of the same chord tones (harmony-locked)
    - Drums track: simple deterministic groove
    """
    if not chords:
        raise ValueError("progression must include at least one chord")
    if not any((add_chords, add_melody, add_bass, add_drums)):
        raise ValueError("Enable at least one track role before generating")

    ts = normalize_time_signature(*time_signature)
    beats_per_bar = _beats_per_bar(ts[0], ts[1])
    chord_beats = max(0.25, float(bars_per_chord) * beats_per_bar)

    engine = MidiEngine(
        bpm=bpm,
        time_signature=ts,
        key_signature=key_signature_token(key),
    )

    chords_track = (
        engine.add_track("Chords", instrument=instrument_chords) if add_chords else None
    )
    bass_track = (
        engine.add_track("Bass", instrument=instrument_bass) if add_bass else None
    )
    melody_track = (
        engine.add_track("Melody", instrument=melody_instrument) if add_melody else None
    )
    drums_track = (
        engine.add_track("Drums", instrument=instrument_drums) if add_drums else None
    )

    cursor = 0.0
    for symbol in chords:
        # Exact voicing from theory parser (default octave 3)
        voicing = parse_chord_symbol(symbol, octave=3)
        if chords_track is not None:
            for pitch in voicing:
                chords_track.add_note(pitch, cursor, chord_beats, 88)

        if bass_track is not None:
            bass_track.add_note(_bass_midi(symbol), cursor, chord_beats, 92)

        if melody_track is not None:
            # Arpeggiate chord tones one octave up (same pitch classes)
            arp = parse_chord_symbol(symbol, octave=4)
            # Skip duplicate bass tone if slash put bass first at low register in voicing;
            # arp is independent re-parse without needing that.
            step = min(1.0, chord_beats / max(1, len(arp)))
            t = cursor
            idx = 0
            while t < cursor + chord_beats - 1e-9:
                pitch = arp[idx % len(arp)]
                dur = min(step, cursor + chord_beats - t)
                if dur > 1e-9:
                    melody_track.add_note(pitch, t, dur, 82)
                t += step
                idx += 1

        if drums_track is not None:
            _add_drum_groove(
                drums_track,
                start=cursor,
                duration=chord_beats,
                beats_per_bar=beats_per_bar,
            )

        cursor += chord_beats

    return engine
