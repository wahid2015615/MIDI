"""Shared HTTP error mapping for generate routers."""

from __future__ import annotations

from fastapi import HTTPException

from app.features.generation.ai_client import AIMusicError


def raise_generate_http(exc: BaseException) -> None:
    """Map known domain errors to 4xx/503; re-raise unexpected as-is (→500)."""
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, AIMusicError):
        status = 499 if "cancelled" in str(exc).lower() else 503
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    if isinstance(exc, (ValueError, OverflowError)):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Unexpected: let FastAPI return 500 with traceback in logs
    raise exc
