from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.features.chords_to_midi.router import router as chords_router
from app.features.meta.router import router as meta_router
from app.features.notes_to_midi.router import router as notes_router
from app.features.text_to_midi.router import router as text_router

logger = logging.getLogger("midigen.api")

_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]

# Localhost + common private LAN origins (Next.js on another machine)
_DEFAULT_ORIGIN_REGEX = (
    r"https?://("
    r"localhost|127\.0\.0\.1|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
    r")(:\d+)?$"
)


def _cors_origins() -> list[str]:
    """Local defaults plus optional CORS_ORIGINS (comma-separated) for deploy."""
    extra = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    seen: set[str] = set()
    origins: list[str] = []
    for origin in [*_DEFAULT_ORIGINS, *extra]:
        if origin not in seen:
            seen.add(origin)
            origins.append(origin)
    return origins


def _cors_origin_regex() -> str | None:
    """Optional regex. Empty CORS_ORIGIN_REGEX disables; unset uses LAN default."""
    if "CORS_ORIGIN_REGEX" in os.environ:
        value = os.environ["CORS_ORIGIN_REGEX"].strip()
        return value or None
    return _DEFAULT_ORIGIN_REGEX


app = FastAPI(
    title="MIDI Generation API",
    description="Generate Standard MIDI files using a local GGUF model.",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "%s %s -> %s (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    print(
        f"{request.method} {request.url.path} -> {response.status_code} ({elapsed_ms:.1f} ms)",
        flush=True,
    )
    return response


app.include_router(text_router)
app.include_router(chords_router)
app.include_router(notes_router)
app.include_router(meta_router)


@app.get("/health")
def health(probe: bool = False) -> dict:
    """Liveness. Pass probe=1 to load/check the local GGUF model."""
    from app.features.generation.ai_client import model_status as ai_status

    return {
        "status": "ok",
        "version": __version__,
        "ai": ai_status(probe=probe),
    }
