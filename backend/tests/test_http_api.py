"""HTTP contract tests (TestClient) — no GGUF required."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    # Keep bind loopback so default CORS regex / probe gates behave as local.
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.delenv("MIDIGEN_API_TOKEN", raising=False)
    # Import after env so module-level CORS helpers see HOST if re-evaluated.
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_health_ok_without_probe(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "ai" in data


def test_cancel_empty_body(client: TestClient):
    res = client.post("/generate/cancel", json={})
    assert res.status_code == 200
    assert res.json() == {"cancelled": True}


def test_cancel_with_request_id(client: TestClient):
    res = client.post(
        "/generate/cancel",
        json={"client_request_id": "req-abc"},
    )
    assert res.status_code == 200
    assert res.json()["cancelled"] is True


def test_parse_text_ok(client: TestClient):
    res = client.post(
        "/parse/text",
        json={"prompt": "sad piano in A Minor 90 BPM 8 bars"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "detected" in data
    assert "bpm" in data


def test_prompt_too_long_rejected(client: TestClient):
    res = client.post(
        "/generate/text",
        json={"prompt": "x" * 8001},
    )
    assert res.status_code == 422


def test_progression_too_long_rejected(client: TestClient):
    res = client.post(
        "/generate/chords",
        json={"progression": "C " * 4001},
    )
    assert res.status_code == 422


def test_notes_too_many_lines_rejected(client: TestClient):
    res = client.post(
        "/generate/notes",
        json={"notes": ["C4 q"] * 2001},
    )
    assert res.status_code == 422


def test_generate_chords_download(client: TestClient):
    res = client.post(
        "/generate/chords",
        json={
            "progression": "C | G | Am | F",
            "add_melody": True,
            "add_chords": True,
            "add_bass": True,
            "add_drums": False,
            "expression": {"sustain": False, "modulation": False, "pitch_bend": False},
            "timing": {"humanize": False, "swing": 0, "ppq": 480},
            "filename": "http_test_chords.mid",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("audio/midi")
    body = res.content
    assert body[:4] == b"MThd"
    assert "X-MIDI-BPM" in res.headers


def test_generate_chords_all_roles_off(client: TestClient):
    res = client.post(
        "/generate/chords",
        json={
            "progression": "C | Am",
            "add_melody": False,
            "add_chords": False,
            "add_bass": False,
            "add_drums": False,
        },
    )
    assert res.status_code == 400


def test_meta_styles_shape(client: TestClient):
    res = client.get("/meta/styles")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data.get("moods"), list) and data["moods"]
    assert isinstance(data.get("styles"), list) and data["styles"]
    assert isinstance(data.get("quantize_grids"), list)
    assert isinstance(data.get("ppq_options"), list)


def test_api_token_rejects_text_without_header(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("MIDIGEN_API_TOKEN", "secret-token")
    # Re-import security reads env at call time — token helpers read os.getenv live.
    from app.main import app

    with TestClient(app) as c:
        res = c.post("/generate/text", json={"prompt": "hello piano 8 bars"})
        assert res.status_code == 401


def test_api_token_accepts_header(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("MIDIGEN_API_TOKEN", "secret-token")
    from app.main import app
    from app.features.generation import service as gen_service
    from app.core.engine import MidiEngine, NoteEvent

    engine = MidiEngine(bpm=120)
    track = engine.add_track("Melody", channel=0, instrument="acoustic_grand_piano")
    track.notes.append(NoteEvent(60, 0.0, 1.0, 80))

    def _fake_generate(*_a, **_k):
        return engine

    monkeypatch.setattr(gen_service, "generate_from_prompt", _fake_generate)
    # Also patch the name imported into the router module
    import app.features.text_to_midi.router as text_router

    monkeypatch.setattr(text_router, "generate_from_prompt", _fake_generate)

    with TestClient(app) as c:
        res = c.post(
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
            headers={"X-MIDI-Token": "secret-token"},
        )
        assert res.status_code == 200
        assert res.content[:4] == b"MThd"


def test_cors_regex_off_when_host_non_loopback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    from app.main import _cors_origin_regex

    assert _cors_origin_regex() is None

    monkeypatch.setenv("HOST", "127.0.0.1")
    assert _cors_origin_regex() is not None
