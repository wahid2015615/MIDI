"""Canonical Mood and Style catalogs for MIDI generation."""

from __future__ import annotations

MOODS: tuple[str, ...] = (
    "Happy",
    "Sad",
    "Calm",
    "Energetic",
    "Epic",
    "Dark",
    "Romantic",
    "Hopeful",
    "Emotional",
    "Aggressive",
    "Mysterious",
    "Dreamy",
    "Cinematic",
    "Uplifting",
    "Relaxing",
    "Tense",
    "Melancholic",
    "Playful",
    "Nostalgic",
    "Inspirational",
)

STYLES: tuple[str, ...] = (
    "Pop",
    "Rock",
    "Hip Hop",
    "Trap",
    "EDM",
    "House",
    "Techno",
    "Lo-Fi",
    "Jazz",
    "Blues",
    "Classical",
    "Orchestral",
    "Cinematic",
    "Ambient",
    "Synthwave",
    "Funk",
    "R&B",
    "Country",
    "Folk",
    "Reggae",
)

DEFAULT_MOOD = "Happy"
DEFAULT_STYLE = "Pop"

# Optional BPM hints when a style is detected in free-text prompts
STYLE_BPM_HINTS: dict[str, float] = {
    "Pop": 120,
    "Rock": 128,
    "Hip Hop": 90,
    "Trap": 140,
    "EDM": 128,
    "House": 124,
    "Techno": 130,
    "Lo-Fi": 84,
    "Jazz": 110,
    "Blues": 90,
    "Classical": 100,
    "Orchestral": 96,
    "Cinematic": 100,
    "Ambient": 80,
    "Synthwave": 100,
    "Funk": 108,
    "R&B": 95,
    "Country": 112,
    "Folk": 100,
    "Reggae": 78,
}

# Optional mood pairing when only a style is inferred from a prompt
STYLE_DEFAULT_MOOD: dict[str, str] = {
    "Pop": "Happy",
    "Rock": "Energetic",
    "Hip Hop": "Playful",
    "Trap": "Dark",
    "EDM": "Energetic",
    "House": "Uplifting",
    "Techno": "Tense",
    "Lo-Fi": "Relaxing",
    "Jazz": "Relaxing",
    "Blues": "Melancholic",
    "Classical": "Cinematic",
    "Orchestral": "Epic",
    "Cinematic": "Cinematic",
    "Ambient": "Dreamy",
    "Synthwave": "Nostalgic",
    "Funk": "Playful",
    "R&B": "Romantic",
    "Country": "Hopeful",
    "Folk": "Nostalgic",
    "Reggae": "Calm",
}


def _norm_key(value: str) -> str:
    text = value.strip().lower().replace("_", " ").replace("-", " ")
    text = text.replace("&", " and ")
    return " ".join(text.split())


_MOOD_LOOKUP = {_norm_key(m): m for m in MOODS}
_STYLE_LOOKUP = {_norm_key(s): s for s in STYLES}
# Extra aliases commonly typed in prompts
_STYLE_LOOKUP.update(
    {
        "lofi": "Lo-Fi",
        "hiphop": "Hip Hop",
        "hip-hop": "Hip Hop",
        "rnb": "R&B",
        "r and b": "R&B",
        "synth wave": "Synthwave",
    }
)


def normalize_mood(value: str) -> str:
    """Return canonical mood label or raise ValueError."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("mood must be a non-empty string")
    canonical = _MOOD_LOOKUP.get(_norm_key(value))
    if canonical is None:
        raise ValueError(
            f"Unsupported mood {value!r}. "
            f"Allowed values: {', '.join(MOODS)}"
        )
    return canonical


def normalize_style(value: str) -> str:
    """Return canonical style label or raise ValueError."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("style must be a non-empty string")
    canonical = _STYLE_LOOKUP.get(_norm_key(value))
    if canonical is None:
        raise ValueError(
            f"Unsupported style {value!r}. "
            f"Allowed values: {', '.join(STYLES)}"
        )
    return canonical


def match_mood_in_text(text: str) -> str | None:
    """Find a mood mentioned as a whole word/phrase (longest labels first)."""
    padded = f" {_norm_key(text)} "
    for mood in sorted(MOODS, key=len, reverse=True):
        token = f" {_norm_key(mood)} "
        if token in padded:
            return mood
    return None


def match_style_in_text(text: str) -> str | None:
    """Find a style mentioned as a whole word/phrase (longest labels first)."""
    padded = f" {_norm_key(text)} "
    # Prefer longer aliases/labels so "hip hop" wins over bare fragments
    for key, style in sorted(_STYLE_LOOKUP.items(), key=lambda kv: len(kv[0]), reverse=True):
        token = f" {key} "
        if token in padded:
            return style
    return None
