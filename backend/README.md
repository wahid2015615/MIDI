# MIDIgen Backend

FastAPI service that turns text, chord progressions, or note lists into Standard MIDI Files (`.mid`) using **mido**.

| Mode | AI (local GGUF)? | Behavior |
| ---- | ---------------- | -------- |
| Text | Yes | LLM → composition JSON → MidiEngine |
| Chords | No | Exact voicings from `parse_chord_symbol` |
| Notes | No | Exact line parser → MidiEngine |

## Requirements

- Python **3.10+**
- Local model file: `backend/models/Qwen3-4B-Q4_K_M.gguf` (~2.5 GB) for **text mode only**

Chords and notes generation work offline without the GGUF.

## Setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd backend
copy .env.example .env
```

Download / copy the GGUF into (text mode):

```
backend/models/Qwen3-4B-Q4_K_M.gguf
```

Install dependencies:

```powershell
pip install -r requirements.txt
pip install -e .
```

`llama-cpp-python` may take a few minutes on first install (Windows wheels or build).

## Run the server

```powershell
python run.py
```

| Resource   | URL                                      |
| ---------- | ---------------------------------------- |
| API        | http://127.0.0.1:8000                    |
| Swagger UI | http://127.0.0.1:8000/docs               |
| ReDoc      | http://127.0.0.1:8000/redoc              |
| Health     | http://127.0.0.1:8000/health             |

| Variable          | Default       | Description                                      |
| ----------------- | ------------- | ------------------------------------------------ |
| `HOST`            | `127.0.0.1`   | Bind address; use `0.0.0.0` when deploying       |
| `PORT`            | `8000`        | Preferred listen port                            |
| `CORS_ORIGINS`    | _(empty)_     | Extra allowed frontend origins (comma-separated) |
| `CORS_ORIGIN_REGEX` | _(LAN regex)_ | Empty string disables default private-LAN regex |
| `UVICORN_RELOAD`  | `0`           | Set to `1` to enable auto-reload                 |

If the preferred port is busy, `run.py` exits with a clear error so
`NEXT_PUBLIC_API_URL` stays in sync. Set `PORT_FALLBACK=1` only if you want
the old “next free port” behaviour (then update the frontend URL to match).

## Environment reference

| Variable             | Required | Description                                      |
| -------------------- | -------- | ------------------------------------------------ |
| `LOCAL_MODEL_PATH`   | No       | Override path to `.gguf` (default under `models/`) |
| `AI_TEMPERATURE`     | No       | Default `0.3` (clamped ≥ 0; seed does not override) |
| `AI_MAX_TOKENS`      | No       | Default `3072`                                   |
| `LOCAL_N_CTX`        | No       | Context size, default `4096`                     |
| `LOCAL_N_THREADS`    | No       | CPU threads (default CPU count − 1)              |
| `LOCAL_N_GPU_LAYERS` | No       | GPU layers (`0` = CPU only)                      |
| `MODEL_IDLE_UNLOAD_SECONDS` | No | Idle unload after last use (default `120`; min 5) |
| `PORT_FALLBACK`      | No       | `1` = auto-pick next free port when busy         |
| `CORS_ORIGINS`       | No       | Extra origins for deploy                         |
| `CORS_ORIGIN_REGEX`  | No       | Override or disable default LAN regex            |
| `UVICORN_RELOAD`     | No       | `1` = auto-reload                                |

See `.env.example` for a full template.

## Endpoints

| Method | Path                     | AI  | Description |
| ------ | ------------------------ | --- | ----------- |
| `GET`  | `/health`                | —   | Status, version, AI status (`?probe=1` checks GGUF; includes `loaded`) |
| `POST` | `/generate/text`         | Yes | Prompt → MIDI file download |
| `POST` | `/generate/text/preview` | Yes | Same generation, JSON metadata only |
| `POST` | `/generate/cancel`       | —   | Abort in-flight local GGUF compose (`{"cancelled": true}`; generate may return 499) |
| `POST` | `/parse/text`            | No  | Heuristic parse of prompt fields |
| `POST` | `/generate/chords`       | No  | Exact progression → MIDI file |
| `POST` | `/generate/notes`        | No  | Note lines → MIDI file |
| `GET`  | `/meta/instruments`      | —   | GM instruments + aliases |
| `GET`  | `/meta/styles`           | —   | Styles, moods, PPQ / quantize options |
| `GET`  | `/meta/ai`               | —   | Current local model summary |

HTTP generate routes run the shared post-pipeline: score meta → mix →
track selection (text/chords) → expression → timing → SMF validate → download.

### Chords (`POST /generate/chords`)

Builds tracks from `app/features/chords_to_midi/exact.py` (no LLM):

- **Chords** — block voicing per symbol (`Am7` → A C E G, …)
- **Bass** — root / slash bass
- **Melody** — arpeggio of the same chord tones
- **Drums** — simple deterministic groove

Progression separators: `|` `-` `,` `->`/`→` spaces newlines.  
Qualities: authoritative list in `app/core/theory.py` (`CHORD_QUALITY` / aliases). Includes maj, m, 7, maj7, m7, sus, dim/dim7, 5, 6, add9/madd9/add2, 9/11/13, m7b5, 7alt/7b9…, maj7#11, slash `C/G`.

### Notes (`POST /generate/notes`)

Exact line grammar — **no LLM**. See `examples/notes_example.txt`.

Supports:

- Single notes: `C4 q`, `E4 half 90`
- Same-line chords: `C4 E4 G4 q` (shared start beat)
- Rests: `rest q` / `r q`
- Multi-track: `@track Melody …`, `#track Bass …`, `[Chords instrument]`

Tracks are defined in the note text (not Studio role pills). Shared `mix`, `timing`, and `expression` still apply after parse. With `humanize: false`, same-beat chord notes land on the same tick.

## CLI

Installed as `midi-gen` when the package is installed editable:

```powershell
midi-gen text "Happy piano melody in C Major, 120 BPM, 8 bars" -o samples/text.mid
midi-gen chords "C | G | Am | F" --bpm 120 --drums -o samples/chords.mid
midi-gen notes examples/notes_example.txt --bpm 100 -o samples/notes.mid
midi-gen serve --host 127.0.0.1 --port 8000
```

CLI = composition → `engine.export` only (no mix / expression / timing pipeline).
Use REST or the Studio for full mixer and timing control.

## Sample MIDI batch

```powershell
python examples/generate_samples.py
```

Text (AI) samples require `backend/models/Qwen3-4B-Q4_K_M.gguf`. Chords/notes samples do not.

## Related docs

- [DOCUMENTATION.txt](../DOCUMENTATION.txt) — full engineering reference
- [Project README](../README.md)
- [Frontend README](../frontend/README.md)
