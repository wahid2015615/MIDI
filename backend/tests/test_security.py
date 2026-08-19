"""Security tests: API token, probe gate, filename, input caps, CORS."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.shared import security as sec
from app.shared.midi_response import safe_filename


def test_wrong_token_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("MIDIGEN_API_TOKEN", "correct-token")
    from app.main import app

    with TestClient(app) as client:
        res = client.post(
            "/generate/text",
            json={"prompt": "hello piano 8 bars"},
            headers={"X-MIDI-Token": "wrong-token"},
        )
        assert res.status_code == 401


def test_bearer_token_accepted_for_text(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("MIDIGEN_API_TOKEN", "secret-token")
    from app.core.engine import MidiEngine, NoteEvent
    from app.features.generation import service as gen_service
    from app.main import app
    import app.features.text_to_midi.router as text_router

    engine = MidiEngine(bpm=120)
    track = engine.add_track("Melody", channel=0, instrument="acoustic_grand_piano")
    track.notes.append(NoteEvent(60, 0.0, 1.0, 80))

    def _fake_generate(*_a, **_k):
        return engine

    monkeypatch.setattr(gen_service, "generate_from_prompt", _fake_generate)
    monkeypatch.setattr(text_router, "generate_from_prompt", _fake_generate)

    with TestClient(app) as client:
        res = client.post(
            "/generate/text",
            json={
                "prompt": "hello piano 8 bars",
                "expression": {
                    "sustain": False,
                    "modulation": False,
                    "pitch_bend": False,
                },
                "timing": {"humanize": False, "swing": 0, "ppq": 480},
            },
            headers={"Authorization": "Bearer secret-token"},
        )
        assert res.status_code == 200
        assert res.content[:4] == b"MThd"


def test_chords_remain_open_when_token_set(monkeypatch: pytest.MonkeyPatch):
    """Chords/Notes stay unauthenticated (Studio local use)."""
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("MIDIGEN_API_TOKEN", "secret-token")
    from app.main import app

    with TestClient(app) as client:
        res = client.post(
            "/generate/chords",
            json={
                "progression": "C | G",
                "add_melody": False,
                "add_chords": True,
                "add_bass": False,
                "add_drums": False,
                "expression": {
                    "sustain": False,
                    "modulation": False,
                    "pitch_bend": False,
                },
                "timing": {"humanize": False, "swing": 0, "ppq": 480},
            },
        )
        assert res.status_code == 200
        assert res.content[:4] == b"MThd"


def test_probe_forbidden_for_remote_client_when_exposed(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.delenv("MIDIGEN_API_TOKEN", raising=False)
    monkeypatch.setattr(sec, "client_is_loopback", lambda _req: False)
    from app.main import app

    with TestClient(app) as client:
        res = client.get("/health?probe=1")
        assert res.status_code == 403


def test_health_without_probe_stays_public(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.delenv("MIDIGEN_API_TOKEN", raising=False)
    from app.main import app

    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


def test_filename_injection_sanitized_on_chords(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.delenv("MIDIGEN_API_TOKEN", raising=False)
    from app.main import app

    nasty = '../../evil; filename="hack.mid'
    with TestClient(app) as client:
        res = client.post(
            "/generate/chords",
            json={
                "progression": "C | Am",
                "add_melody": False,
                "add_chords": True,
                "add_bass": False,
                "add_drums": False,
                "filename": nasty,
                "expression": {
                    "sustain": False,
                    "modulation": False,
                    "pitch_bend": False,
                },
                "timing": {"humanize": False, "swing": 0, "ppq": 480},
            },
        )
        assert res.status_code == 200
        disp = res.headers.get("content-disposition", "")
        cleaned = safe_filename(nasty)
        assert ".." not in cleaned
        assert "/" not in cleaned
        assert "\\" not in cleaned
        assert cleaned.endswith(".mid")
        assert ".." not in disp
        assert "filename=" in disp.lower()


def test_oversized_parse_prompt_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.delenv("MIDIGEN_API_TOKEN", raising=False)
    from app.main import app

    with TestClient(app) as client:
        res = client.post("/parse/text", json={"prompt": "x" * 8001})
        assert res.status_code == 422
