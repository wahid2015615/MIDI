from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.features.chords_to_midi.schemas import ChordGenerateRequest
from app.features.generation.ai_client import AIMusicError
from app.features.generation.service import generate_from_chords
from app.shared.http_errors import raise_generate_http
from app.shared.midi_response import (
    apply_expression_options,
    apply_score_meta,
    apply_timing,
    apply_track_mix,
    apply_track_selection,
    ensure_exportable,
    send_midi,
)

router = APIRouter(tags=["chords-to-midi"])


@router.post("/generate/chords")
def generate_chords(body: ChordGenerateRequest):
    try:
        print("[MIDIgen] POST /generate/chords — request received", flush=True)
        if not any(
            (body.add_chords, body.add_melody, body.add_bass, body.add_drums)
        ):
            raise HTTPException(
                status_code=400,
                detail="Enable at least one track role before generating",
            )
        mix = body.mix
        melody_inst = body.instrument
        if mix and mix.instrument_melody:
            melody_inst = mix.instrument_melody
        ts = body.time_signature.as_tuple() if body.time_signature else None
        engine = generate_from_chords(
            body.progression,
            bpm=body.bpm,
            bars_per_chord=body.bars_per_chord,
            add_chords=body.add_chords,
            add_melody=body.add_melody,
            add_bass=body.add_bass,
            add_drums=body.add_drums,
            key=body.key,
            time_signature=ts,
            melody_instrument=melody_inst,
            instrument_chords=(
                mix.instrument_chords if mix and mix.instrument_chords else "electric_piano_1"
            ),
            instrument_bass=(
                mix.instrument_bass if mix and mix.instrument_bass else "electric_bass_finger"
            ),
            instrument_drums=(
                mix.instrument_drums if mix and mix.instrument_drums else "drum_kit"
            ),
            seed=body.seed,
        )
        apply_score_meta(engine, time_signature=body.time_signature, key=body.key)
        apply_track_mix(engine, body.mix)
        apply_track_selection(
            engine,
            include_melody=body.add_melody,
            include_chords=body.add_chords,
            include_bass=body.add_bass,
            include_drums=body.add_drums,
        )
        apply_expression_options(engine, body.expression)
        apply_timing(engine, body.timing, seed=body.seed)
        ensure_exportable(engine)
        return send_midi(
            engine,
            body.filename,
            body.file_type,
            duplicate_score_meta=body.duplicate_score_meta,
        )
    except (AIMusicError, ValueError, OverflowError, HTTPException) as exc:
        raise_generate_http(exc)
