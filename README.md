# MIDIgen

Generate **Standard MIDI Files** (`.mid`) from text prompts, chord progressions, or exact note lists.

| Mode | AI? | Output |
| ---- | --- | ------ |
| **Text** | Yes (local GGUF) | Creative arrangement from a natural-language prompt |
| **Chords** | No | **Exact** voicings from chord symbols (Am7 → A C E G, …) |
| **Notes** | No | **Exact** pitch, timing, duration, velocity |

Compatible with major DAWs (Ableton Live, FL Studio, Logic Pro, Cubase, Reaper, Studio One) via SMF Type 0 and Type 1 export.

## Features

- **Text → MIDI** — natural-language prompts (style, mood, key, BPM, bars); requires `Qwen3-4B-Q4_K_M.gguf`
- **Chords → MIDI** — exact progression voicings (e.g. `C | G | Am | F`); optional melody arpeggio, bass, drums
- **Notes → MIDI** — line-based input (`C4 q`, same-line `C4 E4 G4 q`, rests, multi-track directives)
- **Multi-track mix** — melody, chords, bass, drums with instrument, channel, volume, pan, mute/solo
- **Timing** — PPQ, quantize, MPC-style swing, humanize
- **Expression** — sustain (CC64), modulation (CC1), pitch bend (applied before timing)
- **Studio UI** — Next.js frontend with downloadable `.mid` output
- **API & CLI** — FastAPI REST endpoints and `midi-gen` command-line tool

## Architecture

```
Text / Chords / Notes
        │
        ├─ Text ──────────► Local GGUF (Qwen) → JSON → MidiEngine
        ├─ Chords ────────► Exact voicer (parse_chord_symbol) → MidiEngine
        └─ Notes ─────────► Line parser → MidiEngine
        │
        ▼
 HTTP post-pipeline (after composition):
   score meta → mix → [select: text/chords only] → expression → timing → validate SMF
   Notes skip apply_track_selection (tracks come from @track lines).
        │
        ▼
 Standard .mid (Type 0 or 1)
```

## Mixer / Solo (quick)

| Situation | What exports |
| --------- | ------------ |
| No Solo | All enabled, unmuted roles |
| Solo on one role | Only that role |
| Solo on several | Those roles (multi-solo) |
| Solo + Mute same role | Solo wins |

Muted / disabled roles are **omitted** from the file (export-as-heard), not left as silent tracks.

## Chord input (exact mode)

Separators (any one style): `|`  `-`  `,`  `->` / `→`  spaces  newlines

```text
C | G | Am | F
Am7 | Dm7 | G7 | Cmaj7
Cmaj9 | Am7/E | Bm7b5 | G7b9
```

