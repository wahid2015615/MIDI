"""Command-line interface for MIDI generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.core.engine import MidiEngine
from app.features.generation.service import generate_from_chords, generate_from_prompt
from app.features.notes_to_midi.inputs import add_notes_from_lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MIDI Generation Module")
    sub = parser.add_subparsers(dest="command", required=True)

    p_text = sub.add_parser("text", help="Generate MIDI from a text prompt")
    p_text.add_argument("prompt", type=str)
    p_text.add_argument("-o", "--output", default="samples/text_output.mid")
    p_text.add_argument("--type", dest="file_type", type=int, choices=[0, 1], default=1)
    p_text.add_argument("--seed", type=int, default=42)

    p_chords = sub.add_parser("chords", help="Generate MIDI from a chord progression")
    p_chords.add_argument("progression", type=str)
    p_chords.add_argument("-o", "--output", default="samples/chords_output.mid")
    p_chords.add_argument("--bpm", type=float, default=120)
    p_chords.add_argument("--melody", action="store_true", default=True)
    p_chords.add_argument("--no-melody", action="store_false", dest="melody")
    p_chords.add_argument("--bass", action="store_true", default=True)
    p_chords.add_argument("--no-bass", action="store_false", dest="bass")
    p_chords.add_argument("--drums", action="store_true")
    p_chords.add_argument("--type", dest="file_type", type=int, choices=[0, 1], default=1)

    p_notes = sub.add_parser("notes", help="Generate MIDI from a notes file")
    p_notes.add_argument("file", type=str)
    p_notes.add_argument("-o", "--output", default="samples/notes_output.mid")
    p_notes.add_argument("--bpm", type=float, default=120)
    p_notes.add_argument("--instrument", default="acoustic_grand_piano")
    p_notes.add_argument("--type", dest="file_type", type=int, choices=[0, 1], default=1)

    p_serve = sub.add_parser("serve", help="Run FastAPI server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.command == "text":
        engine = generate_from_prompt(args.prompt, seed=args.seed)
        print(f"Saved: {engine.export(args.output, file_type=args.file_type)}")
    elif args.command == "chords":
        engine = generate_from_chords(
            args.progression,
            bpm=args.bpm,
            add_melody=args.melody,
            add_bass=args.bass,
            add_drums=args.drums,
        )
        print(f"Saved: {engine.export(args.output, file_type=args.file_type)}")
    elif args.command == "notes":
        lines = Path(args.file).read_text(encoding="utf-8").splitlines()
        engine = MidiEngine(bpm=args.bpm)
        add_notes_from_lines(engine, lines, instrument=args.instrument)
        print(f"Saved: {engine.export(args.output, file_type=args.file_type)}")
    elif args.command == "serve":
        import os

        import uvicorn

        reload = os.getenv("UVICORN_RELOAD", "0") == "1"
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=reload,
        )


if __name__ == "__main__":
    main()
