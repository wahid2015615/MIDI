"""Idle unload: keep GGUF warm briefly, then free RAM after inactivity."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.features.generation import ai_client


@pytest.fixture(autouse=True)
def _reset_llm_state(monkeypatch: pytest.MonkeyPatch):
    """Isolate module globals between tests."""
    monkeypatch.setattr(ai_client, "_llm", None)
    monkeypatch.setattr(ai_client, "_llm_path", None)
    monkeypatch.setattr(ai_client, "_idle_timer", None)
    monkeypatch.setattr(ai_client, "_idle_generation", 0)
    monkeypatch.setattr(ai_client, "_in_flight", 0)
    yield
    with ai_client._llm_lock:
        if ai_client._idle_timer is not None:
            ai_client._idle_timer.cancel()
            ai_client._idle_timer = None
        ai_client._idle_generation += 1
        ai_client._in_flight = 0
    monkeypatch.setattr(ai_client, "_llm", None)
    monkeypatch.setattr(ai_client, "_llm_path", None)


def test_idle_unload_default_is_two_minutes() -> None:
    assert ai_client._idle_unload_seconds() == 120.0


def test_idle_unload_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_IDLE_UNLOAD_SECONDS", "8")
    assert ai_client._idle_unload_seconds() == 8.0


def test_schedule_cancel_and_unload_frees_stub_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[bool] = []

    class Stub:
        def close(self) -> None:
            closed.append(True)

    monkeypatch.setenv("MODEL_IDLE_UNLOAD_SECONDS", "5")
    with ai_client._llm_lock:
        ai_client._llm = Stub()
        ai_client._llm_path = "stub.gguf"

    ai_client._schedule_idle_unload()
    assert ai_client._idle_timer is not None
    assert ai_client.model_is_loaded()

    ai_client._cancel_idle_unload()
    assert ai_client._idle_timer is None
    assert ai_client.model_is_loaded()

    ai_client._unload_llm(reason="test")
    assert not ai_client.model_is_loaded()
    assert closed == [True]


def test_idle_timer_fires_and_unloads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_IDLE_UNLOAD_SECONDS", "5")
    stub = SimpleNamespace(close=lambda: None)
    with ai_client._llm_lock:
        ai_client._llm = stub
        ai_client._llm_path = "stub.gguf"

    ai_client._schedule_idle_unload()
    # Timer must wait >=5s; poll briefly with margin
    deadline = time.time() + 8.0
    while time.time() < deadline and ai_client.model_is_loaded():
        time.sleep(0.05)

    assert not ai_client.model_is_loaded()


def test_timer_restart_delays_unload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_IDLE_UNLOAD_SECONDS", "5")
    stub = SimpleNamespace(close=lambda: None)
    with ai_client._llm_lock:
        ai_client._llm = stub
        ai_client._llm_path = "stub.gguf"

    ai_client._schedule_idle_unload()
    time.sleep(2.5)
    # Soft renew as on a second generation finishing
    ai_client._cancel_idle_unload()
    assert ai_client.model_is_loaded()
    ai_client._schedule_idle_unload()

    time.sleep(2.5)
    # Original window would have elapsed (~5s); restart should keep it loaded
    assert ai_client.model_is_loaded()

    deadline = time.time() + 8.0
    while time.time() < deadline and ai_client.model_is_loaded():
        time.sleep(0.05)
    assert not ai_client.model_is_loaded()


def test_stale_timer_does_not_unload_after_reschedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A timer already waiting on the lock must not unload after renew."""
    monkeypatch.setenv("MODEL_IDLE_UNLOAD_SECONDS", "5")
    stub = SimpleNamespace(close=lambda: None)
    with ai_client._llm_lock:
        ai_client._llm = stub
        ai_client._llm_path = "stub.gguf"

    ai_client._schedule_idle_unload()
    with ai_client._llm_lock:
        stale_gen = ai_client._idle_generation

    # Reschedule (as after another generation) — invalidates stale_gen
    ai_client._schedule_idle_unload()
    with ai_client._llm_lock:
        assert ai_client._idle_generation != stale_gen

    ai_client._unload_llm_generation(stale_gen)
    assert ai_client.model_is_loaded()


def test_compose_schedules_idle_unload_in_finally() -> None:
    import inspect

    src = inspect.getsource(ai_client.compose_midi_json)
    assert "_cancel_idle_timer_locked()" in src
    assert "_in_flight" in src
    assert "_schedule_idle_unload()" in src
    assert "finally:" in src


def test_in_flight_blocks_idle_unload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_IDLE_UNLOAD_SECONDS", "5")
    stub = SimpleNamespace(close=lambda: None)
    with ai_client._llm_lock:
        ai_client._llm = stub
        ai_client._llm_path = "stub.gguf"
        ai_client._in_flight = 1

    ai_client._schedule_idle_unload()
    assert ai_client._idle_timer is None
    assert ai_client.model_is_loaded()

    with ai_client._llm_lock:
        ai_client._in_flight = 0
    ai_client._schedule_idle_unload()
    assert ai_client._idle_timer is not None
    ai_client._cancel_idle_unload()
    assert ai_client.model_is_loaded()
