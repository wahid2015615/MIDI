"""Ensure expression events (sustain, CC, pitch bend) land in exported MIDI."""

from __future__ import annotations

from app.core.engine import MidiEngine, MidiTrack
from app.core.instruments import is_drum_instrument


# Instruments that typically benefit from sustain pedal
_SUSTAIN_INSTRUMENTS = {
    "acoustic_grand_piano",
    "bright_acoustic_piano",
    "electric_grand_piano",
    "honky_tonk_piano",
    "electric_piano_1",
    "electric_piano_2",
    "harpsichord",
    "clavinet",
    "string_ensemble_1",
    "string_ensemble_2",
    "choir_aahs",
    "voice_oohs",
    "pad_2_warm",
    "pad_1_new_age",
}

# Historical defaults (used when callers omit advanced params)
DEFAULT_SUSTAIN_ON = 127
DEFAULT_SUSTAIN_OFF = 0
DEFAULT_SUSTAIN_HOLD_RATIO = 0.92
DEFAULT_MODULATION_VALUE = 24
DEFAULT_MODULATION_INTERVAL_BARS = 2.0
DEFAULT_MODULATION_ACCENT_RATIO = 0.5
DEFAULT_PB_SCOOP_DEPTH = 400
DEFAULT_PB_INTERVAL_BARS = 4.0
DEFAULT_PB_SCOOP_BEATS = 0.25
PITCH_BEND_CENTER = 8192


def _beats_per_bar(engine: MidiEngine) -> float:
    num, den = engine.time_signature
    # one bar in quarter-note beats
    return num * (4.0 / den)


def _track_end_beat(track: MidiTrack) -> float:
    end = 0.0
    for note in track.notes:
        end = max(end, note.start_beat + note.duration_beats)
    return end


def _has_cc(track: MidiTrack, control: int) -> bool:
    return any(cc.control == control for cc in track.cc_events)


def _has_pitch_bend(track: MidiTrack) -> bool:
    return bool(track.pitch_bends)


def apply_expression(
    engine: MidiEngine,
    *,
    sustain: bool = True,
    modulation: bool = True,
    pitch_bend: bool = True,
    sustain_on_value: int = DEFAULT_SUSTAIN_ON,
    sustain_off_value: int = DEFAULT_SUSTAIN_OFF,
    sustain_hold_ratio: float = DEFAULT_SUSTAIN_HOLD_RATIO,
    modulation_value: int = DEFAULT_MODULATION_VALUE,
    modulation_interval_bars: float = DEFAULT_MODULATION_INTERVAL_BARS,
    modulation_accent_ratio: float = DEFAULT_MODULATION_ACCENT_RATIO,
    pitch_bend_scoop_depth: int = DEFAULT_PB_SCOOP_DEPTH,
    pitch_bend_interval_bars: float = DEFAULT_PB_INTERVAL_BARS,
    pitch_bend_scoop_beats: float = DEFAULT_PB_SCOOP_BEATS,
) -> None:
    """
    Write musical expression into tracks so exported .mid contains:
    - Sustain pedal (CC64) on suitable tracks
    - Modulation (CC1) accents
    - Pitch bend center + optional light bends on lead/synth
    Volume (CC7) and pan (CC10) are already written on export.

    Advanced numeric args customize the automation; defaults preserve legacy.
    """
    bar = _beats_per_bar(engine)
    duration = max(engine.duration_beats(active_only=True), bar)

    sustain_on = max(0, min(127, int(sustain_on_value)))
    sustain_off = max(0, min(127, int(sustain_off_value)))
    hold_ratio = max(0.05, min(1.0, float(sustain_hold_ratio)))

    mod_peak = max(0, min(127, int(modulation_value)))
    mod_interval = max(0.25, float(modulation_interval_bars))
    mod_accent = max(0.05, float(modulation_accent_ratio))

    pb_depth = max(0, min(8191, int(pitch_bend_scoop_depth)))
    pb_interval = max(0.25, float(pitch_bend_interval_bars))
    pb_scoop = max(0.05, float(pitch_bend_scoop_beats))

    for track in engine._active_tracks():
        if is_drum_instrument(track.instrument) or track.channel == 9:
            # Drums: still ensure pitch bend center is clean; skip sustain/mod
            if pitch_bend and not _has_pitch_bend(track):
                track.add_pitch_bend(PITCH_BEND_CENTER, 0.0)
            continue

        name = track.name.strip().lower()
        end = max(_track_end_beat(track), duration)

        # Sustain pedal: hold through most of each bar, lift slightly before next bar
        if sustain and (
            name in {"melody", "chords"}
            or track.instrument in _SUSTAIN_INSTRUMENTS
        ):
            if not _has_cc(track, 64):
                beat = 0.0
                while beat < end - 1e-9:
                    on = beat
                    off = min(beat + bar * hold_ratio, end)
                    if off > on:
                        track.add_sustain(
                            on,
                            off,
                            on_value=sustain_on,
                            off_value=sustain_off,
                        )
                    beat += bar

        # Modulation wheel (CC1) — expression accents on melody
        if modulation and name == "melody" and not _has_cc(track, 1):
            track.add_cc(1, 0, 0.0)
            beat = bar * mod_interval
            while beat < end:
                track.add_cc(1, mod_peak, beat)
                track.add_cc(1, 0, min(beat + bar * mod_accent, end))
                beat += bar * mod_interval

        # Pitch bend: always write center at t=0 so PB data exists in file;
        # scoops on lead/synth melody phrases
        if pitch_bend:
            if not _has_pitch_bend(track):
                track.add_pitch_bend(PITCH_BEND_CENTER, 0.0)
            if name == "melody" and (
                "lead" in track.instrument
                or "synth" in track.instrument
                or track.instrument in {"lead_1_square", "lead_2_sawtooth"}
            ):
                beat = 0.0
                while beat < end:
                    track.add_pitch_bend(PITCH_BEND_CENTER - pb_depth, beat)
                    track.add_pitch_bend(
                        PITCH_BEND_CENTER, min(beat + pb_scoop, end)
                    )
                    beat += bar * pb_interval
