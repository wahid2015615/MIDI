from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.engine import (
    TS_NUMERATOR_MAX,
    TS_NUMERATOR_MIN,
    VALID_TS_DENOMINATORS,
    normalize_time_signature,
)


class TrackOptions(BaseModel):
    melody: bool = True
    chords: bool = True
    bass: bool = True
    drums: bool = False


class TrackMixOptions(BaseModel):
    """Per-role mute/solo/volume/pan/instrument/channel applied after generation."""

    mute_melody: bool = False
    mute_chords: bool = False
    mute_bass: bool = False
    mute_drums: bool = False
    solo_melody: bool = False
    solo_chords: bool = False
    solo_bass: bool = False
    solo_drums: bool = False
    volume_melody: int = Field(default=100, ge=0, le=127)
    volume_chords: int = Field(default=90, ge=0, le=127)
    volume_bass: int = Field(default=100, ge=0, le=127)
    volume_drums: int = Field(default=100, ge=0, le=127)
    pan_melody: int = Field(default=64, ge=0, le=127)
    pan_chords: int = Field(default=64, ge=0, le=127)
    pan_bass: int = Field(default=64, ge=0, le=127)
    pan_drums: int = Field(default=64, ge=0, le=127)
    instrument_melody: str | None = Field(
        default=None, examples=["acoustic_grand_piano"]
    )
    instrument_chords: str | None = Field(default=None, examples=["electric_piano_1"])
    instrument_bass: str | None = Field(
        default=None, examples=["electric_bass_finger"]
    )
    instrument_drums: str | None = Field(default=None, examples=["drum_kit"])
    # None = keep engine auto-assigned channel; 0-15 = override (drums usually 9)
    channel_melody: int | None = Field(default=None, ge=0, le=15)
    channel_chords: int | None = Field(default=None, ge=0, le=15)
    channel_bass: int | None = Field(default=None, ge=0, le=15)
    channel_drums: int | None = Field(default=None, ge=0, le=15)


class TimingOptions(BaseModel):
    quantize: str | None = Field(default="1/16", examples=["1/16", "1/8", None])
    quantize_duration: bool = Field(
        default=True,
        description="When quantizing, also snap note durations to the grid",
    )
    swing: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Off-beat delay fraction of one swing-grid step (0=straight, "
            "~0.33=triplet). Studio sends MPC-style 50–100% converted via "
            "(mpc-50)/50. Not raw MPC percent."
        ),
        examples=[0.0, 0.33, 0.5],
    )
    swing_grid: str = Field(
        default="1/8",
        description="Grid used for swing pairs (typically 1/8 or 1/16)",
        examples=["1/8", "1/16"],
    )
    humanize: bool = False
    humanize_timing: float = Field(
        default=0.02,
        ge=0.0,
        le=0.25,
        description="Max random start-time jitter in beats",
    )
    humanize_velocity: int = Field(
        default=8,
        ge=0,
        le=64,
        description="Max random velocity jitter",
    )
    humanize_duration: float = Field(
        default=0.01,
        ge=0.0,
        le=0.25,
        description="Max random duration jitter in beats",
    )
    humanize_controllers: bool = Field(
        default=False,
        description="Also humanize CC and pitch-bend event times (sustain pairs stay ordered)",
    )
    ppq: int = Field(
        default=480,
        ge=24,
        le=9600,
        description="Pulses Per Quarter Note (ticks_per_beat) for MIDI export",
        examples=[96, 192, 240, 480, 960],
    )
    seed: int | None = Field(
        default=None,
        description="RNG seed for humanization (falls back to request seed)",
    )


class ExpressionOptions(BaseModel):
    """Extra MIDI expression written into the .mid file.

    Boolean toggles enable generation. Optional numeric fields customize the
    automation pattern; defaults match the historical hardcoded behaviour.
    """

    sustain: bool = Field(
        default=True,
        description="Write sustain pedal (CC64) on melody/chords/piano-like tracks",
    )
    modulation: bool = Field(
        default=True,
        description="Write modulation wheel (CC1) accents on melody",
    )
    pitch_bend: bool = Field(
        default=True,
        description="Write pitch bend data (center + optional lead scoops)",
    )

    # Sustain (CC64) — defaults: 127 down / 0 up, hold 92% of each bar
    sustain_on_value: int = Field(default=127, ge=0, le=127)
    sustain_off_value: int = Field(default=0, ge=0, le=127)
    sustain_hold_ratio: float = Field(
        default=0.92,
        ge=0.05,
        le=1.0,
        description="Fraction of each bar the pedal stays down (0.92 = legacy)",
    )

    # Modulation (CC1) — defaults: peak 24 every 2 bars, accent lasts 0.5 bar
    modulation_value: int = Field(
        default=24,
        ge=0,
        le=127,
        description="Peak CC1 intensity for melody accents",
    )
    modulation_interval_bars: float = Field(
        default=2.0,
        ge=0.25,
        le=32.0,
        description="Bars between modulation accents",
    )
    modulation_accent_ratio: float = Field(
        default=0.5,
        ge=0.05,
        le=4.0,
        description="Accent length as a fraction of one bar",
    )

    # Pitch bend — defaults: scoop 400 below center every 4 bars over 0.25 beats
    pitch_bend_scoop_depth: int = Field(
        default=400,
        ge=0,
        le=8191,
        description="How far below center (8192) each lead scoop starts",
    )
    pitch_bend_interval_bars: float = Field(
        default=4.0,
        ge=0.25,
        le=32.0,
        description="Bars between pitch-bend scoops on lead/synth melody",
    )
    pitch_bend_scoop_beats: float = Field(
        default=0.25,
        ge=0.05,
        le=4.0,
        description="Duration of the scoop back to center, in beats",
    )


FileType = Literal[0, 1]


class TimeSignatureOptions(BaseModel):
    """MIDI time signature (numerator / denominator)."""

    numerator: int = Field(
        default=4,
        ge=TS_NUMERATOR_MIN,
        le=TS_NUMERATOR_MAX,
        description=f"Beats per bar ({TS_NUMERATOR_MIN}–{TS_NUMERATOR_MAX})",
    )
    denominator: int = Field(
        default=4,
        description=f"Note value that gets the beat; one of {VALID_TS_DENOMINATORS}",
    )

    @field_validator("numerator", mode="before")
    @classmethod
    def _numerator_int(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("numerator must be an integer")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError("numerator must be an integer")
        return int(value)

    @field_validator("denominator", mode="before")
    @classmethod
    def _denominator_allowed(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("denominator must be an integer")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError("denominator must be an integer")
        den = int(value)
        if den not in VALID_TS_DENOMINATORS:
            raise ValueError(
                f"time_signature.denominator must be one of {VALID_TS_DENOMINATORS}"
            )
        return den

    def as_tuple(self) -> tuple[int, int]:
        return normalize_time_signature(self.numerator, self.denominator)
