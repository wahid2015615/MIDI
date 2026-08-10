"""Timing helpers: quantization, swing, humanization."""

from __future__ import annotations

import random
from typing import Literal

from app.core.engine import CCEvent, MidiTrack, NoteEvent, PitchBendEvent

Grid = Literal["1/1", "1/2", "1/4", "1/8", "1/16", "1/32"]

GRID_BEATS: dict[str, float] = {
    "1/1": 4.0,
    "1/2": 2.0,
    "1/4": 1.0,
    "1/8": 0.5,
    "1/16": 0.25,
    "1/32": 0.125,
}

# Common DAW-friendly PPQ (ticks per quarter note) values
COMMON_PPQ: tuple[int, ...] = (96, 192, 240, 384, 480, 960, 1920)

SWING_GRIDS: tuple[str, ...] = ("1/4", "1/8", "1/16", "1/32")

# Minimum sustain length after timing transforms (avoids same-tick on/off)
_MIN_SUSTAIN_BEATS = 1e-4


def quantize_beat(beat: float, grid: Grid | str = "1/16") -> float:
    step = GRID_BEATS[grid]
    return round(beat / step) * step


def quantize_duration(duration: float, grid: Grid | str = "1/16") -> float:
    """Snap duration to the grid; never collapse below one grid step."""
    step = GRID_BEATS[grid]
    if duration <= 0:
        return step
    snapped = round(duration / step) * step
    return max(step, snapped)


def mpc_swing_to_delay(mpc_ratio: float) -> float:
    """Map MPC-style swing ratio to an off-beat delay fraction.

    Industry (MPC / many DAWs): **0.50 = straight**, **~0.67 = triplet feel**.
    Also accepts whole percents (**50** / **66**).
    Returns delay amount in 0..1 for :func:`apply_swing`
    (triplet ≈ 1/3 ≈ 0.333 delay).
    Values ≤ 0.5 (or ≤ 50%) mean no swing.
    """
    try:
        ratio = float(mpc_ratio)
    except (TypeError, ValueError):
        return 0.0
    if ratio != ratio:  # NaN
        return 0.0
    # Allow 50–100 style percents as well as 0.5–1.0 ratios
    if ratio > 1.0:
        ratio = ratio / 100.0
    if ratio <= 0.5:
        return 0.0
    return min(1.0, (ratio - 0.5) / 0.5)


def apply_swing(beat: float, grid: Grid | str = "1/8", amount: float = 0.0) -> float:
    """Shift off-beat steps later.

    ``amount`` is a **delay fraction of one grid step** (0..1), not MPC %.
    Triplet feel ≈ ``amount=1/3`` (≈0.333). MPC 66% → use
    :func:`mpc_swing_to_delay` (0.67 → ~0.34).
    """
    if amount <= 0:
        return beat
    if grid not in GRID_BEATS:
        grid = "1/8"
    step = GRID_BEATS[grid]
    pair = step * 2
    within = beat % pair
    base = beat - within
    if within >= step - 1e-9:
        swing_shift = step * amount
        return base + step + swing_shift
    return beat


def partition_sustain_events(
    cc_events: list[CCEvent],
    *,
    off_value: int | None = None,
) -> tuple[list[tuple[CCEvent, CCEvent]], list[CCEvent]]:
    """Split CC64 into (on, off) pairs; return pairs and all non-paired events.

    Pairing rules (industry half-pedal safe):
    - If ``off_value`` is set, ON = not off_value, OFF = exactly off_value.
    - Otherwise pair whenever a higher value is followed by a lower value
      (pedal down → up / release), so custom offs like 10 still pair with 127.
    """
    sustain = sorted(
        (cc for cc in cc_events if cc.control == 64),
        key=lambda cc: (cc.time_beat, -cc.value),
    )
    other = [cc for cc in cc_events if cc.control != 64]
    pairs: list[tuple[CCEvent, CCEvent]] = []
    unpaired: list[CCEvent] = []
    index = 0
    while index < len(sustain):
        current = sustain[index]
        nxt = sustain[index + 1] if index + 1 < len(sustain) else None
        if nxt is not None:
            if off_value is not None:
                is_pair = current.value != off_value and nxt.value == off_value
            else:
                is_pair = current.value > nxt.value
            if is_pair:
                pairs.append((current, nxt))
                index += 2
                continue
        unpaired.append(current)
        index += 1
    return pairs, other + unpaired


def _quantize_time(beat: float, grid: Grid | str, swing: float, swing_grid: Grid | str) -> float:
    q = quantize_beat(beat, grid)
    return apply_swing(q, grid=swing_grid, amount=swing)


