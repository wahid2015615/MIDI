from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.engine import BPM_MAX, BPM_MIN, BARS_MAX
from app.features.chords_to_midi.inputs import (
    parse_progression_string,
    validate_progression_chords,
)
from app.shared.limits import PROGRESSION_MAX_LENGTH
from app.shared.schemas import (
    ExpressionOptions,
    FileType,
    TimeSignatureOptions,
    TimingOptions,
    TrackMixOptions,
    coerce_http_bpm,
)


class ChordGenerateRequest(BaseModel):
    progression: str = Field(
        ...,
        min_length=1,
        max_length=PROGRESSION_MAX_LENGTH,
        examples=["C | G | Am | F"],
    )
    bpm: float = Field(default=120, ge=BPM_MIN, le=BPM_MAX)
    bars_per_chord: float = Field(
        default=1.0,
        ge=0.0625,
        le=16,
        description="Bars each chord spans (min 1/16 bar so rendered length is usable)",
    )
    key: str = "C Major"
    time_signature: TimeSignatureOptions | None = None
    instrument: str = "acoustic_grand_piano"
    add_chords: bool = True
    add_melody: bool = True
    add_bass: bool = True
    add_drums: bool = False
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
    filename: str = "chords_output.mid"

    @field_validator("progression")
    @classmethod
    def _progression_has_valid_chords(cls, value: str) -> str:
        chords = parse_progression_string(value)
        if not chords:
            raise ValueError("Progression has no chord symbols")
        validate_progression_chords(chords)
        return value

    @field_validator("bpm", mode="before")
    @classmethod
    def _coerce_bpm(cls, value: object) -> object:
        return coerce_http_bpm(value)

    @model_validator(mode="after")
    def _cap_total_bars(self) -> ChordGenerateRequest:
        chords = parse_progression_string(self.progression)
        total = len(chords) * float(self.bars_per_chord)
        if total > BARS_MAX:
            raise ValueError(
                f"Chord progression spans {total:g} bars "
                f"(len={len(chords)} × bars_per_chord={self.bars_per_chord:g}); "
                f"maximum is {BARS_MAX} bars"
            )
        return self
