"""Core MIDI engine: tracks, events, Type 0 / Type 1 export."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from mido import Message, MetaMessage, MidiFile, MidiTrack as MidoTrack, bpm2tempo

from app.core.instruments import DRUM_CHANNEL, get_program, is_drum_instrument
from app.core.smf_validate import validate_smf_file

logger = logging.getLogger(__name__)

# Safe BPM range for SMF set_tempo (mido 24-bit microseconds)
BPM_MIN = 4.0
BPM_MAX = 300.0

# MIDI time signature (SMF meta): numerator 1–16; denominator must be power of 2
TS_NUMERATOR_MIN = 1
TS_NUMERATOR_MAX = 16
VALID_TS_DENOMINATORS: tuple[int, ...] = (1, 2, 4, 8, 16, 32)

# Composition length (bars): API allows up to 512; UI may use a tighter max
BARS_MIN = 1
BARS_MAX = 512
BARS_DEFAULT = 16

# Absolute beat-time ceiling (~512 bars × 16/4 time). Rejects Inf / DoS sizes.
BEAT_TIME_MAX = float(BARS_MAX * 16)

PPQ_MIN = 24
PPQ_MAX = 9600


def require_finite_beat(
    value: float,
    *,
    name: str,
    allow_zero: bool = False,
    maximum: float = BEAT_TIME_MAX,
) -> float:
    """Validate a beat time is finite and within export-safe bounds."""
    try:
        beat = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc
    if not math.isfinite(beat):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if allow_zero:
        if beat < 0:
            raise ValueError(f"{name} must be >= 0")
    elif beat <= 0:
        raise ValueError(f"{name} must be > 0")
    if beat > maximum:
        raise ValueError(f"{name} must be <= {maximum:g}, got {beat:g}")
    return beat


def clamp_bpm(bpm: float) -> float:
    """Clamp BPM into the safe export range (rejects non-finite values).

    Non-positive values (cleared UI → 0) fall back to 120, not BPM_MIN.
    """
    try:
        value = float(bpm)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"BPM must be a number, got {bpm!r}") from exc
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"BPM must be finite, got {bpm!r}")
    if value <= 0:
        return 120.0
    return max(BPM_MIN, min(BPM_MAX, value))


def normalize_time_signature(
    numerator: int | float,
    denominator: int | float,
) -> tuple[int, int]:
    """Validate and return a MIDI-legal (numerator, denominator) pair.

    Raises ValueError for non-integers or values outside the allowed ranges.
    """
    if isinstance(numerator, bool) or isinstance(denominator, bool):
        raise ValueError(
            f"time_signature values must be integers, got {numerator!r}/{denominator!r}"
        )
    try:
        num = int(numerator)
        den = int(denominator)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"time_signature values must be integers, got {numerator!r}/{denominator!r}"
        ) from exc
    if isinstance(numerator, float) and not float(numerator).is_integer():
        raise ValueError(
            f"time_signature values must be integers, got {numerator!r}/{denominator!r}"
        )
    if isinstance(denominator, float) and not float(denominator).is_integer():
        raise ValueError(
            f"time_signature values must be integers, got {numerator!r}/{denominator!r}"
        )
    if not TS_NUMERATOR_MIN <= num <= TS_NUMERATOR_MAX:
        raise ValueError(
            f"time_signature.numerator must be {TS_NUMERATOR_MIN}–{TS_NUMERATOR_MAX}, got {num}"
        )
    if den not in VALID_TS_DENOMINATORS:
        raise ValueError(
            f"time_signature.denominator must be one of {VALID_TS_DENOMINATORS}, got {den}"
        )
    return num, den


def normalize_bars(bars: int | float, *, maximum: int = BARS_MAX) -> int:
    """Validate bars count; raise ValueError with a clear message if out of range."""
    if isinstance(bars, bool):
        raise ValueError(f"bars must be an integer, got {bars!r}")
    try:
        value = int(bars)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"bars must be an integer, got {bars!r}") from exc
    if isinstance(bars, float) and not float(bars).is_integer():
        raise ValueError(f"bars must be an integer, got {bars!r}")
    max_allowed = int(maximum)
    if not BARS_MIN <= value <= max_allowed:
        raise ValueError(
            f"bars must be between {BARS_MIN} and {max_allowed}, got {value}"
        )
    return value


def clamp_bars(bars: int | float, *, maximum: int = BARS_MAX) -> int:
    """Clamp bars into the allowed range (for prompt parsing / soft paths)."""
    try:
        value = int(round(float(bars)))
    except (TypeError, ValueError):
        return BARS_DEFAULT
    if value != value:  # NaN
        return BARS_DEFAULT
    return max(BARS_MIN, min(int(maximum), value))


@dataclass
class NoteEvent:
    """A single note with timing in beats from track start."""

    pitch: int
    start_beat: float
    duration_beats: float
    velocity: int = 90

    def __post_init__(self) -> None:
        if not 0 <= self.pitch <= 127:
            raise ValueError(f"pitch must be 0-127, got {self.pitch}")
        if not 1 <= self.velocity <= 127:
            raise ValueError(f"velocity must be 1-127, got {self.velocity}")
        self.start_beat = require_finite_beat(
            self.start_beat, name="start_beat", allow_zero=True
        )
        self.duration_beats = require_finite_beat(
            self.duration_beats, name="duration_beats", allow_zero=False
        )


@dataclass
class CCEvent:
    control: int
    value: int
    time_beat: float

    def __post_init__(self) -> None:
        if not 0 <= self.control <= 127:
            raise ValueError(f"CC control must be 0-127, got {self.control}")
        if not 0 <= self.value <= 127:
            raise ValueError(f"CC value must be 0-127, got {self.value}")
        self.time_beat = require_finite_beat(
            self.time_beat, name="CC time_beat", allow_zero=True
        )


@dataclass
class PitchBendEvent:
    value: int  # MIDI pitch wheel 0-16383 (8192 = center)
    time_beat: float

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 16383:
            raise ValueError(f"pitch bend must be 0-16383, got {self.value}")
        self.time_beat = require_finite_beat(
            self.time_beat, name="pitch bend time_beat", allow_zero=True
        )


@dataclass
class MidiTrack:
    name: str
    channel: int = 0
    instrument: str = "acoustic_grand_piano"
    volume: int = 100
    pan: int = 64
    muted: bool = False
    solo: bool = False
    notes: list[NoteEvent] = field(default_factory=list)
    cc_events: list[CCEvent] = field(default_factory=list)
    pitch_bends: list[PitchBendEvent] = field(default_factory=list)

    def add_note(
        self,
        pitch: int,
        start_beat: float,
        duration_beats: float,
        velocity: int = 90,
    ) -> None:
        self.notes.append(NoteEvent(pitch, start_beat, duration_beats, velocity))

    def add_sustain(
        self,
        on_beat: float,
        off_beat: float,
        *,
        on_value: int = 127,
        off_value: int = 0,
    ) -> None:
        """Sustain pedal CC64 (default full down / full up)."""
        self.cc_events.append(
            CCEvent(64, max(0, min(127, int(on_value))), on_beat)
        )
        self.cc_events.append(
            CCEvent(64, max(0, min(127, int(off_value))), off_beat)
        )

    def add_pitch_bend(self, value: int, time_beat: float) -> None:
        self.pitch_bends.append(PitchBendEvent(value=value, time_beat=time_beat))

    def add_cc(self, control: int, value: int, time_beat: float) -> None:
        self.cc_events.append(CCEvent(control=control, value=value, time_beat=time_beat))


class MidiEngine:
    """Build a multi-track MIDI composition and export Standard MIDI Files."""

    def __init__(
        self,
        bpm: float = 120.0,
        time_signature: tuple[int, int] = (4, 4),
        key_signature: str | None = "C",
        ppq: int = 480,
        ticks_per_beat: int | None = None,
    ) -> None:
        self.bpm = clamp_bpm(bpm)
        self.time_signature = normalize_time_signature(*time_signature)
        self.key_signature = key_signature
        raw_ppq = ppq if ticks_per_beat is None else ticks_per_beat
        try:
            ppq_val = int(raw_ppq)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"ppq must be an integer, got {raw_ppq!r}") from exc
        if not PPQ_MIN <= ppq_val <= PPQ_MAX:
            raise ValueError(
                f"ppq must be between {PPQ_MIN} and {PPQ_MAX}, got {ppq_val}"
            )
        self.ppq = ppq_val
        self.tracks: list[MidiTrack] = []

    def _next_melodic_channel(self) -> int:
        """Assign the least-used non-drum channel; prefer free channels first."""
        melodic = [i for i in range(16) if i != DRUM_CHANNEL]
        counts = {i: 0 for i in melodic}
        for track in self.tracks:
            ch = max(0, min(15, int(track.channel)))
            if ch != DRUM_CHANNEL and ch in counts:
                counts[ch] += 1
        free = [i for i in melodic if counts[i] == 0]
        if free:
            return free[0]
        return min(melodic, key=lambda i: (counts[i], i))

    def resolve_export_channels(self) -> None:
        """Force drums on channel 9; keep melodic tracks unique and off channel 9.

        Only **active** (exported) tracks are considered so muted/non-solo lanes
        do not reserve channels or force remaps on the audible mix.

        Prevents GM drum misuse and same-channel collisions (program stomps /
        shared note_off cutting another track). When more than 15 melodic
        active tracks exist, later tracks may share a channel as a last resort.
        """
        used: set[int] = set()
        drum_count = 0
        for track in self._active_tracks():
            if is_drum_instrument(track.instrument):
                drum_count += 1
                if drum_count > 1:
                    raise ValueError(
                        "Only one active drum track is allowed "
                        "(GM channel 10 / index 9). Remove drum_kit from "
                        "extra roles or mute the duplicate."
                    )
                track.channel = DRUM_CHANNEL
                continue
            # Validate instrument early so typos never silently become piano
            get_program(track.instrument)
            ch = max(0, min(15, int(track.channel)))
            if ch == DRUM_CHANNEL or ch in used:
                free = [i for i in range(16) if i != DRUM_CHANNEL and i not in used]
                if free:
                    ch = free[0]
                elif ch == DRUM_CHANNEL:
                    ch = 0
                # else keep ch (forced share — only when >15 melodic tracks)
            track.channel = ch
            used.add(ch)

    def add_track(
        self,
        name: str,
        instrument: str = "acoustic_grand_piano",
        channel: int | None = None,
        volume: int = 100,
        pan: int = 64,
    ) -> MidiTrack:
        # Reject unknown instruments immediately (never silently fall back to piano)
        get_program(instrument)

        if channel is None:
            if is_drum_instrument(instrument):
                channel = DRUM_CHANNEL
            else:
                channel = self._next_melodic_channel()
        else:
            channel = max(0, min(15, int(channel)))
            if is_drum_instrument(instrument):
                channel = DRUM_CHANNEL
            elif channel == DRUM_CHANNEL:
                # Melodic content must never land on the GM drum channel
                channel = self._next_melodic_channel()

        track = MidiTrack(
            name=name,
            channel=channel,
            instrument=instrument,
            volume=volume,
            pan=pan,
        )
        self.tracks.append(track)
        return track

    def beats_to_ticks(self, beats: float) -> int:
        try:
            value = float(beats)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"beats must be a number, got {beats!r}") from exc
        if not math.isfinite(value):
            raise ValueError(f"beats must be finite, got {beats!r}")
        try:
            return max(0, int(round(value * self.ppq)))
        except (OverflowError, ValueError) as exc:
            raise ValueError(
                f"Beat time too large for PPQ conversion: {beats!r}"
            ) from exc

    def _resolve_same_pitch_overlaps(
        self, notes: list[NoteEvent]
    ) -> list[NoteEvent]:
        """Convert overlapping same-pitch notes into legato (off before next on)."""
        if len(notes) <= 1:
            return list(notes)

        min_beats = 1.0 / max(self.ppq, 1)
        by_pitch: dict[int, list[NoteEvent]] = {}
        for note in notes:
            by_pitch.setdefault(int(note.pitch), []).append(note)

        resolved: list[NoteEvent] = []
        for pitch_notes in by_pitch.values():
            ordered = sorted(
                pitch_notes, key=lambda n: (n.start_beat, n.duration_beats)
            )
            group: list[NoteEvent] = []
            for note in ordered:
                if group:
                    prev = group[-1]
                    prev_end = prev.start_beat + prev.duration_beats
                    if note.start_beat <= prev.start_beat:
                        # Same attack time: keep the longer note only
                        if note.duration_beats > prev.duration_beats:
                            logger.debug(
                                "Same-pitch same-start overlap: keeping longer "
                                "note (pitch=%s, duration=%s); dropping shorter",
                                pitch,
                                note.duration_beats,
                            )
                            group[-1] = note
                        else:
                            logger.debug(
                                "Same-pitch same-start overlap: dropping shorter "
                                "note (pitch=%s, duration=%s)",
                                pitch,
                                note.duration_beats,
                            )
                        continue
                    if prev_end > note.start_beat:
                        truncated = note.start_beat - prev.start_beat
                        group[-1] = NoteEvent(
                            pitch=prev.pitch,
                            start_beat=prev.start_beat,
                            duration_beats=truncated if truncated > 0 else min_beats,
                            velocity=prev.velocity,
                        )
                group.append(note)
            resolved.extend(group)
        return resolved

    def _meta_events(self) -> list[tuple[int, MetaMessage]]:
        numerator, denominator = self.time_signature
        events: list[tuple[int, MetaMessage]] = [
            (
                0,
                MetaMessage(
                    "time_signature",
                    numerator=numerator,
                    denominator=denominator,
                    clocks_per_click=24,
                    notated_32nd_notes_per_beat=8,
                ),
            ),
            (0, MetaMessage("set_tempo", tempo=bpm2tempo(self.bpm))),
        ]
        if self.key_signature:
            try:
                events.append(
                    (0, MetaMessage("key_signature", key=self.key_signature))
                )
            except ValueError as exc:
                raise ValueError(
                    f"Unsupported key signature {self.key_signature!r}"
                ) from exc
        return events

    def _active_tracks(self) -> list[MidiTrack]:
        """Tracks that should export / contribute to duration.

        Multi-solo: every solo-enabled track is kept (solo overrides mute).
        When no track is soloed, muted tracks are excluded.
        """
        if any(t.solo for t in self.tracks):
            return [t for t in self.tracks if t.solo]
        return [t for t in self.tracks if not t.muted]

    def _piece_end_tick(self, tracks: Iterable[MidiTrack]) -> int:
        """Latest absolute tick across notes, CC, and pitch bends."""
        end = 0
        for track in tracks:
            for note in track.notes:
                start = self.beats_to_ticks(note.start_beat)
                stop = self.beats_to_ticks(note.start_beat + note.duration_beats)
                if stop <= start:
                    stop = start + 1
                end = max(end, stop)
            for cc in track.cc_events:
                end = max(end, self.beats_to_ticks(cc.time_beat))
            for pb in track.pitch_bends:
                end = max(end, self.beats_to_ticks(pb.time_beat))
        return end

    @staticmethod
    def _same_tick_priority(msg: Message | MetaMessage) -> int:
        """SMF-safe order at one tick: note_off → controllers/meta → note_on.

        note_off before note_on is required so same-pitch re-attacks are audible.
        """
        if msg.type == "note_off" or (
            msg.type == "note_on" and getattr(msg, "velocity", 1) == 0
        ):
            return 0
        if msg.type == "note_on":
            return 2
        return 1

    def _build_mido(
        self,
        file_type: Literal[0, 1] = 1,
        *,
        duplicate_score_meta: bool = False,
    ) -> MidiFile:
        self.resolve_export_channels()
        mid = MidiFile(type=file_type, ticks_per_beat=self.ppq)
        active_tracks = self._active_tracks()
        end_tick = self._piece_end_tick(active_tracks)

        if file_type == 0:
            # Type 0 = exactly one track (tempo + all channels merged)
            mido_track = MidoTrack()
            mido_track.name = "Merged"
            merged = self._meta_events() + self._events_for_tracks(active_tracks)
            self._append_absolute_events(mido_track, merged, end_tick=end_tick)
            mid.tracks.append(mido_track)
            return mid

        # Type 1 = conductor (tempo map) + one track per MidiTrack.
        # SMF 1.0: tempo / time signature belong on track 0 only.
        # Extend conductor to piece end so DAWs that key off track-0 length
        # still see the full song duration.
        conductor = MidoTrack()
        conductor.name = "Conductor"
        for _, msg in self._meta_events():
            conductor.append(msg.copy(time=0))
        conductor.append(MetaMessage("end_of_track", time=end_tick))
        mid.tracks.append(conductor)

        for track in active_tracks:
            mido_track = MidoTrack()
            mido_track.name = track.name
            events = self._events_for_tracks([track])
            if duplicate_score_meta:
                # Optional web-player / online-sequencer compatibility
                events = self._meta_events() + events
            track_end = self._piece_end_tick([track])
            self._append_absolute_events(
                mido_track, events, end_tick=max(track_end, end_tick)
            )
            mid.tracks.append(mido_track)

        return mid

    def _events_for_tracks(
        self, tracks: Iterable[MidiTrack]
    ) -> list[tuple[int, Message | MetaMessage]]:
        """Return absolute-tick timed MIDI messages."""
        events: list[tuple[int, Message | MetaMessage]] = []

        for track in tracks:
            ch = max(0, min(15, int(track.channel)))
            program = get_program(track.instrument)
            volume = max(0, min(127, int(track.volume)))
            pan = max(0, min(127, int(track.pan)))

            # Program change (skip meaningful for drums; still harmless)
            events.append((0, Message("program_change", channel=ch, program=program)))
            events.append(
                (0, Message("control_change", channel=ch, control=7, value=volume))
            )
            events.append(
                (0, Message("control_change", channel=ch, control=10, value=pan))
            )

            for cc in track.cc_events:
                tick = self.beats_to_ticks(cc.time_beat)
                events.append(
                    (
                        tick,
                        Message(
                            "control_change",
                            channel=ch,
                            control=max(0, min(127, int(cc.control))),
                            value=max(0, min(127, int(cc.value))),
                        ),
                    )
                )

            for pb in track.pitch_bends:
                tick = self.beats_to_ticks(pb.time_beat)
                # SMF pitch wheel is signed 14-bit centered at 0 (-8192..8191)
                wheel = max(-8192, min(8191, int(pb.value) - 8192))
                events.append(
                    (
                        tick,
                        Message("pitchwheel", channel=ch, pitch=wheel),
                    )
                )

            # Resolve same-pitch overlaps in beat space, then again in tick space
            # so rounding cannot reintroduce overlapping note_off / note_on.
            tick_notes: list[tuple[int, int, int, int]] = []
            for note in self._resolve_same_pitch_overlaps(track.notes):
                start = self.beats_to_ticks(note.start_beat)
                end = self.beats_to_ticks(note.start_beat + note.duration_beats)
                if end <= start:
                    end = start + 1
                pitch = max(0, min(127, int(note.pitch)))
                velocity = max(1, min(127, int(note.velocity)))
                tick_notes.append((start, end, pitch, velocity))

            tick_notes = self._resolve_same_pitch_overlaps_ticks(tick_notes)
            for start, end, pitch, velocity in tick_notes:
                events.append(
                    (
                        start,
                        Message(
                            "note_on",
                            channel=ch,
                            note=pitch,
                            velocity=velocity,
                        ),
                    )
                )
                events.append(
                    (
                        end,
                        Message(
                            "note_off",
                            channel=ch,
                            note=pitch,
                            velocity=0,
                        ),
                    )
                )

        events.sort(key=lambda item: (item[0], self._same_tick_priority(item[1])))
        return events

    @staticmethod
    def _resolve_same_pitch_overlaps_ticks(
        notes: list[tuple[int, int, int, int]],
    ) -> list[tuple[int, int, int, int]]:
        """Clamp (start, end, pitch, velocity) so same-pitch offs never pass next on."""
        if len(notes) <= 1:
            return list(notes)

        by_pitch: dict[int, list[tuple[int, int, int, int]]] = {}
        for start, end, pitch, vel in notes:
            by_pitch.setdefault(pitch, []).append((start, end, pitch, vel))

        resolved: list[tuple[int, int, int, int]] = []
        for pitch_notes in by_pitch.values():
            ordered = sorted(pitch_notes, key=lambda n: (n[0], n[1]))
            group: list[tuple[int, int, int, int]] = []
            for note in ordered:
                start, end, pitch, vel = note
                if group:
                    prev_start, prev_end, prev_pitch, prev_vel = group[-1]
                    if start <= prev_start:
                        if end - start > prev_end - prev_start:
                            group[-1] = note
                        continue
                    if prev_end > start:
                        truncated = start - prev_start
                        group[-1] = (
                            prev_start,
                            prev_start + max(1, truncated),
                            prev_pitch,
                            prev_vel,
                        )
                group.append((start, end, pitch, vel))
            resolved.extend(group)
        return resolved

    @staticmethod
    def _append_absolute_events(
        mido_track: MidoTrack,
        events: list[tuple[int, Message | MetaMessage]],
        *,
        end_tick: int | None = None,
    ) -> None:
        last_tick = 0
        for abs_tick, msg in events:
            if abs_tick < last_tick:
                abs_tick = last_tick
            delta = abs_tick - last_tick
            msg = msg.copy(time=delta)
            mido_track.append(msg)
            last_tick = abs_tick
        # Pad end_of_track to the intended span when the last event ends early
        # (e.g. setup CCs only) or when aligning tracks to the piece length.
        eot_tick = last_tick if end_tick is None else max(last_tick, end_tick)
        mido_track.append(MetaMessage("end_of_track", time=eot_tick - last_tick))

    def export(
        self,
        path: str | Path,
        file_type: Literal[0, 1] = 1,
        *,
        duplicate_score_meta: bool = False,
    ) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Keep bpm / time signature safe even if mutated after construction
        self.bpm = clamp_bpm(self.bpm)
        self.time_signature = normalize_time_signature(*self.time_signature)
        mid = self._build_mido(
            file_type=file_type,
            duplicate_score_meta=duplicate_score_meta,
        )
        mid.save(path)
        try:
            validate_smf_file(path, expect_type=file_type)
        except ValueError as exc:
            raise ValueError(f"Exported MIDI failed validation: {exc}") from exc
        return path

    def duration_beats(self, *, active_only: bool = True) -> float:
        """Return piece length in beats.

        By default only unmuted (and solo-filtered) tracks count so muted AI
        material cannot stretch expression spans or X-MIDI-Bars.
        """
        end = 0.0
        tracks = self._active_tracks() if active_only else self.tracks
        for track in tracks:
            for note in track.notes:
                end = max(end, note.start_beat + note.duration_beats)
        return end

    def duration_bars(self, *, active_only: bool = True) -> float:
        num, den = self.time_signature
        beats_per_bar = num * (4.0 / den) if den else 0.0
        return (
            self.duration_beats(active_only=active_only) / beats_per_bar
            if beats_per_bar
            else 0.0
        )