"""Optional API token + bind/CORS helpers for local vs exposed deployments."""

from __future__ import annotations

import os

from fastapi import HTTPException, Request


def bind_host() -> str:
    return (os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1").lower()


def bind_is_loopback() -> bool:
    host = bind_host()
    return host in ("127.0.0.1", "localhost", "::1")


def api_token() -> str | None:
    raw = (os.getenv("MIDIGEN_API_TOKEN") or "").strip()
    return raw or None


def request_token(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        return token or None
    header = (request.headers.get("x-midi-token") or "").strip()
    return header or None


def client_is_loopback(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    return host in ("127.0.0.1", "::1", "localhost")


def require_api_token_if_configured(request: Request) -> None:
    """When MIDIGEN_API_TOKEN is set, require matching Bearer / X-MIDI-Token."""
    expected = api_token()
    if not expected:
        return
    if request_token(request) != expected:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API token (Authorization: Bearer … or X-MIDI-Token)",
        )


def require_model_probe_allowed(request: Request) -> None:
    """Gate health?probe=1 — token if configured, else localhost-only when exposed."""
    require_api_token_if_configured(request)
    if api_token():
        return
    if client_is_loopback(request):
        return
    if bind_is_loopback():
        return
    raise HTTPException(
        status_code=403,
        detail=(
            "Model probe is disabled for remote clients when HOST is non-loopback. "
            "Call from localhost or set MIDIGEN_API_TOKEN."
        ),
    )


def require_expensive_ai_allowed(request: Request) -> None:
    """Gate text generate / preview when MIDIGEN_API_TOKEN is configured."""
    require_api_token_if_configured(request)
