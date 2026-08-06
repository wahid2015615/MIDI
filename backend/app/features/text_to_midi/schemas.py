from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.catalog import (
    DEFAULT_MOOD,
    DEFAULT_STYLE,
    MOODS,
    STYLES,
    normalize_mood,
    normalize_style,
)
from app.core.engine import BPM_MAX, BPM_MIN, BARS_DEFAULT, BARS_MAX, BARS_MIN
from app.shared.schemas import (
    ExpressionOptions,
    FileType,
    TimeSignatureOptions,
    TimingOptions,
    TrackMixOptions,
    TrackOptions,
)


class TextGenerateRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        examples=["Generate a 16-bar uplifting piano melody in C Major at 128 BPM."],
    )
    bpm: float | None = Field(default=None, ge=BPM_MIN, le=BPM_MAX)
    bars: int | None = Field(
        default=None,
        ge=BARS_MIN,
        le=BARS_MAX,
        description=f"Number of bars ({BARS_MIN}–{BARS_MAX}; default {BARS_DEFAULT})",
    )
    key: str | None = None
    time_signature: TimeSignatureOptions | None = None
    mood: str | None = Field(
        default=None,
        description=f"One of: {', '.join(MOODS)} (default {DEFAULT_MOOD})",
    )
    style: str | None = Field(
        default=None,
        description=f"One of: {', '.join(STYLES)} (default {DEFAULT_STYLE})",
    )
    instrument: str | None = None
    tracks: TrackOptions | None = None
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
    filename: str = "generated.mid"

    @field_validator("prompt", mode="before")
    @classmethod
    def _normalize_prompt(cls, value: object) -> str:
        if value is None:
            raise ValueError("prompt is required")
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("prompt must not be empty")
        return cleaned

    @field_validator("mood")
    @classmethod
    def _validate_mood(cls, value: str | None) -> str | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return normalize_mood(value)

    @field_validator("style")
    @classmethod
    def _validate_style(cls, value: str | None) -> str | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return normalize_style(value)
