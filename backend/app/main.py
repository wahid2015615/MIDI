from __future__ import annotations

import logging
import os
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.features.chords_to_midi.router import router as chords_router
from app.features.meta.router import router as meta_router
from app.features.notes_to_midi.router import router as notes_router
from app.features.text_to_midi.router import router as text_router
from app.shared.security import (
    api_token,
    bind_host,
    bind_is_loopback,
    require_model_probe_allowed,
)

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
    """LAN regex only on loopback bind unless CORS_ORIGIN_REGEX is set explicitly.

    When HOST is non-loopback (e.g. 0.0.0.0), default private-LAN regex is off —
    set CORS_ORIGINS and/or CORS_ORIGIN_REGEX deliberately for LAN/deploy.
    Empty CORS_ORIGIN_REGEX disables the regex.
    """
    if "CORS_ORIGIN_REGEX" in os.environ:
        value = os.environ["CORS_ORIGIN_REGEX"].strip()
        return value or None
    if bind_is_loopback():
        return _DEFAULT_ORIGIN_REGEX
    return None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    if not bind_is_loopback() and not api_token():
        logger.warning(
            "HOST=%s is non-loopback and MIDIGEN_API_TOKEN is unset — "
            "text generate and probes are open on the network. "
            "Set MIDIGEN_API_TOKEN and tighten CORS_ORIGINS for deploy.",
            bind_host(),
        )
    if not bind_is_loopback() and "CORS_ORIGIN_REGEX" not in os.environ:
        logger.info(
            "Default LAN CORS regex disabled (non-loopback HOST). "
            "Set CORS_ORIGINS and/or CORS_ORIGIN_REGEX for Studio access."
        )
    yield


app = FastAPI(
    title="MIDI Generation API",
    description="Generate Standard MIDI files using a local GGUF model.",
    version=__version__,
    lifespan=_lifespan,
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
    return response


app.include_router(text_router)
app.include_router(chords_router)
app.include_router(notes_router)
app.include_router(meta_router)


@app.get("/health")
def health(request: Request, probe: bool = False) -> dict:
    """Liveness. Pass probe=1 to load/check the local GGUF model."""
    from app.features.generation.ai_client import model_status as ai_status

    if probe:
        require_model_probe_allowed(request)
    return {
        "status": "ok",
        "version": __version__,
        "ai": ai_status(probe=probe),
    }
