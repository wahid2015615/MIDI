"""Generate sample MIDI files for testing / demos.

Text samples require the local GGUF model. Chords and notes are exact
(deterministic) and do not need the model.
"""

from __future__ import annotations

from pathlib import Path

from app.core.engine import MidiEngine
from app.features.generation.service import generate_from_chords, generate_from_prompt
from app.features.notes_to_midi.inputs import add_notes_from_lines

OUT = Path(__file__).resolve().parents[1] / "samples"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    engine = generate_from_prompt(
        "Generate a 16-bar uplifting piano melody in C Major at 128 BPM.",
        seed=7,
    )
    path = engine.export(OUT / "uplifting_piano.mid", file_type=1)
    print(f"Wrote {path} ({engine.duration_bars():.1f} bars @ {engine.bpm} BPM)")

    engine = generate_from_chords(
        "C | G | Am | F",
        bpm=120,
        add_melody=True,
        add_bass=True,
        add_drums=True,
    )
    path = engine.export(OUT / "chord_progression_cgamf.mid", file_type=1)
    print(f"Wrote {path} (exact chords — no AI)")

    engine = MidiEngine(bpm=100, key_signature="C")
    add_notes_from_lines(
        engine,
        [
            "C4 quarter",
            "E4 quarter",
            "G4 half",
            "rest quarter",
            "C5 quarter",
            "B4 quarter",
            "A4 half",
        ],
        instrument="acoustic_grand_piano",
    )
    path = engine.export(OUT / "note_list_example.mid", file_type=1)
    print(f"Wrote {path}")

    engine = generate_from_chords("Am - F - C - G", bpm=90, add_drums=False)
    path = engine.export(OUT / "sad_progression_type0.mid", file_type=0)
    print(f"Wrote {path} (Type 0)")

    print("Done. Open these .mid files in any DAW / MIDI player.")


if __name__ == "__main__":
    main()
