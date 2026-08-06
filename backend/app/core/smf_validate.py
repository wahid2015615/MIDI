"""SMF structure / DAW-compatibility checks for exported MIDI files."""

from __future__ import annotations

import struct
from collections import defaultdict
from pathlib import Path

from mido import MidiFile


def validate_smf_file(path: str | Path, expect_type: int | None = None) -> MidiFile:
    """Re-parse and validate a Standard MIDI File.

    Raises ValueError with a clear message if the file is invalid or
    fails structural / note-balance checks used for DAW compatibility.
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Cannot read MIDI file: {exc}") from exc

    if len(raw) < 14:
        raise ValueError("MIDI file too short to contain a valid SMF header")
    if raw[:4] != b"MThd":
        raise ValueError("Invalid MIDI file: missing MThd header")
    header_len = struct.unpack(">I", raw[4:8])[0]
    if header_len != 6:
        raise ValueError(f"Invalid MIDI header length: {header_len} (expected 6)")

    fmt, ntrks, division = struct.unpack(">HHH", raw[8:14])
    if expect_type is not None and fmt != expect_type:
        raise ValueError(f"MIDI type mismatch: got {fmt}, expected {expect_type}")
    if division & 0x8000:
        raise ValueError("SMPTE division is not supported; expected ticks-per-beat")
    if not 24 <= division <= 9600:
        raise ValueError(f"PPQ/division out of safe range: {division}")

    try:
        mid = MidiFile(path)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Failed to parse MIDI file: {exc}") from exc

    if mid.type != fmt:
        raise ValueError(f"Parsed MIDI type {mid.type} does not match header {fmt}")
    if len(mid.tracks) != ntrks:
        raise ValueError(
            f"Track count mismatch: header={ntrks}, parsed={len(mid.tracks)}"
        )
    if mid.ticks_per_beat != division:
        raise ValueError(
            f"PPQ mismatch: header={division}, parsed={mid.ticks_per_beat}"
        )

    pos = 14
    for i in range(ntrks):
        if pos + 8 > len(raw):
            raise ValueError(f"Truncated MIDI track header at track {i}")
        if raw[pos : pos + 4] != b"MTrk":
            raise ValueError(f"Invalid MIDI track chunk at track {i}: missing MTrk")
        tlen = struct.unpack(">I", raw[pos + 4 : pos + 8])[0]
        pos += 8 + tlen
    if pos != len(raw):
        raise ValueError(
            f"MIDI file length mismatch: consumed={pos}, file={len(raw)}"
        )

    has_tempo = False
    has_ts = False
    lengths: list[int] = []

    for track_index, track in enumerate(mid.tracks):
        abs_tick = 0
        stack: dict[tuple[int, int], int] = defaultdict(int)
        has_eot = False
        by_tick: dict[int, list[tuple[str, int, int]]] = defaultdict(list)

        for msg in track:
            if msg.time < 0:
                raise ValueError(
                    f"Negative delta time in track {track_index}: {msg.time}"
                )
            abs_tick += msg.time
            if msg.type == "end_of_track":
                has_eot = True
            elif msg.type == "set_tempo":
                has_tempo = True
            elif msg.type == "time_signature":
                has_ts = True
            elif msg.type == "note_on" and msg.velocity > 0:
                stack[(msg.channel, msg.note)] += 1
                by_tick[abs_tick].append(("on", msg.channel, msg.note))
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                stack[(msg.channel, msg.note)] -= 1
                by_tick[abs_tick].append(("off", msg.channel, msg.note))
            elif msg.type == "control_change":
                if not 0 <= msg.control <= 127 or not 0 <= msg.value <= 127:
                    raise ValueError(
                        f"CC out of range in track {track_index}: "
                        f"control={msg.control} value={msg.value}"
                    )
            elif msg.type == "pitchwheel":
                if not -8192 <= msg.pitch <= 8191:
                    raise ValueError(
                        f"Pitch bend out of range in track {track_index}: {msg.pitch}"
                    )

        if not has_eot:
            raise ValueError(f"Track {track_index} is missing end_of_track")
        unbalanced = {k: v for k, v in stack.items() if v != 0}
        if unbalanced:
            raise ValueError(
                f"Unbalanced note on/off in track {track_index}: {unbalanced}"
            )
        lengths.append(abs_tick)

        for tick, events in by_tick.items():
            seen_on: set[tuple[int, int]] = set()
            for kind, ch, note in events:
                key = (ch, note)
                if kind == "on":
                    seen_on.add(key)
                elif kind == "off" and key in seen_on:
                    raise ValueError(
                        f"note_off after note_on at same tick {tick} "
                        f"for channel {ch} note {note}"
                    )

    if not has_tempo:
        raise ValueError("MIDI file is missing set_tempo meta event")
    if not has_ts:
        raise ValueError("MIDI file is missing time_signature meta event")
    if lengths and max(lengths) <= 0 and any(
        msg.type == "note_on" and getattr(msg, "velocity", 0) > 0
        for track in mid.tracks
        for msg in track
    ):
        raise ValueError("MIDI file reports zero length but contains notes")
    if fmt == 1 and lengths and max(lengths) > 0:
        if lengths[0] != max(lengths):
            raise ValueError(
                "Type 1 conductor track does not span the full piece length"
            )

    return mid
