from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.engine import BPM_MAX, BPM_MIN
from app.shared.limits import NOTES_LINE_MAX_LENGTH, NOTES_MAX_LINES
from app.shared.schemas import (
    ExpressionOptions,
    FileType,
    TimeSignatureOptions,
    TimingOptions,
    TrackMixOptions,
    coerce_http_bpm,
)


class NotesGenerateRequest(BaseModel):
    notes: list[str] = Field(
        ...,
        min_length=1,
        max_length=NOTES_MAX_LINES,
        examples=[
            [
                "@track Melody acoustic_grand_piano",
                "C4 q",
                "E4 q",
                "G4 h",
                "rest q",
                "C5 q",
                "B4 q",
                "A4 h",
                "@track Bass electric_bass_finger",
                "C2 half",
                "G2 half",
            ]
        ],
    )
    bpm: float = Field(default=120, ge=BPM_MIN, le=BPM_MAX)
    key: str = "C Major"
    time_signature: TimeSignatureOptions | None = None
    instrument: str = "acoustic_grand_piano"
    mix: TrackMixOptions | None = None
    timing: TimingOptions | None = None
    expression: ExpressionOptions | None = None
    file_type: FileType = 1
    duplicate_score_meta: bool = Field(
        default=False,
        description=(
            "Type 1 only: also write tempo/time/key meta on every note track "
            "(web-player compatibility). Default False = SMF conductor-only."
        ),
    )
    seed: int | None = 42
    filename: str = "notes_output.mid"

    @field_validator("bpm", mode="before")
    @classmethod
    def _coerce_bpm(cls, value: object) -> object:
        return coerce_http_bpm(value)

    @field_validator("notes")
    @classmethod
    def _notes_not_blank(cls, value: list[str]) -> list[str]:
        meaningful: list[str] = []
        has_playable = False
        for line in value:
            if not isinstance(line, str):
                continue
            if len(line) > NOTES_LINE_MAX_LENGTH:
                raise ValueError(
                    f"Each notes line must be at most {NOTES_LINE_MAX_LENGTH} characters"
                )
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if stripped.startswith("#") and not lower.startswith("#track"):
                continue
            meaningful.append(stripped)
            if lower.startswith("@track") or lower.startswith("#track"):
                continue
            if lower.startswith("["):
                continue
            if lower.startswith("rest") or lower == "r" or lower.startswith("r "):
                continue
            # Likely a note / pitch token
            has_playable = True
        if not meaningful:
            raise ValueError(
                "notes must include at least one track directive or note/rest line"
            )
        if not has_playable:
            raise ValueError(
                "Note list has no playable notes — add lines like: C4 q"
            )
        return value
