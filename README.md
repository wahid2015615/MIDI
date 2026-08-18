# MIDIgen

Generate **Standard MIDI Files** (`.mid`) from text, chords, or exact note lists. Open the result in Ableton Live, FL Studio, Logic Pro, Cubase, Reaper, Studio One, or any SMF-compatible DAW.

| Mode | AI? | What you get |
| ---- | --- | ------------ |
| **Text** | Yes (local GGUF) | Creative arrangement from a natural-language prompt |
| **Chords** | No | Exact voicings from chord symbols (`Am7` → A C E G, …) |
| **Notes** | No | Exact pitch, timing, duration, and velocity |

Studio UI on **:3001**, FastAPI on **:8000**. Exports SMF Type 0 (single track) or Type 1 (multi-track with Conductor).

> Do **not** commit the model. `Qwen3-4B-Q4_K_M.gguf` (~2.5 GB) stays on disk under `backend/models/`. Git ignores `*.gguf`. Chords and Notes work without it.

---

## Contents

1. [Quick start (Docker)](#quick-start-docker)
2. [Quick start (Python + Node)](#quick-start-python--node)
3. [Features](#features)
4. [Architecture](#architecture)
5. [Mixer / Solo](#mixer--solo)
6. [Chord input](#chord-input)
7. [Notes input](#notes-input)
8. [Configuration](#configuration)
9. [HTTP API](#http-api)
10. [CLI](#cli)
11. [GitHub Actions](#github-actions)
12. [Deploy](#deploy)
13. [AWS CD](#aws-cd)
14. [Docs](#docs)

---

## Quick start (Docker)

Recommended. Needs Docker Desktop (Windows) or Docker Engine + Compose.

```powershell
cd "path\to\MIDI"
copy .env.docker.example .env.docker
# Optional Text mode: put Qwen3-4B-Q4_K_M.gguf in backend\models\
docker compose --env-file .env.docker up --build
```

| URL | Service |
| --- | ------- |
| [http://localhost:3001](http://localhost:3001) | Studio |
| [http://localhost:8000/docs](http://localhost:8000/docs) | API (Swagger) |
| [http://localhost:8000/health](http://localhost:8000/health) | Health |

First backend build can take a while (`llama-cpp-python`). Stop with `Ctrl+C`, or:

```powershell
docker compose --env-file .env.docker down
```

Start again without rebuilding:

```powershell
docker compose --env-file .env.docker up
```

Do **not** also run `python run.py` / `npm run dev` while Compose is up — ports 8000 and 3001 will clash.

The GGUF is **mounted** from `backend/models/` (read-only). It is never baked into the image.

---

## Quick start (Python + Node)

Use this for local development without Docker.

**Need:** Python 3.10+, Node.js 18+. Text mode also needs `backend/models/Qwen3-4B-Q4_K_M.gguf`.

### Backend

```powershell
cd "path\to\MIDI"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd backend
copy .env.example .env
pip install -r requirements.txt
pip install -e .
python run.py
```

API: [http://127.0.0.1:8000](http://127.0.0.1:8000) · docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Windows shortcut: `start-backend.bat` from the repo root (expects an existing `.venv`).

### Frontend

```powershell
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

Studio: [http://localhost:3001](http://localhost:3001). `NEXT_PUBLIC_API_URL` must match the backend (default `http://127.0.0.1:8000`).

Windows shortcut: `start-frontend.bat` from the repo root.

---

## Features

- **Text → MIDI** — style, mood, key, BPM, bars from a prompt; needs the local Qwen GGUF
- **Chords → MIDI** — exact progression voicings (e.g. `C | G | Am | F`); optional melody arpeggio, bass, drums
- **Notes → MIDI** — line input (`C4 q`, same-line `C4 E4 G4 q`, rests, `@track` directives)
- **Mixer** — melody, chords, bass, drums with instrument, channel, volume, pan, mute/solo
- **Timing** — PPQ, quantize, MPC-style swing, humanize
- **Expression** — sustain (CC64), modulation (CC1), pitch bend (applied before timing)
- **Studio** — Next.js UI with downloadable `.mid`
- **API & CLI** — FastAPI REST and `midi-gen`

---

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

---

## Mixer / Solo

| Situation | What exports |
| --------- | ------------ |
| No Solo | All enabled, unmuted roles |
| Solo on one role | Only that role |
| Solo on several | Those roles (multi-solo) |
| Solo + Mute same role | Solo wins |

Muted / disabled roles are **omitted** from the file (export-as-heard), not left as silent tracks.

---

## Chord input

Separators (any one style): `|`  `-`  `,`  `->` / `→`  spaces  newlines

```text
C | G | Am | F
Am7 | Dm7 | G7 | Cmaj7
Cmaj9 | Am7/E | Bm7b5 | G7b9
```

Qualities: `backend/app/core/theory.py` `CHORD_QUALITY` (maj, m, 7, maj7, m7, sus2/4, dim/dim7, 5, 6, add9/madd9/add2, 9/11/13 family, m7b5, 7alt / 7b9…, maj7#11, slash `C/G`, plus aliases).

---

## Notes input

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

---

## Configuration

### Backend (`backend/.env`)

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `LOCAL_MODEL_PATH` | Optional path to `.gguf` | `models/Qwen3-4B-Q4_K_M.gguf` |
| `AI_TEMPERATURE` | Sampling temperature (≥ 0; seed does not override) | `0.3` |
| `AI_MAX_TOKENS` | Max completion tokens | `3072` |
| `LOCAL_N_CTX` | Context window | `4096` |
| `LOCAL_N_THREADS` | CPU threads (optional) | CPU count − 1 |
| `LOCAL_N_GPU_LAYERS` | Offload layers to GPU (`0` = CPU) | `0` |
| `MODEL_IDLE_UNLOAD_SECONDS` | Idle seconds before unloading GGUF from RAM | `120` (min 5) |
| `HOST` | Bind address (`0.0.0.0` for deploy) | `127.0.0.1` |
| `PORT` | Uvicorn port | `8000` |
| `PORT_FALLBACK` | Auto next free port if busy (`1` = yes) | `0` (fail hard) |
| `CORS_ORIGINS` | Extra allowed frontend origins | _(localhost defaults)_ |
| `CORS_ORIGIN_REGEX` | Override/disable default LAN regex | _(private LAN allowed)_ |
| `MIDIGEN_API_TOKEN` | Optional token for text generate + probe | _(unset)_ |
| `GENERATED_ARCHIVE_MAX` | Max archived `.mid` files under `generated/` | `200` |
| `UVICORN_RELOAD` | Auto-reload on code changes | `0` |

Template: `backend/.env.example`.

### Frontend (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

`NEXT_PUBLIC_API_URL` is **build-time**. After changing it, rebuild the frontend (or the Docker frontend image).

### Docker (`.env.docker`)

Copy from `.env.docker.example`. Important keys: `NEXT_PUBLIC_API_URL`, `CORS_ORIGINS`, host ports. Never commit `.env.docker`.

---

## HTTP API

| Method | Path | AI? | Description |
| ------ | ---- | --- | ----------- |
| `GET` | `/health` | — | Health, version, AI status (`?probe=1` loads/checks GGUF) |
| `POST` | `/generate/text` | Yes | Text prompt → `.mid` download |
| `POST` | `/generate/text/preview` | Yes | Same generation, JSON metadata only |
| `POST` | `/generate/cancel` | — | Abort in-flight local GGUF compose |
| `POST` | `/parse/text` | No | Heuristic parse of prompt fields |
| `POST` | `/generate/chords` | No | Exact chord progression → `.mid` |
| `POST` | `/generate/notes` | No | Note lines → `.mid` |
| `GET` | `/meta/instruments` | — | GM instruments and aliases |
| `GET` | `/meta/styles` | — | Styles, moods, PPQ, quantize, swing |
| `GET` | `/meta/ai` | — | Local model configuration |

Shared generate options: mix, timing, expression, `file_type` (`0`/`1`), `duplicate_score_meta` (Type 1: default `false` = Conductor-only tempo map).

Live schemas: `/docs`. Engineering reference: [DOCUMENTATION.txt](DOCUMENTATION.txt).

---

## CLI

After `pip install -e .` in `backend`:

```powershell
midi-gen text "Generate an 8-bar piano melody in C Major at 120 BPM." -o samples/out.mid
midi-gen chords "C | G | Am | F" --bpm 120 -o samples/chords.mid
midi-gen notes examples/notes_example.txt -o samples/notes.mid
midi-gen serve --port 8000
```

CLI writes composition → export only (no Studio mix / expression / timing pipeline). Use REST or the Studio for full mixer/timing control.

Sample batch:

```powershell
cd backend
python examples/generate_samples.py
```

Outputs land in `backend/samples/`. Text samples need the GGUF; chords/notes do not.

---

## GitHub Actions

File: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

Repo: [github.com/wahid2015615/MIDI](https://github.com/wahid2015615/MIDI)

| Job | What | When |
| --- | ---- | ---- |
| **backend-test** | pytest | Every push / pull request |
| **frontend-test** | `npm run build:prod` | Every push / pull request |
| **backend-image** / **frontend-image** | Push to GitHub Container Registry | `main`, `feature/midi`, or tags |
| **deploy-aws** | SSH to EC2, pull images, run containers | Only when `AWS_DEPLOY=true` |

Public repos use free standard GitHub-hosted runners. Optional variable: `NEXT_PUBLIC_API_URL` (baked into the frontend image).

Images (after a successful image job):

- `ghcr.io/wahid2015615/midi/backend:latest`
- `ghcr.io/wahid2015615/midi/frontend:latest`

### AWS CD (EC2)

`deploy-aws` is **skipped** (pipeline stays green) until AWS is configured.

1. AWS console → EC2 → Ubuntu 24.04 VM, **x86_64** (`t3.large` / 8 GB RAM minimum; 16 GB better for the 2.8 GB GGUF). 30 GB disk. Security group: **22** (your IP), **8000** and **3001** (public).
2. SSH in and run `sudo bash deploy/aws/setup-ec2.sh` (copy the file from this repo).
3. Optional text mode: copy `Qwen3-4B-Q4_K_M.gguf` to `/opt/midigen/models/` on the VM (not via git).
4. GitHub → Settings → Secrets and variables → Actions:
   - Variable `AWS_PUBLIC_HOST` = EC2 public IPv4 or DNS
   - Variable `AWS_DEPLOY` = `true`
   - Variable `AWS_EC2_USER` = `ubuntu` (skip if Ubuntu AMI)
   - Secret `EC2_SSH_KEY` = full private key (`BEGIN` … `END`)
5. Push to `feature/midi` (or **Run workflow**). After deploy: `http://<AWS_PUBLIC_HOST>:3001` and `http://<AWS_PUBLIC_HOST>:8000/docs`.

GHCR packages for this repo must be pullable with `GITHUB_TOKEN` (default for the same repository). If pull fails, set the package visibility to **Public** (Package settings).

---

## Deploy

| Piece | What to set |
| ----- | ----------- |
| Model | `backend/models/Qwen3-4B-Q4_K_M.gguf` on the host (text mode). Never commit it |
| Backend bind | `HOST=0.0.0.0` and a public `PORT` |
| Backend CORS | `CORS_ORIGINS=` the Studio origin (e.g. `http://YOUR_IP:3001`) |
| Frontend | `NEXT_PUBLIC_API_URL=` the public API URL, then rebuild |
| Docker | `.env.docker` from `.env.docker.example`; `docker compose --env-file .env.docker up --build` |
| AWS EC2 | GitHub Actions `deploy-aws` (see [AWS CD](#aws-cd-ec2)); SG ports **22**, **8000**, **3001** |
| Oracle Free VM | Open firewall ports **8000** and **3001**; rebuild frontend after changing the public API URL |

Restart the API after code pulls unless `UVICORN_RELOAD=1`. Full checklist: [DOCUMENTATION.txt](DOCUMENTATION.txt) §16.

---

## Layout

```
MIDI/
├── DOCUMENTATION.txt         # Engineering reference
├── README.md                 # This file
├── docker-compose.yml
├── .env.docker.example
├── .github/workflows/ci.yml  # GitHub Actions (test + GHCR + optional AWS CD)
├── deploy/aws/               # EC2 compose + setup/deploy scripts
├── .gitlab-ci.yml            # GitLab CI (legacy)
├── start-backend.bat
├── start-frontend.bat
├── backend/                  # FastAPI + MidiEngine + local GGUF (text)
│   ├── Dockerfile
│   ├── README.md
│   ├── app/
│   ├── models/               # Place Qwen3-4B-Q4_K_M.gguf here (not in git)
│   ├── generated/            # Archived .mid (local)
│   ├── examples/
│   ├── samples/
│   ├── tests/
│   └── run.py
└── frontend/                 # Next.js Studio
    ├── Dockerfile
    ├── README.md
    └── src/
```

---

## Docs

| File | Contents |
| ---- | -------- |
| [DOCUMENTATION.txt](DOCUMENTATION.txt) | Architecture, pipelines, mixer, API, deploy |
| [backend/README.md](backend/README.md) | API setup, env vars, CLI |
| [frontend/README.md](frontend/README.md) | Studio setup, mixer, MPC swing |
| OpenAPI | `http://127.0.0.1:8000/docs` when the API is running |
