from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.engine import MidiEngine
from app.features.generation.composer import key_signature_token
from app.features.notes_to_midi.inputs import add_notes_from_lines
from app.features.notes_to_midi.schemas import NotesGenerateRequest
from app.shared.http_errors import raise_generate_http
from app.shared.midi_response import (
    apply_expression_options,
    apply_score_meta,
    apply_timing,
    apply_track_mix,
    ensure_exportable,
    send_midi,
)

router = APIRouter(tags=["notes-to-midi"])


@router.post("/generate/notes")
def generate_notes(body: NotesGenerateRequest):
    try:
        instrument = body.instrument
        if body.mix and body.mix.instrument_melody:
            instrument = body.mix.instrument_melody
        ts = body.time_signature.as_tuple() if body.time_signature else (4, 4)
        engine = MidiEngine(
            bpm=body.bpm,
            time_signature=ts,
            key_signature=key_signature_token(body.key),
        )
        add_notes_from_lines(engine, body.notes, instrument=instrument)
        if not any(t.notes for t in engine.tracks):
            raise ValueError("No playable notes found in the note list")
        apply_score_meta(engine, time_signature=body.time_signature, key=body.key)
        apply_track_mix(engine, body.mix)
        apply_expression_options(engine, body.expression)
        apply_timing(engine, body.timing, seed=body.seed)
        ensure_exportable(engine)
        return send_midi(
            engine,
            body.filename,
            body.file_type,
            duplicate_score_meta=body.duplicate_score_meta,
        )
    except (ValueError, HTTPException) as exc:
        raise_generate_http(exc)
