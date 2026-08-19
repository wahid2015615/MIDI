# MIDIgen Frontend

Next.js studio UI for [MIDIgen](../README.md). Compose from text, chords, or note lists, adjust mix and timing, preview the result in Studio, then download Standard MIDI (`.mid`) files from the backend API.

## Requirements

- **Node.js** 18+
- Running MIDIgen backend (default `http://127.0.0.1:8000`)
- Local GGUF on the backend only for **Text** mode (Chords / Notes work without it)

## Setup

```powershell
cd frontend
copy .env.example .env.local
npm install
```

Configure the API base URL in `.env.local`:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Use the same host and port printed when the backend starts.

## Development

```powershell
npm run dev
```

Open [http://localhost:3001](http://localhost:3001).

From the repo root on Windows: `start-frontend.bat`.

## Scripts

| Command         | Description              |
| --------------- | ------------------------ |
| `npm run dev`   | Dev server on **:3001** (Turbopack) |
| `npm run build` | Production build         |
| `npm run start` | Serve production on **:3001** |
| `npm run lint`  | ESLint                   |
| `npm test`      | Vitest unit tests        |

## Features

- Modes: **Text** (AI), **Chords** (exact, no AI), **Notes** (exact, no AI)
- Track roles: melody, chords, bass, drums (enable pills)
- Per-track instrument, channel, volume, pan, **Mute / Solo**
- Timing: PPQ, quantize, **MPC-style swing** (50 = straight, ~66 = triplet), humanize
- Expression: sustain, modulation, pitch bend
- Export Type 0 or Type 1 MIDI
- **In-studio preview** after generate: waveform, play/pause, key/BPM/bars tags; **Download MIDI** is opt-in (file is not auto-saved)
- Motion in `src/app/globals.css` (page entrance, hover, generate sheen, result player, dropdowns; respects `prefers-reduced-motion`)
- Live API / local model status indicators (via `/health?probe=1`) — model required only for Text
- Bars UI range **1–128** (API allows up to 512)

### Mode tips

| Mode | Input | Notes |
| ---- | ----- | ----- |
| Text | Natural language | Needs GGUF; creative / not note-exact |
| Chords | `C \| G \| Am \| F` (or `-`, `,`, arrows, newlines) | Exact chord tones; melody = arpeggio of those tones |
| Notes | `C4 q`, `C4 E4 G4 q`, `@track Bass …` | Exact placement; multi-track via directives |

Shared on generate for every mode: **mix**, **timing** (PPQ / quantize / swing / humanize), **expression** (sustain / mod / pitch bend).

For same-tick chord stacks in Notes/Chords `.mid` output, leave **Humanize** off (Studio default). When on, timing uses ±`humanize_timing` beats (default 0.02 ≈ ±10 ticks @ PPQ 480) — intentional jitter, not AI rewriting notes.

## API calls used by Studio

| Endpoint | Purpose |
| -------- | ------- |
| `POST /generate/text\|chords\|notes` | Generate `.mid` (Studio previews in-page; download is a button) |
| `POST /generate/cancel` | Abort in-flight Text (GGUF) generation |
| `POST /parse/text` | Auto-fill detected prompt fields (text mode) |
| `GET /health?probe=1` | API + local model status |
| `GET /meta/instruments` | Instrument dropdowns |
| `GET /meta/styles` | Style / mood / grid catalogs |

`resolveApiBase()` rewrites `127.0.0.1` in `NEXT_PUBLIC_API_URL` to the page hostname when the Studio is opened via LAN (e.g. `http://192.168.x.x:3001`).

Not called by the current UI (REST still available):

- `POST /generate/text/preview` — metadata-only generate
- `GET /meta/ai` — covered by `/health`
- `duplicate_score_meta` — not sent; API default `false` (Conductor-only meta)

Mode-specific **examples** sit under the compose input (4 per tab, different formats). There is no Session summary sidebar.

## Mixer behavior

| Control | Effect on exported `.mid` |
| ------- | ------------------------- |
| Role off | Role not included |
| Mute | Role omitted from file |
| Solo (one or more) | Only soloed roles included |
| Solo + Mute same role | Solo wins |

When any Solo is active, the UI shows **Clear solos (N exporting)**.

## Swing

Studio slider uses **MPC-style percent** (50–75). Before calling the API it converts to a delay fraction:

```text
delay = (mpc - 50) / 50
```

Example: 66% ≈ triplet → delay ≈ 0.32. Do not confuse this with raw API `TimingOptions.swing` if calling HTTP yourself.

## Project layout

```
frontend/
├── src/
│   ├── app/                    # App Router (layout, page, styles)
│   ├── features/studio/        # Studio UI, API client, MIDI preview, types
│   └── shared/ui/              # Shared form helpers
├── .env.example
├── package.json
└── next.config.ts
```

## Related docs

- [DOCUMENTATION.txt](../DOCUMENTATION.txt) — full engineering reference  
- [Project README](../README.md)  
- [Backend README](../backend/README.md)  
- API docs: `http://127.0.0.1:8000/docs`  
