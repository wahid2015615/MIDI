from __future__ import annotations

import re

from app.core.theory import parse_chord_symbol


def _repair_dash_fragments(parts: list[str]) -> list[str]:
    """Rejoin quality-only fragments created by naive '-' splits (e.g. C-7 → C, 7)."""
    repaired: list[str] = []
    for part in parts:
        token = part.strip().strip(",").strip("|").strip()
        if not token:
            continue
        # Fragments that do not start with a pitch-class letter belong to the
        # previous chord (jazz hyphen: C-7 after an overly aggressive split).
        if repaired and not re.match(r"^[A-Ga-g]", token):
            repaired[-1] = f"{repaired[-1]}-{token}"
        else:
            repaired.append(token)
    return repaired


def _expand_mixed_separators(parts: list[str]) -> list[str]:
    """After a primary split, also split leftover spaced dashes / commas."""
    expanded: list[str] = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        if re.search(r"\s-\s", text):
            expanded.extend(re.split(r"\s+-\s+", text))
        elif "," in text:
            expanded.extend(text.split(","))
        else:
            expanded.append(text)
    return expanded


def parse_progression_string(text: str) -> list[str]:
    """Split a progression string into chord tokens (no validation).

    Supported separators (priority order):
      |  pipe / bar   e.g. C | G | Am | F  or  | C | G | Am | F |
      -  dash / arrow  e.g. C - G - Am - F, C -> G, C → G
         Jazz hyphens inside symbols (C-7) are preserved when separators are
         spaced (``C-7 - F-7``) or repaired after unspaced splits.
      ,  comma         e.g. C, G, Am, F
      whitespace / newlines  e.g. C G Am F  or one chord per line

    Mixed separators after a primary ``|`` split (e.g. ``C | G - Am | F``)
    are also expanded so inner spaced dashes / commas become separate chords.
    """
    text = text.replace("→", "->")
    text = text.replace("–", "-").replace("—", "-")

    if "|" in text:
        raw_parts = _expand_mixed_separators(text.split("|"))
    elif "->" in text:
        raw_parts = _expand_mixed_separators(re.split(r"\s*->\s*", text))
    elif re.search(r"\s-\s", text):
        # Spaced dashes: safe for jazz C-7 - F-7
        raw_parts = re.split(r"\s+-\s+", text)
    elif "," in text:
        raw_parts = text.split(",")
    elif "-" in text:
        # Unspaced classic C-G-Am; repair C-7 → C + 7 fragments
        return _repair_dash_fragments(text.split("-"))
    else:
        raw_parts = text.split()

    chords: list[str] = []
    for part in raw_parts:
        token = part.strip().strip(",").strip("|").strip()
        if token:
            chords.append(token)
    return chords


def validate_progression_chords(chords: list[str]) -> None:
    """Raise ValueError if any token is not a supported chord symbol."""
    bad: list[str] = []
    for symbol in chords:
        try:
            parse_chord_symbol(symbol)
        except ValueError:
            bad.append(symbol)
    if bad:
        raise ValueError(
            "Invalid chord(s): "
            + ", ".join(bad)
            + ". Use symbols like C, Am, G7, Dm7, Cmaj7."
        )
