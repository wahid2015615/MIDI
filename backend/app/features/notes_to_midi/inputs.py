from __future__ import annotations

import re
from typing import Sequence

from app.core.engine import MidiEngine, MidiTrack
from app.core.instruments import resolve_instrument_slug
from app.core.theory import note_name_to_midi, parse_duration
from app.features.generation.composer import _canonical_track_name

# Pitch token: C4, F#3, Bb5, C-1, …
NOTE_TOKEN_RE = re.compile(r"^[A-Ga-g](?:#|b|♯|♭)?-?\d+$")

# @track …  |  #track …  (name may be multi-word; instrument is last GM token(s))
TRACK_DIRECTIVE_RE = re.compile(
    r"^(?:@track|#track)\s+(?P<body>.+?)\s*$",
    re.IGNORECASE,
)

# [Melody]  or  [Chords electric_piano_1]  or  [Electric Bass flute]
SECTION_RE = re.compile(
    r"^\[\s*(?P<body>[^\]]+)\s*\]\s*$",
)

DEFAULT_TRACK_INSTRUMENTS: dict[str, str] = {
    "melody": "acoustic_grand_piano",
    "chords": "electric_piano_1",
    "bass": "electric_bass_finger",
    "drums": "drum_kit",
}


def _is_rest_line(lower: str) -> bool:
    """True for bare `r`, `r q`, `rest`, `rest quarter`, etc."""
    return lower == "r" or lower.startswith("rest") or lower.startswith("r ")


def _default_instrument(track_name: str) -> str:
    return DEFAULT_TRACK_INSTRUMENTS.get(
        track_name.strip().lower(),
        "acoustic_grand_piano",
    )


def _split_name_and_instrument(parts: list[str]) -> tuple[str, str | None]:
    """Split directive tokens into track name + optional validated instrument.

    Instrument is taken from the longest valid GM/alias suffix (1–3 tokens),
    leaving at least one token for the track name. Examples:
      Melody flute              → ("Melody", "flute")
      Electric Bass flute       → ("Electric Bass", "flute")
      Bass electric_bass_finger → ("Bass", "electric_bass_finger")
      Bass                      → ("Bass", None)

    If the first token is a known mixer role and more tokens follow but none
    resolve as an instrument, raise (e.g. ``Melody not_a_real_synth``).
    Otherwise an unrecognized multi-word body is treated as a custom track name.
    """
    if not parts:
        return "Melody", None
    if len(parts) == 1:
        return parts[0], None

    max_inst_tokens = min(3, len(parts) - 1)
    for n in range(max_inst_tokens, 0, -1):
        candidate = " ".join(parts[-n:])
        try:
            slug = resolve_instrument_slug(candidate)
            name = " ".join(parts[:-n]).strip()
            if not name:
                continue
            return name, slug
        except ValueError:
            continue

    role_aliases = {
        "melody",
        "lead",
        "chords",
        "chord",
        "harmony",
        "harmonies",
        "pad",
        "pads",
        "keys",
        "comp",
        "accompaniment",
        "bass",
        "drums",
        "drum",
        "percussion",
        "perc",
    }
    if parts[0].strip().lower() in role_aliases:
        # Explicit instrument was attempted after a role name — validate it.
        slug = resolve_instrument_slug(" ".join(parts[1:]))
        return parts[0], slug

    return " ".join(parts), None


def _parse_section_body(body: str) -> tuple[str, str | None]:
    parts = body.strip().split()
    return _split_name_and_instrument(parts)


def parse_note_event_line(line: str) -> tuple[list[str], str, int | None]:
    """Parse ``C4 q``, ``C4 E4 G4 q``, or ``C4 E4 G4 half note 90``.

    Returns ``(pitch_tokens, duration_token, velocity_or_None)``.
    Same-line pitches share one beat / one duration (and optional velocity).
    """
    parts = line.split()
    if len(parts) < 2:
        raise ValueError(
            f"Cannot parse note line: '{line}' "
            "(expected: C4 q  or  C4 E4 G4 q)"
        )

    pitches: list[str] = []
    i = 0
    while i < len(parts) and NOTE_TOKEN_RE.match(parts[i]):
        pitches.append(parts[i])
        i += 1

    if not pitches:
        raise ValueError(f"Cannot parse note line: '{line}' (missing pitch)")
    if i >= len(parts):
        raise ValueError(f"Cannot parse note line: '{line}' (missing duration)")

    dur_parts = [parts[i]]
    i += 1
    if i < len(parts) and parts[i].lower() in {"note", "notes"}:
        dur_parts.append(parts[i])
        i += 1

    velocity: int | None = None
    if i < len(parts):
        if parts[i].isdigit() and i == len(parts) - 1:
            velocity = int(parts[i])
            i += 1
        else:
            raise ValueError(f"Cannot parse note line: '{line}'")

    if i != len(parts):
        raise ValueError(f"Cannot parse note line: '{line}'")

    return pitches, " ".join(dur_parts), velocity


