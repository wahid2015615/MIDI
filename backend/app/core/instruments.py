"""General MIDI (GM) instrument map and helpers."""

from __future__ import annotations

# Program numbers are 0-based (MIDI Program Change).
GM_INSTRUMENTS: dict[str, int] = {
    # Piano
    "acoustic_grand_piano": 0,
    "bright_acoustic_piano": 1,
    "electric_grand_piano": 2,
    "honky_tonk_piano": 3,
    "electric_piano_1": 4,
    "electric_piano_2": 5,
    # Guitar / Bass
    "nylon_guitar": 24,
    "steel_guitar": 25,
    "electric_guitar_clean": 27,
    "electric_guitar_muted": 28,
    "overdriven_guitar": 29,
    "distortion_guitar": 30,
    "acoustic_bass": 32,
    "electric_bass_finger": 33,
    "electric_bass_pick": 34,
    "fretless_bass": 35,
    "slap_bass_1": 36,
    # Strings / Ensemble
    "violin": 40,
    "viola": 41,
    "cello": 42,
    "contrabass": 43,
    "tremolo_strings": 44,
    "pizzicato_strings": 45,
    "orchestral_harp": 46,
    "string_ensemble_1": 48,
    "string_ensemble_2": 49,
    "synth_strings_1": 50,
    # Brass / Reed / Pipe
    "trumpet": 56,
    "trombone": 57,
    "tuba": 58,
    "french_horn": 60,
    "alto_sax": 65,
    "tenor_sax": 66,
    "oboe": 68,
    "clarinet": 71,
    "flute": 73,
    "pan_flute": 75,
    # Synth
    "lead_1_square": 80,
    "lead_2_sawtooth": 81,
    "pad_1_new_age": 88,
    "pad_2_warm": 89,
    # Percussion (channel 9 / 10)
    "drum_kit": 0,
}

# Friendly aliases used in prompts / API.
ALIASES: dict[str, str] = {
    "piano": "acoustic_grand_piano",
    "acoustic piano": "acoustic_grand_piano",
    "grand piano": "acoustic_grand_piano",
    "electric piano": "electric_piano_1",
    "epiano": "electric_piano_1",
    "guitar": "steel_guitar",
    "acoustic guitar": "steel_guitar",
    "electric guitar": "electric_guitar_clean",
    "bass": "electric_bass_finger",
    "electric bass": "electric_bass_finger",
    "strings": "string_ensemble_1",
    "violin": "violin",
    "flute": "flute",
    "synth": "lead_1_square",
    "synth lead": "lead_1_square",
    "drums": "drum_kit",
    "drum kit": "drum_kit",
    "drum": "drum_kit",
}

DRUM_CHANNEL = 9  # 0-based MIDI channel 10


def resolve_instrument_slug(name: str) -> str:
    """Return a canonical GM slug (or digit program string); raise if unknown."""
    raw = name.strip()
    key = raw.lower().replace("-", " ").replace(" ", "_")
    spaced = raw.lower().replace("_", " ").replace("-", " ")

    if key in GM_INSTRUMENTS:
        return key
    if spaced in ALIASES:
        return ALIASES[spaced]
    if key in ALIASES:
        return ALIASES[key]
    if raw.isdigit():
        value = int(raw)
        if 0 <= value <= 127:
            return raw

    raise ValueError(
        f"Unknown instrument '{name}'. "
        f"Try one of: {', '.join(sorted(set(ALIASES) | set(GM_INSTRUMENTS)))}"
    )


def get_program(name: str) -> int:
    """Resolve an instrument name (or alias) to a GM program number."""
    slug = resolve_instrument_slug(name)
    if slug.isdigit():
        return int(slug)
    return GM_INSTRUMENTS[slug]


def is_drum_instrument(name: str) -> bool:
    spaced = name.strip().lower().replace("_", " ").replace("-", " ")
    return spaced in {"drums", "drum", "drum kit"} or name.strip().lower() in {
        "drum_kit",
        "drums",
    }