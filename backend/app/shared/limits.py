"""Shared request-size limits for generate / parse endpoints."""

from __future__ import annotations

# Keep generate prompt aligned with POST /parse/text.
PROMPT_MAX_LENGTH = 8000
PROGRESSION_MAX_LENGTH = 4000
NOTES_MAX_LINES = 2000
NOTES_LINE_MAX_LENGTH = 500
CLIENT_REQUEST_ID_MAX_LENGTH = 128