def humanize_track(
    track: MidiTrack,
    *,
    timing_beats: float = 0.02,
    velocity_jitter: int = 8,
    duration_beats: float = 0.01,
    controllers: bool = False,
    seed: int | None = None,
) -> None:
    """Humanize note starts, durations, velocities, and optionally CC/pitch-bend times."""
    rng = random.Random(seed)

    new_notes: list[NoteEvent] = []
    for note in track.notes:
        start = note.start_beat
        if timing_beats > 0:
            start = max(0.0, start + rng.uniform(-timing_beats, timing_beats))

        dur = note.duration_beats
        if duration_beats > 0:
            dur = max(0.05, dur + rng.uniform(-duration_beats, duration_beats))

        vel = note.velocity
        if velocity_jitter > 0:
            vel = min(
                127,
                max(1, vel + rng.randint(-velocity_jitter, velocity_jitter)),
            )

        new_notes.append(
            NoteEvent(
                pitch=note.pitch,
                start_beat=start,
                duration_beats=dur,
                velocity=vel,
            )
        )
    track.notes = new_notes

    if not controllers:
        return

    if timing_beats > 0 and track.cc_events:
        pairs, rest = partition_sustain_events(track.cc_events)
        new_cc: list[CCEvent] = []
        # Sustain pairs share one timing offset so ON/OFF order is preserved
        for on_ev, off_ev in pairs:
            delta = rng.uniform(-timing_beats, timing_beats)
            on_t = max(0.0, on_ev.time_beat + delta)
            off_t = max(0.0, off_ev.time_beat + delta)
            if off_t <= on_t:
                off_t = on_t + max(off_ev.time_beat - on_ev.time_beat, _MIN_SUSTAIN_BEATS)
            new_cc.append(CCEvent(64, on_ev.value, on_t))
            new_cc.append(CCEvent(64, off_ev.value, off_t))
        for cc in rest:
            if cc.control == 64:
                # Unpaired sustain: leave timing unchanged to avoid orphans moving
                new_cc.append(cc)
            else:
                t = max(0.0, cc.time_beat + rng.uniform(-timing_beats, timing_beats))
                new_cc.append(CCEvent(control=cc.control, value=cc.value, time_beat=t))
        track.cc_events = new_cc

    if timing_beats > 0 and track.pitch_bends:
        new_pb: list[PitchBendEvent] = []
        for pb in track.pitch_bends:
            t = max(0.0, pb.time_beat + rng.uniform(-timing_beats, timing_beats))
            new_pb.append(PitchBendEvent(value=pb.value, time_beat=t))
        track.pitch_bends = new_pb


def quantize_track(
    track: MidiTrack,
    grid: Grid | str = "1/16",
    swing: float = 0.0,
    *,
    swing_grid: Grid | str = "1/8",
    quantize_duration_flag: bool = True,
) -> None:
    """Quantize note starts (and optionally durations), CC times, and pitch bends.

    Sustain (CC64) on/off pairs are quantized together so they never collapse
    onto the same timestamp.
    """
    if grid not in GRID_BEATS:
        raise ValueError(f"Unknown quantize grid '{grid}'")

    for note in track.notes:
        q = quantize_beat(note.start_beat, grid)
        note.start_beat = apply_swing(q, grid=swing_grid, amount=swing)
        if quantize_duration_flag:
            note.duration_beats = quantize_duration(note.duration_beats, grid)

    if track.cc_events:
        pairs, rest = partition_sustain_events(track.cc_events)
        new_cc: list[CCEvent] = []
        for on_ev, off_ev in pairs:
            on_t = _quantize_time(on_ev.time_beat, grid, swing, swing_grid)
            duration = max(off_ev.time_beat - on_ev.time_beat, _MIN_SUSTAIN_BEATS)
            off_t = on_t + duration
            # If off also lands on a grid boundary that equals on, nudge forward
            if off_t <= on_t:
                off_t = on_t + _MIN_SUSTAIN_BEATS
            new_cc.append(CCEvent(64, on_ev.value, on_t))
            new_cc.append(CCEvent(64, off_ev.value, off_t))
        for cc in rest:
            if cc.control == 64:
                # Do not independently quantize unpaired sustain events
                new_cc.append(cc)
            else:
                t = _quantize_time(cc.time_beat, grid, swing, swing_grid)
                new_cc.append(CCEvent(control=cc.control, value=cc.value, time_beat=t))
        track.cc_events = new_cc

    for pb in track.pitch_bends:
        q = quantize_beat(pb.time_beat, grid)
        pb.time_beat = apply_swing(q, grid=swing_grid, amount=swing)