Qualities: see `backend/app/core/theory.py` `CHORD_QUALITY` (maj, m, 7, maj7, m7, sus2/4, dim/dim7, 5, 6, add9/madd9/add2, 9/11/13 family, m7b5, 7alt / 7b9…, maj7#11, slash `C/G`, plus aliases).

## Notes input (exact mode)

Deterministic line parser — **no AI**. Multi-track via `@track` / `#track` / `[Name]`.

```text
@track Chords electric_piano_1
C4 E4 G4 q
F4 A4 C5 q
G4 B4 D5 q
C4 E4 G4 h

@track Melody flute
G5 e
A5 e
G5 e
E5 e
F5 q
D5 q
E5 h

@track Bass acoustic_bass
C2 q
C2 q
F2 q
F2 q
G2 q
G2 q
C2 h
```

Same-line pitches (`C4 E4 G4 q`) share one beat. In the `.mid`, list order of those notes may differ; pitches and durations match. Studio **Humanize** (default off) applies ±`humanize_timing` beats of jitter (default 0.02 beats ≈ ±10 ticks at PPQ 480) — turn it off for same-tick stacks.

All modes still send shared **mix / timing / expression** on generate.

## Prerequisites

- **Python** 3.10+
- **Node.js** 18+ (for the studio UI)
- Local model file: `backend/models/Qwen3-4B-Q4_K_M.gguf` (~2.5 GB) — **text mode only** (chords/notes work without it)

## Quick start

### 1. Backend

```powershell
cd "path\to\MIDI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd backend
copy .env.example .env
# Place Qwen3-4B-Q4_K_M.gguf into backend/models/  (needed for Text mode)
pip install -r requirements.txt
pip install -e .
python run.py
```

API defaults to `http://127.0.0.1:8000`. Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

On Windows you can also run `start-backend.bat` from the repo root (expects an existing `.venv`).

### 2. Frontend

```powershell
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3001](http://localhost:3001). Ensure `NEXT_PUBLIC_API_URL` matches the backend URL (default `http://127.0.0.1:8000`).

On Windows: `start-frontend.bat` from the repo root.

## Configuration

### Backend (`backend/.env`)

| Variable              | Description                                | Default                      |
| --------------------- | ------------------------------------------ | ---------------------------- |
| `LOCAL_MODEL_PATH`    | Optional path to `.gguf`                   | `models/Qwen3-4B-Q4_K_M.gguf` |
| `AI_TEMPERATURE`      | Sampling temperature (≥ 0; seed does not override) | `0.3`                |
| `AI_MAX_TOKENS`       | Max completion tokens                      | `3072`                       |
| `LOCAL_N_CTX`         | Context window                             | `4096`                       |
| `LOCAL_N_THREADS`     | CPU threads (optional)                     | CPU count − 1                |
| `LOCAL_N_GPU_LAYERS`  | Offload layers to GPU (`0` = CPU)          | `0`                          |
| `MODEL_IDLE_UNLOAD_SECONDS` | Idle seconds before unloading GGUF from RAM | `120` (min 5)          |
| `HOST`                | Bind address (`0.0.0.0` for deploy)        | `127.0.0.1`                  |
| `PORT`                | Uvicorn port                               | `8000`                       |
| `PORT_FALLBACK`       | Auto next free port if busy (`1` = yes)    | `0` (fail hard)              |
| `CORS_ORIGINS`        | Extra allowed frontend origins             | _(localhost defaults)_       |
| `CORS_ORIGIN_REGEX`   | Override/disable default LAN regex         | _(private LAN allowed)_      |
| `MIDIGEN_API_TOKEN`   | Optional token for text generate + probe   | _(unset)_                    |
| `GENERATED_ARCHIVE_MAX` | Max archived `.mid` files under generated/ | `200`                      |
| `UVICORN_RELOAD`      | Auto-reload on code changes                | `0`                          |

See `backend/.env.example` for a full template.

### Frontend (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

## API overview

| Method | Path                       | AI? | Description                              |
| ------ | -------------------------- | --- | ---------------------------------------- |
| `GET`  | `/health`                  | —   | Health, version, AI status (`?probe=1` loads/checks GGUF) |
| `POST` | `/generate/text`           | Yes | Text prompt → `.mid` download            |
| `POST` | `/generate/text/preview`   | Yes | Same generation, JSON metadata only      |
| `POST` | `/generate/cancel`         | —   | Abort in-flight local GGUF compose       |
| `POST` | `/parse/text`              | No  | Heuristic parse of prompt fields         |
| `POST` | `/generate/chords`         | No  | Exact chord progression → `.mid`         |
| `POST` | `/generate/notes`          | No  | Note lines → `.mid`                      |
| `GET`  | `/meta/instruments`        | —   | GM instruments and aliases               |
| `GET`  | `/meta/styles`             | —   | Styles, moods, PPQ, quantize, swing      |
| `GET`  | `/meta/ai`                 | —   | Local model configuration                |

Shared generate options: mix, timing, expression, `file_type` (`0`/`1`), `duplicate_score_meta` (Type 1: default `false` = Conductor-only tempo map).

Full schemas: `/docs`. Full engineering reference: [DOCUMENTATION.txt](DOCUMENTATION.txt).

## CLI

After `pip install -e .` in `backend`:

```powershell
midi-gen text "Generate an 8-bar piano melody in C Major at 120 BPM." -o samples/out.mid
midi-gen chords "C | G | Am | F" --bpm 120 -o samples/chords.mid
midi-gen notes examples/notes_example.txt -o samples/notes.mid
midi-gen serve --port 8000
```

CLI writes composition → export only (no Studio mix / expression / timing pipeline). Use REST or the Studio for full mixer/timing control.

## Sample MIDI files

```powershell
cd backend
python examples/generate_samples.py
```

Outputs land in `backend/samples/`. Text (AI) samples need the local GGUF model; chords/notes samples do not.

## Project layout

```
MIDI/
├── DOCUMENTATION.txt         # Full engineering reference
├── README.md                 # This file
├── docker-compose.yml
├── .env.docker.example
├── .gitlab-ci.yml
├── start-backend.bat
├── start-frontend.bat
├── backend/                  # FastAPI + MidiEngine + local GGUF (text)
│   ├── Dockerfile
│   ├── README.md
│   ├── app/
│   │   └── features/chords_to_midi/exact.py   # Exact chord voicer
│   ├── models/               # Place Qwen3-4B-Q4_K_M.gguf here (text mode)
│   ├── generated/            # Archived .mid + last model raw JSON
│   ├── examples/
│   ├── samples/
│   └── run.py
└── frontend/                 # Next.js studio UI
    ├── Dockerfile
    ├── README.md
    └── src/
```

## Docker (local or Oracle Free VM)

Requires Docker Engine + Compose. Text mode still needs the GGUF on disk (mounted, not baked into the image).

```powershell
copy .env.docker.example .env.docker
# Optional: put Qwen3-4B-Q4_K_M.gguf in backend/models/
docker compose --env-file .env.docker up --build
```

| URL | Service |
| --- | ------- |
| http://localhost:3001 | Studio |
| http://localhost:8000/docs | API |

On an Oracle Free VM, set `NEXT_PUBLIC_API_URL=http://YOUR_PUBLIC_IP:8000` and matching `CORS_ORIGINS`, then rebuild. Open firewall ports **8000** and **3001**.

GitLab CI (`.gitlab-ci.yml`): runs pytest + frontend build, then pushes images to the GitLab Container Registry on `main` / `feature/MIDI` / tags.

## Deploy notes

| Piece | What to set |
| ----- | ----------- |
| Backend `.env` | Model path if not default; never commit secrets |
| Backend model  | `backend/models/Qwen3-4B-Q4_K_M.gguf` (text mode) |
| Backend bind | `HOST=0.0.0.0` and a public `PORT` |
| Backend CORS | `CORS_ORIGINS=https://your-frontend-domain` |
| Frontend | `NEXT_PUBLIC_API_URL=https://your-api-domain` then `npm run build` / `npm start` |
| Docker | `.env.docker` from `.env.docker.example`; `docker compose up --build` |

Restart the API after code pulls unless `UVICORN_RELOAD=1`.

## Documentation

- [**DOCUMENTATION.txt**](DOCUMENTATION.txt) — architecture, pipelines, mixer, API, deploy
- [Backend README](backend/README.md) — API setup, env vars, CLI details
- [Frontend README](frontend/README.md) — studio UI setup and mixer/swing notes
- OpenAPI — `http://127.0.0.1:8000/docs` when the server is running
