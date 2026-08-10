"""Local GGUF chat client for MIDI composition (llama.cpp / Qwen)."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from app.features.generation.config import AIConfig, get_ai_config

logger = logging.getLogger(__name__)

_llm = None
_llm_path: str | None = None
_llm_lock = threading.Lock()
_idle_timer: threading.Timer | None = None
# Bumped on cancel/reschedule so a late timer callback cannot unload a warm model
_idle_generation = 0
# Generations currently holding a live llm handle (blocks idle unload).
_in_flight = 0
# Per-generation cancel handles (isolates concurrent text generates).
_cancel_lock = threading.Lock()
_next_generation_id = 0
_generation_cancelled: dict[int, bool] = {}
_client_to_generation: dict[str, int] = {}
# Idle unload after generation (seconds). Env override: MODEL_IDLE_UNLOAD_SECONDS
_DEFAULT_IDLE_UNLOAD_SECONDS = 120.0


def begin_generation(client_request_id: str | None = None) -> int:
    """Register an in-flight compose; return a handle id for cancel checks."""
    global _next_generation_id
    cid = (client_request_id or "").strip() or None
    with _cancel_lock:
        _next_generation_id += 1
        gid = _next_generation_id
        _generation_cancelled[gid] = False
        if cid:
            previous = _client_to_generation.get(cid)
            if previous is not None and previous in _generation_cancelled:
                _generation_cancelled[previous] = True
            _client_to_generation[cid] = gid
        return gid


def end_generation(generation_id: int, client_request_id: str | None = None) -> None:
    """Drop cancel bookkeeping for a finished compose."""
    cid = (client_request_id or "").strip() or None
    with _cancel_lock:
        _generation_cancelled.pop(generation_id, None)
        if cid and _client_to_generation.get(cid) == generation_id:
            _client_to_generation.pop(cid, None)


def request_generation_cancel(client_request_id: str | None = None) -> None:
    """Abort matching in-flight AI compose(s) at the next safe checkpoint.

    If ``client_request_id`` is provided, only that generation is cancelled.
    Otherwise every currently registered generation is cancelled.
    Note: llama.cpp ``create_completion`` is not interruptible mid-call; cancel
    is observed before/after inference.
    """
    cid = (client_request_id or "").strip() or None
    with _cancel_lock:
        if cid:
            gid = _client_to_generation.get(cid)
            if gid is not None and gid in _generation_cancelled:
                _generation_cancelled[gid] = True
            return
        for gid in list(_generation_cancelled):
            _generation_cancelled[gid] = True


def _raise_if_cancelled(generation_id: int) -> None:
    with _cancel_lock:
        cancelled = _generation_cancelled.get(generation_id, True)
    if cancelled:
        raise AIMusicError("Generation cancelled")


def _idle_unload_seconds() -> float:
    raw = (os.getenv("MODEL_IDLE_UNLOAD_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_IDLE_UNLOAD_SECONDS
    try:
        return max(5.0, float(raw))
    except ValueError:
        return _DEFAULT_IDLE_UNLOAD_SECONDS


def _cancel_idle_timer_locked() -> None:
    """Cancel pending idle unload. Caller must hold ``_llm_lock``."""
    global _idle_timer, _idle_generation
    if _idle_timer is not None:
        _idle_timer.cancel()
        _idle_timer = None
    _idle_generation += 1


def _cancel_idle_unload() -> None:
    with _llm_lock:
        _cancel_idle_timer_locked()


def _close_llm_instance(llm: Any) -> None:
    """Best-effort close + GC for a llama.cpp instance (caller drops references)."""
    import gc

    close = getattr(llm, "close", None)
    try:
        if callable(close):
            close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error while closing local model: %s", exc)
    try:
        del llm
    except Exception:  # noqa: BLE001
        pass
    gc.collect()


def _unload_llm_generation(expected_generation: int) -> None:
    """Drop the cached GGUF if this timer is still the current idle epoch."""
    global _llm, _llm_path, _idle_timer

    with _llm_lock:
        if expected_generation != _idle_generation:
            return
        if _in_flight > 0:
            # A request is using the model; finally-block will reschedule unload.
            return
        _idle_timer = None
        if _llm is None:
            return
        llm = _llm
        _llm = None
        _llm_path = None
    _close_llm_instance(llm)
    _log_step("Model unloaded from RAM (idle timeout)")


def _unload_llm(*, reason: str = "idle timeout") -> None:
    """Force-unload (tests / explicit). Always clears the current epoch."""
    global _llm, _llm_path, _idle_timer, _idle_generation

    with _llm_lock:
        if _idle_timer is not None:
            _idle_timer.cancel()
            _idle_timer = None
        _idle_generation += 1
        if _llm is None:
            return
        llm = _llm
        _llm = None
        _llm_path = None
    _close_llm_instance(llm)
    _log_step(f"Model unloaded from RAM ({reason})")


def _schedule_idle_unload() -> None:
    """Start / restart the idle timer; model stays loaded until it fires."""
    global _idle_timer, _idle_generation
    seconds = _idle_unload_seconds()
    with _llm_lock:
        if _idle_timer is not None:
            _idle_timer.cancel()
            _idle_timer = None
        _idle_generation += 1
        if _llm is None or _in_flight > 0:
            return
        gen = _idle_generation
        timer = threading.Timer(seconds, _unload_llm_generation, args=(gen,))
        timer.daemon = True
        _idle_timer = timer
        timer.start()
    _log_step(f"Model idle unload in {seconds:.0f}s (timer reset)")


def model_is_loaded() -> bool:
    """Return True if a GGUF instance is currently cached in this process."""
    with _llm_lock:
        return _llm is not None


class AIMusicError(RuntimeError):
    pass


def _log_step(message: str) -> None:
    """Print + log so progress is visible in the backend terminal."""
    line = f"[MIDIgen] {message}"
    print(line, flush=True)
    logger.info(message)


def _strip_think_blocks(text: str) -> str:
    """Qwen3 may emit <think>...</think>; remove before JSON parse."""
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<think>[\s\S]*$", "", text, flags=re.IGNORECASE)
    # Orphan close tag after JSON (then duplicate JSON)
    text = re.sub(r"</think>[\s\S]*$", "", text, flags=re.IGNORECASE)
    return text.strip()


def _loads_first_json(text: str) -> Any:
    """Parse the first JSON value only (ignore trailing junk / duplicates)."""
    return json.JSONDecoder().raw_decode(text.lstrip())[0]


def _slice_json_object(text: str) -> str:
    """Take the first complete top-level JSON object via brace matching."""
    start = text.find("{")
    if start < 0:
        raise AIMusicError("Model did not return a JSON object")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _repair_json_text(raw: str) -> str:
    """Fix truncated / messy JSON from one local-model response (no second call)."""
    text = raw.strip()
    text = re.sub(r",\s*([}\]])", r"\1", text)

    in_string = False
    escape = False
    stack: list[str] = []
    last_safe = -1

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
            continue
        if ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
                if not stack:
                    last_safe = i
            continue

    if in_string:
        if last_safe >= 0:
            text = text[: last_safe + 1]
        else:
            text += '"'

    if last_safe >= 0:
        # Recheck if already balanced after trim
        probe = text if not in_string or last_safe < 0 else text[: last_safe + 1]
        stack2: list[str] = []
        in_s = False
        esc = False
        balanced_at = -1
        for i, ch in enumerate(probe):
            if in_s:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_s = False
                continue
            if ch == '"':
                in_s = True
            elif ch == "{":
                stack2.append("}")
            elif ch == "[":
                stack2.append("]")
            elif ch in "}]":
                if stack2 and stack2[-1] == ch:
                    stack2.pop()
                    if not stack2:
                        balanced_at = i
        if balanced_at >= 0 and not stack2:
            return re.sub(r",\s*([}\]])", r"\1", probe[: balanced_at + 1])

    stack = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()

    if in_string:
        text += '"'
    text = re.sub(r",\s*(\"[^\"]*\"\s*:)?\s*$", "", text)
    text = re.sub(r",\s*$", "", text)
    text = re.sub(r":\s*$", ": null", text)
    while stack:
        text += stack.pop()
    return re.sub(r",\s*([}\]])", r"\1", text)


def _normalize_composition(data: Any) -> dict[str, Any] | None:
    """Map common local-model shapes onto {bpm, key, time_signature, tracks}."""
    if isinstance(data, list):
        if data and all(isinstance(x, dict) for x in data):
            return {
                "bpm": 120,
                "key": "C Major",
                "time_signature": [4, 4],
                "tracks": data,
            }
        return None

    if not isinstance(data, dict):
        return None

    # Nested wrappers: { "composition": {...} }, { "data": {...} }, etc.
    for wrap_key in ("composition", "data", "result", "midi", "score", "output"):
        inner = data.get(wrap_key)
        if isinstance(inner, (dict, list)):
            normalized = _normalize_composition(inner)
            if normalized is not None:
                # Prefer outer bpm/key if present
                for meta in ("bpm", "key", "time_signature"):
                    if meta in data and meta not in normalized:
                        normalized[meta] = data[meta]
                return normalized

    tracks = data.get("tracks")
    if tracks is None:
        for alt in ("Tracks", "track_list", "parts", "instruments", "channels"):
            if isinstance(data.get(alt), list):
                tracks = data[alt]
                break

    # Role keys as objects: { "Melody": { "notes": [...] }, "Bass": {...} }
    if tracks is None:
        role_canon = {
            "melody": "Melody",
            "chords": "Chords",
            "bass": "Bass",
            "drums": "Drums",
        }
        role_tracks: list[dict[str, Any]] = []
        for role_key, role_name in role_canon.items():
            chunk = data.get(role_name)
            if chunk is None:
                chunk = data.get(role_key)
            if isinstance(chunk, dict) and isinstance(chunk.get("notes"), list):
                role_tracks.append(
                    {
                        "name": role_name,
                        "instrument": chunk.get("instrument")
                        or ("drum_kit" if role_name == "Drums" else "acoustic_grand_piano"),
                        "notes": chunk["notes"],
                    }
                )
            elif isinstance(chunk, list) and chunk:
                role_tracks.append(
                    {
                        "name": role_name,
                        "instrument": "drum_kit"
                        if role_name == "Drums"
                        else "acoustic_grand_piano",
                        "notes": chunk,
                    }
                )
        if role_tracks:
            tracks = role_tracks

    # Top-level notes only
    if tracks is None and isinstance(data.get("notes"), list) and data["notes"]:
        tracks = [
            {
                "name": "Melody",
                "instrument": str(data.get("instrument") or "acoustic_grand_piano"),
                "notes": data["notes"],
            }
        ]

    if not isinstance(tracks, list) or not tracks:
        return None

    # Coerce track entries: sometimes a track is just a notes list
    fixed_tracks: list[dict[str, Any]] = []
    for i, item in enumerate(tracks):
        if isinstance(item, list):
            fixed_tracks.append(
                {
                    "name": "Melody" if i == 0 else f"Track{i+1}",
                    "instrument": "acoustic_grand_piano",
                    "notes": item,
                }
            )
        elif isinstance(item, dict):
            notes = item.get("notes")
            if notes is None:
                for nk in ("Notes", "note_list", "events"):
                    if isinstance(item.get(nk), list):
                        notes = item[nk]
                        break
            if not isinstance(notes, list):
                continue
            fixed = dict(item)
            fixed["notes"] = notes
            if "name" not in fixed:
                fixed["name"] = "Melody"
            if "instrument" not in fixed:
                fixed["instrument"] = "acoustic_grand_piano"
            fixed_tracks.append(fixed)

    if not fixed_tracks:
        return None

    out = dict(data)
    out["tracks"] = fixed_tracks
    out.setdefault("bpm", 120)
    out.setdefault("key", "C Major")
    out.setdefault("time_signature", [4, 4])
    return out


def _extract_json(text: str) -> dict[str, Any]:
    text = _strip_think_blocks(text.strip())
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    candidates = [text]
    try:
        candidates.append(_slice_json_object(text))
    except AIMusicError:
        pass

    errors: list[str] = []
    parsed_any = False
    for cand in candidates:
        for attempt in (cand, _repair_json_text(cand)):
            try:
                data = _loads_first_json(attempt)
            except json.JSONDecodeError as exc:
                errors.append(str(exc))
                continue
            parsed_any = True
            normalized = _normalize_composition(data)
            if normalized is not None:
                if attempt != cand:
                    _log_step(
                        "JSON was truncated/messy — repaired locally (no model retry)"
                    )
                if normalized is not data:
                    _log_step("JSON shape normalized to tracks[] (no model retry)")
                return normalized
            keys = (
                list(data.keys())[:12]
                if isinstance(data, dict)
                else type(data).__name__
            )
            errors.append(f"JSON missing usable tracks (keys={keys})")

    snippet = re.sub(r"\s+", " ", text)[:240]
    _log_step(f"JSON parse failed. Snippet: {snippet}")
    detail = errors[-1] if errors else "unknown parse error"
    if not parsed_any:
        raise AIMusicError(
            f"Model returned invalid JSON ({detail}). "
            "Try fewer bars or fewer tracks."
        ) from None
    raise AIMusicError(
        f"Model JSON had no playable tracks ({detail}). "
        "Try fewer bars or fewer tracks."
    ) from None


def _get_llm(cfg: AIConfig, *, quiet: bool = False):
    """Lazy-load and cache the GGUF model in memory."""
    global _llm, _llm_path
    path = str(cfg.model_path)
    with _llm_lock:
        if _llm is not None and _llm_path == path:
            if not quiet:
                _log_step(f"Model already loaded in memory: {cfg.model}")
            return _llm
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise AIMusicError(
                "llama-cpp-python is not installed. "
                "Run: pip install llama-cpp-python"
            ) from exc

        if not cfg.configured:
            raise AIMusicError(
                f"Local model not found at {cfg.model_path}. "
                f"Place Qwen3-4B-Q4_K_M.gguf in backend/models/ "
                f"(or set LOCAL_MODEL_PATH in backend/.env)."
            )

        # Path change (or reload): close previous GGUF so RAM does not leak.
        if _llm is not None:
            old = _llm
            _llm = None
            _llm_path = None
            _cancel_idle_timer_locked()
            _close_llm_instance(old)
            _log_step("Previous model closed before loading a new path")

        _log_step(
            f"Loading local model ({cfg.model}) — first time can take 30–90s..."
        )
        _log_step(
            f"  path={path} | n_ctx={cfg.n_ctx} | threads={cfg.n_threads} | "
            f"gpu_layers={cfg.n_gpu_layers}"
        )
        started = time.perf_counter()
        try:
            _llm = Llama(
                model_path=path,
                n_ctx=cfg.n_ctx,
                n_threads=cfg.n_threads,
                n_gpu_layers=cfg.n_gpu_layers,
                verbose=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise AIMusicError(f"Failed to load local model: {exc}") from exc
        _llm_path = path
        _log_step(f"Model loaded in {time.perf_counter() - started:.1f}s")
        return _llm


def probe_provider(cfg: AIConfig | None = None) -> bool:
    """Return True if the GGUF file exists and loads."""
    global _in_flight
    config = cfg or get_ai_config()
    if not config.configured:
        return False
    try:
        with _llm_lock:
            _cancel_idle_timer_locked()
            _in_flight += 1
        try:
            _get_llm(config, quiet=True)
        finally:
            with _llm_lock:
                _in_flight = max(0, _in_flight - 1)
        _schedule_idle_unload()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Local model probe failed: %s", exc)
        if model_is_loaded():
            _schedule_idle_unload()
        return False


def model_status(*, probe: bool = False) -> dict[str, Any]:
    cfg = get_ai_config()
    loaded = model_is_loaded()
    online = False
    if cfg.configured and probe:
        online = probe_provider(cfg)
        loaded = model_is_loaded()
    elif cfg.configured and not probe:
        # "online" means the model file is available for generation (may still
        # need a cold load after idle unload). Use ``loaded`` for RAM state.
        online = True
    return {
        "provider": "local",
        "model": cfg.model,
        "model_path": str(cfg.model_path),
        "configured": cfg.configured,
        "online": online,
        "loaded": loaded,
        "temperature": cfg.temperature,
        "n_ctx": cfg.n_ctx,
        "n_threads": cfg.n_threads,
        "n_gpu_layers": cfg.n_gpu_layers,
    }


def _build_qwen_completion_prompt(system: str, user: str) -> tuple[str, str]:
    """ChatML-style prompt with JSON prefill so the model cannot emit empty {}."""
    prefill = '{\n  "bpm": '
    prompt = (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\n{user}\n\n"
        "Reply with ONE JSON object only. It MUST include a non-empty "
        '"tracks" array with notes. /no_think<|im_end|>\n'
        f"<|im_start|>assistant\n{prefill}"
    )
    return prompt, prefill


def compose_midi_json(
    *,
    system_prompt: str,
    user_prompt: str,
    seed: int | None = None,
    config: AIConfig | None = None,
    client_request_id: str | None = None,
) -> dict[str, Any]:
    cfg = config or get_ai_config()
    if not cfg.configured:
        raise AIMusicError(
            f"Local model not found at {cfg.model_path}. "
            "Place Qwen3-4B-Q4_K_M.gguf in backend/models/ "
            "(or set LOCAL_MODEL_PATH in backend/.env)."
        )

    _log_step("Starting AI composition (local Qwen) — single call...")
    global _in_flight
    generation_id = begin_generation(client_request_id)
    with _llm_lock:
        _cancel_idle_timer_locked()
        _in_flight += 1
    try:
        _raise_if_cancelled(generation_id)
        llm = _get_llm(cfg)
        _raise_if_cancelled(generation_id)
        # Respect AI_TEMPERATURE even when a seed is set for reproducibility.
        temperature = max(0.0, float(cfg.temperature))

        system = (
            system_prompt
            + "\n\nCRITICAL: Include \"tracks\": [ ... ] with at least one note. "
            "Never return {}."
        )
        user = f"{user_prompt}\n\n/no_think"
        prompt, prefill = _build_qwen_completion_prompt(system, user)

        create_kwargs: dict[str, Any] = {
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": cfg.max_tokens,
            "stop": ["<|im_end|>", "<|endoftext|>", "<|im_start|>"],
        }
        if seed is not None:
            create_kwargs["seed"] = int(seed)

        _log_step(
            f"Model generating JSON (max_tokens={cfg.max_tokens}, "
            f"temp={temperature}, prefill=on) — please wait..."
        )
        started = time.perf_counter()
        _raise_if_cancelled(generation_id)
        try:
            # Serialize inference: llama.cpp models are not generally thread-safe.
            with _llm_lock:
                try:
                    response = llm.create_completion(**create_kwargs)
                except Exception as exc:  # noqa: BLE001
                    if seed is not None and "seed" in str(exc).lower():
                        create_kwargs.pop("seed", None)
                        response = llm.create_completion(**create_kwargs)
                    else:
                        raise AIMusicError(
                            f"Local model request failed: {exc}"
                        ) from exc
        except AIMusicError:
            raise

        _raise_if_cancelled(generation_id)
        elapsed = time.perf_counter() - started
        try:
            continuation = response["choices"][0]["text"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise AIMusicError(
                "Local model returned unexpected response shape"
            ) from exc

        content = prefill + continuation
        if not content.strip() or content.strip() == "{}":
            raise AIMusicError(
                "Model returned empty JSON. Restart backend and try a shorter prompt."
            )

        _log_step(f"Model finished in {elapsed:.1f}s — parsing JSON...")
        try:
            debug_path = (
                Path(__file__).resolve().parents[3]
                / "generated"
                / "_last_model_raw.json.txt"
            )
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(str(content)[:20000], encoding="utf-8")
        except OSError:
            pass

        data = _extract_json(str(content))
        _raise_if_cancelled(generation_id)

        tracks = data.get("tracks")
        if isinstance(tracks, list):
            cleaned = []
            for track in tracks:
                if not isinstance(track, dict):
                    continue
                notes = track.get("notes")
                if isinstance(notes, list) and notes:
                    cleaned.append(track)
            data["tracks"] = cleaned

        tracks = data.get("tracks") if isinstance(data.get("tracks"), list) else []
        if not tracks:
            raise AIMusicError(
                "Model JSON had no playable notes. Try a simpler prompt "
                "(fewer bars / fewer tracks)."
            )

        note_count = sum(
            len(t["notes"])
            for t in tracks
            if isinstance(t, dict) and isinstance(t.get("notes"), list)
        )
        _log_step(f"JSON OK — tracks={len(tracks)}, notes={note_count}")
        return data
    finally:
        end_generation(generation_id, client_request_id)
        with _llm_lock:
            _in_flight = max(0, _in_flight - 1)
            should_schedule = _in_flight == 0 and _llm is not None
        if should_schedule:
            _schedule_idle_unload()
