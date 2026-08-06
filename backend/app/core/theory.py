"""Convert note names like C4, F#3, Bb5 to MIDI numbers."""

from __future__ import annotations

NOTE_TO_SEMITONE = {
    "C": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
}

DURATION_BEATS = {
    "whole": 4.0,
    "w": 4.0,
    "half": 2.0,
    "h": 2.0,
    "quarter": 1.0,
    "q": 1.0,
    "eighth": 0.5,
    "e": 0.5,
    "8th": 0.5,
    "sixteenth": 0.25,
    "s": 0.25,
    "16th": 0.25,
    "dotted_quarter": 1.5,
    "dq": 1.5,
    "dotted_half": 3.0,
    "dh": 3.0,
    "triplet_quarter": 2 / 3,
    "tq": 2 / 3,
}

SCALE_INTERVALS = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
}

# Intervals in semitones from chord root (compound extensions use >11).
CHORD_QUALITY: dict[str, tuple[int, ...]] = {
    # V1
    "": (0, 4, 7),
    "maj": (0, 4, 7),
    "m": (0, 3, 7),
    "min": (0, 3, 7),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "min7": (0, 3, 7, 10),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    # V2
    "5": (0, 7),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "dim7": (0, 3, 6, 9),
    "m7b5": (0, 3, 6, 10),
    "7sus": (0, 5, 7, 10),
    "7sus4": (0, 5, 7, 10),
    "9": (0, 4, 7, 10, 14),
    "m9": (0, 3, 7, 10, 14),
    "maj9": (0, 4, 7, 11, 14),
    "add9": (0, 4, 7, 14),
    "madd9": (0, 3, 7, 14),
    "add2": (0, 2, 4, 7),
    # V3
    "11": (0, 4, 7, 10, 14, 17),
    "m11": (0, 3, 7, 10, 14, 17),
    "maj11": (0, 4, 7, 11, 14, 17),
    "13": (0, 4, 7, 10, 14, 21),
    "m13": (0, 3, 7, 10, 14, 21),
    "maj13": (0, 4, 7, 11, 14, 21),
    "7b5": (0, 4, 6, 10),
    "7#5": (0, 4, 8, 10),
    "7b9": (0, 4, 7, 10, 13),
    "7#9": (0, 4, 7, 10, 15),
    "7#11": (0, 4, 7, 10, 18),
    "7b13": (0, 4, 7, 10, 20),
    "7alt": (0, 4, 6, 10, 13, 15),
    "maj7#11": (0, 4, 7, 11, 18),
    "9b5": (0, 4, 6, 10, 14),
    "9#5": (0, 4, 8, 10, 14),
    "m7#5": (0, 3, 8, 10),
}

CHORD_QUALITY_ALIASES = {
    "mi": "m",
    "-": "m",
    "-7": "m7",
    "-6": "m6",
    "-9": "m9",
    "-11": "m11",
    "-13": "m13",
    "min": "m",
    "sus": "sus4",
    "power": "5",
    "dom": "7",
    "dom7": "7",
    "dominant": "7",
    "dominant7": "7",
    "halfdim": "m7b5",
    "half-dim": "m7b5",
    "ø": "m7b5",
    "ø7": "m7b5",
    # Classic diminished (not half-dim): Co / Co7
    "o": "dim",
    "o7": "dim7",
    "0": "m7b5",  # sometimes B0 for half-dim
    "min7": "m7",
    "min6": "m6",
    "min9": "m9",
    "min11": "m11",
    "min13": "m13",
    "min7b5": "m7b5",
    "madd2": "add2",
    "sus7": "7sus4",
    "sus4add7": "7sus4",
}

SUPPORTED_CHORD_HINT = (
    "maj, m, 5, 6, m6, dim, dim7, aug, 7, maj7, m7, m7b5, "
    "sus2, sus4, 7sus4, 9, m9, maj9, add9, add2, 11, 13, "
    "7b9, 7#9, 7b5, 7#5, 7alt, slash (C/G)"
)


def _normalize_pitch_token(token: str) -> str:
    token = token.strip().replace("♭", "b").replace("♯", "#")
    if len(token) >= 2 and token[1] == "b":
        return (token[0] + "B").upper()
    return token.upper()


def note_name_to_midi(note: str) -> int:
    """Convert note like 'C4', 'F#3', 'Bb5' to MIDI number."""
    note = note.strip().replace("♭", "b").replace("♯", "#")
    if len(note) < 2:
        raise ValueError(f"Invalid note: {note}")

    if len(note) >= 2 and note[1] in "#b":
        pitch = _normalize_pitch_token(note[:2])
        octave_str = note[2:]
    else:
        pitch = note[0].upper()
        octave_str = note[1:]

    try:
        octave = int(octave_str)
    except ValueError as exc:
        raise ValueError(f"Invalid note octave in '{note}'") from exc

    if pitch not in NOTE_TO_SEMITONE:
        raise ValueError(f"Unknown pitch class in '{note}'")

    midi = (octave + 1) * 12 + NOTE_TO_SEMITONE[pitch]
    if not 0 <= midi <= 127:
        raise ValueError(f"MIDI note out of range for '{note}': {midi}")
    return midi