def _add_parsed_notes(
    track: MidiTrack,
    line: str,
    cursor: float,
    default_velocity: int,
) -> float:
    """Add one or more same-beat notes; return cursor after shared duration."""
    pitches, dur_token, vel_opt = parse_note_event_line(line)
    dur = parse_duration(dur_token)
    vel = default_velocity if vel_opt is None else vel_opt
    for token in pitches:
        track.add_note(note_name_to_midi(token), cursor, dur, vel)
    return cursor + dur


def add_notes_from_lines(
    engine: MidiEngine,
    lines: Sequence[str],
    track_name: str = "Melody",
    instrument: str = "acoustic_grand_piano",
    start_beat: float = 0.0,
    default_velocity: int = 90,
) -> MidiTrack:
    """
    Parse note lines into one or more tracks.

    Multi-track directives (any may be mixed):
      @track Melody acoustic_grand_piano
      #track Bass electric_bass_finger
      @track Electric Bass flute
      [Chords]
      [Drums drum_kit]

    Same-line chords share one beat:
      C4 E4 G4 q
      C4 E4 G4 half note 90

    Without directives, all notes go on a single track named ``track_name``.
    Each track keeps its own beat cursor (independent timelines).
    """
    tracks_by_name: dict[str, MidiTrack] = {}
    cursors: dict[str, float] = {}
    current_name = _canonical_track_name(track_name)
    current_instrument = resolve_instrument_slug(instrument)

    def _ensure_track(
        name: str,
        inst: str | None = None,
    ) -> MidiTrack:
        key = _canonical_track_name(name)
        if key not in tracks_by_name:
            slug = resolve_instrument_slug(inst or _default_instrument(key))
            tracks_by_name[key] = engine.add_track(key, instrument=slug)
            cursors[key] = start_beat
        elif inst is not None:
            # Overwrite must validate the same way as add_track.
            slug = resolve_instrument_slug(inst)
            tracks_by_name[key].instrument = slug
        return tracks_by_name[key]

    # Peek whether any track directive exists
    has_directives = False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") and not line.lower().startswith("#track"):
            # allow # comments that are not #track
            if line.lower().startswith("#track"):
                has_directives = True
                break
            continue
        if TRACK_DIRECTIVE_RE.match(line) or SECTION_RE.match(line):
            has_directives = True
            break

    if not has_directives:
        track = _ensure_track(current_name, current_instrument)
        cursor = start_beat
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            lower = line.lower()
            if _is_rest_line(lower):
                parts = line.split()
                dur_token = " ".join(parts[1:]) if len(parts) > 1 else "quarter"
                cursor += parse_duration(dur_token)
                continue
            cursor = _add_parsed_notes(track, line, cursor, default_velocity)
        if not track.notes:
            raise ValueError("No playable notes found in the note list")
        return track

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # Comments: allow "#track ..." but treat other "#" as comments
        if line.startswith("#") and not line.lower().startswith("#track"):
            continue

        directive = TRACK_DIRECTIVE_RE.match(line)
        if directive:
            name, inst = _split_name_and_instrument(directive.group("body").split())
            current_name = _canonical_track_name(name.strip())
            if inst:
                current_instrument = inst
                _ensure_track(current_name, current_instrument)
            else:
                # Bare @track Role — keep prior custom instrument if track exists.
                track = _ensure_track(current_name, None)
                current_instrument = track.instrument
            continue

        section = SECTION_RE.match(line)
        if section:
            name, inst = _parse_section_body(section.group("body"))
            current_name = _canonical_track_name(name.strip())
            if inst:
                current_instrument = inst
                _ensure_track(current_name, current_instrument)
            else:
                track = _ensure_track(current_name, None)
                current_instrument = track.instrument
            continue

        track = _ensure_track(current_name)
        cursor = cursors[current_name]

        lower = line.lower()
        if _is_rest_line(lower):
            parts = line.split()
            dur_token = " ".join(parts[1:]) if len(parts) > 1 else "quarter"
            cursors[current_name] = cursor + parse_duration(dur_token)
            continue

        cursors[current_name] = _add_parsed_notes(
            track, line, cursor, default_velocity
        )

    if not tracks_by_name:
        return _ensure_track(track_name, instrument)
    if not any(t.notes for t in tracks_by_name.values()):
        raise ValueError("No playable notes found in the note list")
    # Return the first track for backward-compatible return type
    return next(iter(tracks_by_name.values()))
