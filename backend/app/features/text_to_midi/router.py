from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.features.generation.ai_client import AIMusicError
from app.features.generation.service import (
    generate_from_prompt,
    parse_text_prompt_detailed,
)
from app.features.text_to_midi.schemas import TextGenerateRequest
from app.shared.http_errors import raise_generate_http
from app.shared.midi_response import (
    apply_expression_options,
    apply_score_meta,
    apply_timing,
    apply_track_mix,
    apply_track_selection,
    engine_meta,
    ensure_exportable,
    send_midi,
)


router = APIRouter(tags=["text-to-midi"])


@router.post("/generate/cancel")
def cancel_generate(body: dict | None = None) -> dict[str, bool]:
    """Best-effort abort of in-flight local-model generation.

    Optional JSON body ``{"client_request_id": "..."}`` cancels only that
    request. Omitted / empty cancels all currently registered generates.
    Cancel is observed at AI checkpoints (before/after llama.cpp completion);
    mid-inference CPU work may finish before the HTTP call returns 499.
    """
    from app.features.generation.ai_client import request_generation_cancel

    client_request_id = None
    if isinstance(body, dict):
        raw = body.get("client_request_id")
        if raw is not None:
            cleaned = str(raw).strip()
            client_request_id = cleaned or None
    request_generation_cancel(client_request_id)
    return {"cancelled": True}


def _ts_tuple(body: TextGenerateRequest) -> tuple[int, int] | None:
    if body.time_signature is None:
        return None
    return body.time_signature.as_tuple()


def _role_flags(body: TextGenerateRequest) -> tuple[bool | None, bool | None, bool | None, bool | None]:
    include_melody = None if body.tracks is None else body.tracks.melody
    include_chords = None if body.tracks is None else body.tracks.chords
    include_bass = None if body.tracks is None else body.tracks.bass
    include_drums = None if body.tracks is None else body.tracks.drums
    return include_melody, include_chords, include_bass, include_drums


def _require_at_least_one_role(body: TextGenerateRequest) -> None:
    if body.tracks is None:
        return
    if not any(
        (body.tracks.melody, body.tracks.chords, body.tracks.bass, body.tracks.drums)
    ):
        raise HTTPException(
            status_code=400,
            detail="Enable at least one track role before generating",
        )


@router.post("/generate/text")
def generate_text(body: TextGenerateRequest):
    try:
        print("[MIDIgen] POST /generate/text — request received", flush=True)
        _require_at_least_one_role(body)
        mix = body.mix
        melody_inst = body.instrument
        if mix and mix.instrument_melody:
            melody_inst = mix.instrument_melody
        include_melody, include_chords, include_bass, include_drums = _role_flags(body)
        engine = generate_from_prompt(
            body.prompt,
            seed=body.seed,
            bpm=body.bpm,
            bars=body.bars,
            key=body.key,
            time_signature=_ts_tuple(body),
            mood=body.mood,
            style=body.style,
            instrument=melody_inst,
            include_chords=include_chords,
            include_bass=include_bass,
            include_drums=include_drums,
            include_melody=include_melody,
            instrument_chords=None if mix is None else mix.instrument_chords,
            instrument_bass=None if mix is None else mix.instrument_bass,
            instrument_drums=None if mix is None else mix.instrument_drums,
            client_request_id=body.client_request_id,
        )
        apply_score_meta(engine, time_signature=body.time_signature, key=body.key)
        apply_track_mix(engine, body.mix)
        apply_track_selection(
            engine,
            include_melody=include_melody,
            include_chords=include_chords,
            include_bass=include_bass,
            include_drums=include_drums,
        )
        # Expression before timing so auto CC/PB get quantize / swing / humanize
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


@router.post("/generate/text/preview")
def generate_text_preview(body: TextGenerateRequest) -> dict:
    try:
        _require_at_least_one_role(body)
        mix = body.mix
        melody_inst = body.instrument
        if mix and mix.instrument_melody:
            melody_inst = mix.instrument_melody
        include_melody, include_chords, include_bass, include_drums = _role_flags(body)
        engine = generate_from_prompt(
            body.prompt,
            seed=body.seed,
            bpm=body.bpm,
            bars=body.bars,
            key=body.key,
            time_signature=_ts_tuple(body),
            mood=body.mood,
            style=body.style,
            instrument=melody_inst,
            include_chords=include_chords,
            include_bass=include_bass,
            include_drums=include_drums,
            include_melody=include_melody,
            instrument_chords=None if mix is None else mix.instrument_chords,
            instrument_bass=None if mix is None else mix.instrument_bass,
            instrument_drums=None if mix is None else mix.instrument_drums,
            client_request_id=body.client_request_id,
        )
        apply_score_meta(engine, time_signature=body.time_signature, key=body.key)
        apply_track_mix(engine, body.mix)
        apply_track_selection(
            engine,
            include_melody=include_melody,
            include_chords=include_chords,
            include_bass=include_bass,
            include_drums=include_drums,
        )
        apply_expression_options(engine, body.expression)
        apply_timing(engine, body.timing, seed=body.seed)
        ensure_exportable(engine)
        return engine_meta(engine)
    except (AIMusicError, ValueError, OverflowError, HTTPException) as exc:
        raise_generate_http(exc)


class TextParseRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)

    @field_validator("prompt", mode="before")
    @classmethod
    def _normalize_prompt(cls, value: object) -> str:
        if value is None:
            raise ValueError("prompt is required")
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("prompt must not be empty")
        return cleaned


@router.post("/parse/text")
def parse_text(body: TextParseRequest) -> dict:
    result = parse_text_prompt_detailed(body.prompt)
    spec = result.spec
    return {
        "bars": spec.bars,
        "bpm": spec.bpm,
        "key": spec.key,
        "mood": spec.mood,
        "style": spec.style,
        "instrument": spec.instrument,
        "include_chords": spec.include_chords,
        "include_bass": spec.include_bass,
        "include_drums": spec.include_drums,
        "time_signature": {
            "numerator": spec.time_signature[0],
            "denominator": spec.time_signature[1],
        },
        "detected": result.detected,
    }