def parse_duration(token: str) -> float:
    """Parse a duration token into quarter-note beats.

    Accepts short forms (``quarter``, ``q``, ``half``) and sheet-style
    phrases (``quarter note``, ``half notes``).
    """
    token = token.strip().lower().replace("-", "_")
    # Allow "quarter note" / "half notes" from sheet-music style docs
    if token.endswith(" notes"):
        token = token[: -len(" notes")].strip()
    elif token.endswith(" note"):
        token = token[: -len(" note")].strip()
    if token in DURATION_BEATS:
        return DURATION_BEATS[token]
    try:
        return float(token)
    except ValueError as exc:
        raise ValueError(f"Unknown duration '{token}'") from exc


def key_root_midi(key: str, octave: int = 4) -> int:
    root = key.strip().replace("♭", "b").replace("♯", "#").split()[0]
    return note_name_to_midi(f"{root}{octave}")


def scale_pitch_classes(key: str) -> list[int]:
    """Return pitch classes (0-11) for a key like 'C Major' or 'A minor'."""
    parts = key.strip().replace("♭", "b").replace("♯", "#").split()
    if not parts:
        raise ValueError("Empty key")

    root_key = _normalize_pitch_token(parts[0])
    if root_key not in NOTE_TO_SEMITONE:
        raise ValueError(f"Unknown key root: {key}")

    mode = "major"
    if len(parts) > 1:
        mode_token = parts[1].lower()
        if mode_token.startswith("min"):
            mode = "minor"
        elif mode_token in SCALE_INTERVALS:
            mode = mode_token

    root_pc = NOTE_TO_SEMITONE[root_key]
    return [(root_pc + i) % 12 for i in SCALE_INTERVALS[mode]]


def _parse_pitch_class(token: str) -> str:
    """Parse a pitch-class token like C, F#, Bb into a note_name-safe root."""
    token = token.strip().replace("♭", "b").replace("♯", "#")
    if not token:
        raise ValueError("Empty pitch class")
    if len(token) >= 2 and token[1] in "#b":
        if len(token) > 2:
            raise ValueError(f"Unexpected trailing characters in pitch '{token}'")
        root = token[0].upper() + token[1]
    else:
        if len(token) > 1:
            raise ValueError(f"Unexpected trailing characters in pitch '{token}'")
        root = token[0].upper()
    normalized = _normalize_pitch_token(root)
    if normalized not in NOTE_TO_SEMITONE:
        raise ValueError(f"Unknown pitch class '{token}'")
    return root


def _normalize_chord_quality(quality: str) -> str:
    """Normalize quality spelling into a CHORD_QUALITY key."""
    q = (
        quality.strip()
        .replace("♭", "b")
        .replace("♯", "#")
        .replace("Ø", "ø")
        .replace("(", "")
        .replace(")", "")
        .replace("^", "maj")
        .lower()
    )
    q = q.replace("major", "maj").replace("minor", "min")
    # Half-diminished glyphs before other aliasing
    if q in {"ø", "ø7"} or q.startswith("ø"):
        return "m7b5"
    while q in CHORD_QUALITY_ALIASES:
        q = CHORD_QUALITY_ALIASES[q]
    # min7 / min9 already handled via aliases; leftover "min" alone → m
    if q == "min":
        q = "m"
    return q


def parse_chord_symbol(symbol: str, octave: int = 3) -> list[int]:
    """Parse chord symbols into MIDI pitches.

    Supports V1–V3 qualities and slash bass (e.g. ``C/G``, ``Am7/E``).

    Raises ValueError for unknown roots or unknown quality strings (never
    silently remaps garbage like "Foo" to a major triad).
    """
    symbol = symbol.strip().replace("♭", "b").replace("♯", "#").replace("Ø", "ø")
    if not symbol:
        raise ValueError("Empty chord symbol")

    bass_token: str | None = None
    main = symbol
    if "/" in symbol:
        main, bass_raw = symbol.rsplit("/", 1)
        main = main.strip()
        bass_raw = bass_raw.strip()
        if not main or not bass_raw:
            raise ValueError(f"Invalid slash chord '{symbol}'")
        bass_token = bass_raw

    if len(main) > 1 and main[1] in "#b":
        root = main[:2]
        quality = main[2:]
    else:
        root = main[0]
        quality = main[1:]

    root_token = root[0].upper() + (root[1:] if len(root) > 1 else "")
    if root_token[0] not in "ABCDEFG":
        raise ValueError(f"Invalid chord root in '{symbol}'")
    if len(root_token) > 1 and root_token[1] not in "#b":
        raise ValueError(f"Invalid chord root in '{symbol}'")

    quality_raw = quality
    quality = _normalize_chord_quality(quality)

    if quality not in CHORD_QUALITY:
        raise ValueError(
            f"Unknown chord quality '{quality_raw}' in '{symbol}'. "
            f"Supported: {SUPPORTED_CHORD_HINT}"
        )

    intervals = CHORD_QUALITY[quality]
    root_midi = note_name_to_midi(f"{root_token}{octave}")
    pitches = [root_midi + i for i in intervals]

    if bass_token is not None:
        bass_pc = _parse_pitch_class(bass_token)
        bass_octave = max(0, octave - 1)
        bass_midi = note_name_to_midi(f"{bass_pc}{bass_octave}")
        # Prefer bass below the chord; nudge down an octave if needed
        if bass_midi >= root_midi:
            candidate = bass_midi - 12
            if candidate >= 0:
                bass_midi = candidate
        pitches = [bass_midi] + [p for p in pitches if p % 12 != bass_midi % 12]

    for p in pitches:
        if not 0 <= p <= 127:
            raise ValueError(f"MIDI note out of range in chord '{symbol}': {p}")
    return pitches


def bpm_to_tempo_usec(bpm: float) -> int:
    return int(60_000_000 / bpm)
