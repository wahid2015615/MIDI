"""Convert model JSON composition into MidiEngine tracks."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.engine import MidiEngine, clamp_bpm, normalize_time_signature
from app.core.theory import note_name_to_midi

logger = logging.getLogger(__name__)


def _pitch_to_midi(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Invalid pitch value: {value!r}")
    if isinstance(value, int):
        pitch = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"Pitch must be an integer MIDI note, got {value!r}")
        pitch = int(value)
    elif isinstance(value, str):
        token = value.strip()
        if token.isdigit():
            pitch = int(token)
        else:
            # Allow "60.0" only when it is an exact integer decimal
            try:
                as_float = float(token)
            except ValueError:
                pitch = note_name_to_midi(token)
            else:
                if not as_float.is_integer():
                    raise ValueError(
                        f"Pitch must be an integer MIDI note, got {value!r}"
                    )
                pitch = int(as_float)
    else:
        raise ValueError(f"Invalid pitch value: {value!r}")
    if not 0 <= pitch <= 127:
        raise ValueError(f"Pitch out of range: {pitch}")
    return pitch


def key_signature_token(key: str) -> str:
    """Map 'C Major' / 'A Minor' / 'Bb Major' → mido key_signature tokens."""
    parts = key.strip().replace("♯", "#").replace("♭", "b").split()
    if not parts:
        return "C"
    root = parts[0]
    # Normalize accidentals attached to root (e.g. Bb, F#)
    if len(root) >= 2 and root[1] in "#b":
        root = root[0].upper() + root[1]
    else:
        root = root[0].upper() + root[1:]
    if len(parts) > 1 and parts[1].lower().startswith("min"):
        return f"{root}m"
    return root


def _canonical_track_name(name: str) -> str:
    """Map AI track labels onto mixer roles (Melody/Chords/Bass/Drums).

    Handles exact names, multi-word labels (``Electric Bass``), and known
    compounds (``Bassline``). Does **not** use open prefix matching so
    ``Bassoon`` stays Bassoon (not Bass).
    """
    raw = (name or "Track").strip()
    if not raw:
        return "Track"
    lower = raw.lower()
    aliases = {
        "melody": "Melody",
        "lead": "Melody",
        "chords": "Chords",
        "chord": "Chords",
        "harmony": "Chords",
        "harmonies": "Chords",
        "pad": "Chords",
        "pads": "Chords",
        "keys": "Chords",
        "comp": "Chords",
        "accompaniment": "Chords",
        "bass": "Bass",
        "drums": "Drums",
        "drum": "Drums",
        "percussion": "Drums",
        "perc": "Drums",
    }
    # Exact compounds only — avoid startswith("bass") → Bassoon
    compounds = {
        "bassline": "Bass",
        "basslines": "Bass",
        "drumkit": "Drums",
        "drumkits": "Drums",
        "chordpad": "Chords",
        "chordpads": "Chords",
    }
    if lower in aliases:
        return aliases[lower]
    if lower in compounds:
        return compounds[lower]

    tokens = [t for t in re.split(r"[^a-z0-9]+", lower) if t]
    for tok in tokens:
        if tok in aliases:
            return aliases[tok]
    for tok in tokens:
        if tok in compounds:
            return compounds[tok]

    return raw


MIXER_ROLES = frozenset({"melody", "chords", "bass", "drums"})
MELODIC_MIXER_ROLES = frozenset({"melody", "chords", "bass"})


def composition_to_engine(data: dict[str, Any]) -> MidiEngine:
    bpm = clamp_bpm(float(data.get("bpm", 120)))
    key = str(data.get("key", "C"))
    key_sig = key_signature_token(key)
    ts = data.get("time_signature") or [4, 4]
    if not isinstance(ts, (list, tuple)) or len(ts) != 2:
        ts = (4, 4)
    try:
        time_signature = normalize_time_signature(ts[0], ts[1])
    except (TypeError, ValueError) as exc:
        logger.warning("Invalid AI time_signature %s (%s); falling back to 4/4", ts, exc)
        time_signature = (4, 4)

    engine = MidiEngine(bpm=bpm, time_signature=time_signature, key_signature=key_sig)
    tracks = data.get("tracks") or []
    if not isinstance(tracks, list) or not tracks:
        raise ValueError("Model composition has no tracks")

    notes_attempted = 0
    notes_added = 0
    skipped_notes: list[str] = []

    for raw in tracks:
        if not isinstance(raw, dict):
            continue
        name = _canonical_track_name(str(raw.get("name") or "Track"))
        instrument = str(raw.get("instrument") or "acoustic_grand_piano")
        channel = raw.get("channel")
        channel_i: int | None = None
        if channel is not None:
            try:
                channel_i = int(channel)
                if not 0 <= channel_i <= 15:
                    channel_i = None
            except (TypeError, ValueError):
                channel_i = None
        track = engine.add_track(name=name, instrument=instrument, channel=channel_i)
        notes = raw.get("notes") or []
        if not isinstance(notes, list):
            continue
        track_attempted = 0
        track_added = 0
        for note in notes:
            if not isinstance(note, dict):
                skipped_notes.append(f"{name}: non-object note {note!r}")
                notes_attempted += 1
                track_attempted += 1
                continue
            notes_attempted += 1
            track_attempted += 1
            try:
                pitch = _pitch_to_midi(note.get("pitch"))
                start = float(note.get("start_beat", 0))
                dur = float(note.get("duration_beats", 1))
                vel = int(note.get("velocity", 90))
            except (TypeError, ValueError) as exc:
                skipped_notes.append(f"{name}: {note!r} ({exc})")
                continue
            if dur <= 0:
                skipped_notes.append(f"{name}: non-positive duration {note!r}")
                continue
            vel = min(127, max(1, vel))
            track.add_note(pitch, max(0.0, start), dur, vel)
            notes_added += 1
            track_added += 1

        if track_attempted > 0 and track_added == 0:
            raise ValueError(
                f"Track '{name}' had {track_attempted} note(s) but none were valid"
            )

        for cc in raw.get("cc") or raw.get("control_changes") or []:
            if not isinstance(cc, dict):
                continue
            try:
                track.add_cc(
                    min(127, max(0, int(cc.get("control", 64)))),
                    min(127, max(0, int(cc.get("value", 0)))),
                    max(0.0, float(cc.get("time_beat", 0))),
                )
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping invalid CC on track %s: %s", name, exc)
                continue

        for sust in raw.get("sustain") or []:
            if not isinstance(sust, dict):
                continue
            try:
                on_b = max(0.0, float(sust.get("on_beat", sust.get("start_beat", 0))))
                off_b = max(
                    0.0, float(sust.get("off_beat", sust.get("end_beat", on_b + 1)))
                )
                if off_b > on_b:
                    track.add_sustain(on_b, off_b)
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping invalid sustain on track %s: %s", name, exc)
                continue

        for pb in raw.get("pitch_bends") or []:
            if not isinstance(pb, dict):
                continue
            try:
                value = pb.get("value", 8192)
                # allow -8192..8191 or 0..16383
                value_i = int(value)
                if -8192 <= value_i <= 8191:
                    value_i = value_i + 8192
                value_i = min(16383, max(0, value_i))
                track.add_pitch_bend(value_i, max(0.0, float(pb.get("time_beat", 0))))
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping invalid pitch bend on track %s: %s", name, exc)
                continue

        # Mute/solo are controlled by the studio mixer only — ignore AI flags so a
        # single "solo": true in model JSON cannot drop the other requested tracks.
        if "volume" in raw:
            try:
                track.volume = min(127, max(0, int(raw["volume"])))
            except (TypeError, ValueError):
                pass
        if "pan" in raw:
            try:
                track.pan = min(127, max(0, int(raw["pan"])))
            except (TypeError, ValueError):
                pass

    if skipped_notes:
        preview = "; ".join(skipped_notes[:8])
        more = len(skipped_notes) - 8
        suffix = f" (+{more} more)" if more > 0 else ""
        logger.warning(
            "Skipped %d invalid AI note(s): %s%s",
            len(skipped_notes),
            preview,
            suffix,
        )

    if notes_attempted > 0 and notes_added == 0:
        raise ValueError("Model composition produced no playable notes")
    # Allow at most 10% skipped notes before rejecting the composition
    if notes_attempted > 0 and notes_added / notes_attempted < 0.9:
        raise ValueError(
            f"Model composition is incomplete: only {notes_added}/{notes_attempted} "
            "notes were valid (need ≥90%)"
        )
    if not any(t.notes for t in engine.tracks):
        raise ValueError("Model composition produced no playable notes")
    return engine
