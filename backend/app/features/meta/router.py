from __future__ import annotations

from fastapi import APIRouter

from app.core.catalog import (
    DEFAULT_MOOD,
    DEFAULT_STYLE,
    MOODS,
    STYLES,
    STYLE_BPM_HINTS,
    STYLE_DEFAULT_MOOD,
)
from app.core.engine import (
    BARS_DEFAULT,
    BARS_MAX,
    BARS_MIN,
    TS_NUMERATOR_MAX,
    TS_NUMERATOR_MIN,
    VALID_TS_DENOMINATORS,
)
from app.core.instruments import ALIASES, GM_INSTRUMENTS
from app.core.timing import COMMON_PPQ, GRID_BEATS, SWING_GRIDS
from app.features.generation.service import model_status

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/instruments")
def list_instruments() -> dict:
    return {
        "instruments": [
            {"id": key, "program": program, "label": key.replace("_", " ").title()}
            for key, program in GM_INSTRUMENTS.items()
        ],
        "aliases": ALIASES,
    }


@router.get("/styles")
def list_styles() -> dict:
    return {
        "styles": list(STYLES),
        "moods": list(MOODS),
        "default_mood": DEFAULT_MOOD,
        "default_style": DEFAULT_STYLE,
        "quantize_grids": list(GRID_BEATS.keys()),
        "swing_grids": list(SWING_GRIDS),
        "swing_mpc": {
            "min": 50,
            "max": 75,
            "straight": 50,
            "triplet_approx": 66,
            "note": "Studio uses MPC-style %; API TimingOptions.swing is delay fraction (mpc-50)/50",
        },
        "ppq_options": list(COMMON_PPQ),
        "bars": {"min": BARS_MIN, "max": BARS_MAX, "default": BARS_DEFAULT},
        "time_signature_numerator": {
            "min": TS_NUMERATOR_MIN,
            "max": TS_NUMERATOR_MAX,
        },
        "time_signature_denominators": list(VALID_TS_DENOMINATORS),
        "style_bpm_hints": STYLE_BPM_HINTS,
        "style_default_mood": STYLE_DEFAULT_MOOD,
    }


@router.get("/ai")
def ai_info() -> dict:
    return model_status()
