import type {
  ExpressionOptions,
  TimingOptions,
  TimeSignatureOptions,
  TrackMixOptions,
  TrackOptions,
} from "../types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

export { API_BASE };

/** Format FastAPI `detail` (string | array | object) into a readable message. */
export function formatApiDetail(detail: unknown, fallback = "Request failed"): string {
  if (detail == null) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const row = item as { loc?: unknown[]; msg?: string; type?: string };
        const loc = Array.isArray(row.loc)
          ? row.loc
              .filter((p) => p !== "body" && p !== "query")
              .map(String)
              .join(".")
          : "";
        const msg = row.msg || JSON.stringify(item);
        return loc ? `${loc}: ${msg}` : msg;
      }
      return String(item);
    });
    return parts.filter(Boolean).join("; ") || fallback;
  }
  if (typeof detail === "object") {
    const obj = detail as { msg?: string; message?: string };
    if (obj.msg) return obj.msg;
    if (obj.message) return obj.message;
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return fallback;
  }
}

export function isAbortError(err: unknown): boolean {
  if (!err || typeof err !== "object") return false;
  const name = (err as { name?: string }).name;
  return name === "AbortError" || name === "CanceledError";
}

async function readErrorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json();
    return formatApiDetail(data.detail ?? data, fallback);
  } catch {
    return fallback;
  }
}

type RequestOptions = {
  signal?: AbortSignal;
};

async function downloadMidi(
  path: string,
  body: unknown,
  fallbackName: string,
  options?: RequestOptions,
) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options?.signal,
  });

  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Generation failed"));
  }

  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = /filename="?([^"]+)"?/i.exec(disposition);
  const filename = match?.[1] || fallbackName;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);

  return {
    filename,
    bpm: res.headers.get("X-MIDI-BPM"),
    bars: res.headers.get("X-MIDI-Bars"),
    tracks: res.headers.get("X-MIDI-Tracks"),
    ppq: res.headers.get("X-MIDI-PPQ"),
    key: res.headers.get("X-MIDI-Key"),
    timeSig: res.headers.get("X-MIDI-TimeSig"),
  };
}

export async function generateFromText(
  payload: {
    prompt: string;
    bpm?: number | null;
    bars?: number | null;
    key?: string | null;
    time_signature?: TimeSignatureOptions | null;
    mood?: string | null;
    style?: string | null;
    instrument?: string | null;
    tracks?: TrackOptions;
    mix?: TrackMixOptions;
    timing?: TimingOptions;
    expression?: ExpressionOptions;
    file_type?: 0 | 1;
    filename?: string;
    seed?: number;
  },
  options?: RequestOptions,
) {
  return downloadMidi(
    "/generate/text",
    payload,
    payload.filename || "generated.mid",
    options,
  );
}

export async function generateFromChords(
  payload: {
    progression: string;
    bpm?: number;
    bars_per_chord?: number;
    key?: string;
    time_signature?: TimeSignatureOptions | null;
    instrument?: string;
    add_chords?: boolean;
    add_melody?: boolean;
    add_bass?: boolean;
    add_drums?: boolean;
    mix?: TrackMixOptions;
    timing?: TimingOptions;
    expression?: ExpressionOptions;
    file_type?: 0 | 1;
    filename?: string;
    seed?: number;
  },
  options?: RequestOptions,
) {
  return downloadMidi(
    "/generate/chords",
    payload,
    payload.filename || "chords.mid",
    options,
  );
}

export async function generateFromNotes(
  payload: {
    notes: string[];
    bpm?: number;
    key?: string;
    time_signature?: TimeSignatureOptions | null;
    instrument?: string;
    mix?: TrackMixOptions;
    timing?: TimingOptions;
    expression?: ExpressionOptions;
    file_type?: 0 | 1;
    filename?: string;
    seed?: number;
  },
  options?: RequestOptions,
) {
  return downloadMidi(
    "/generate/notes",
    payload,
    payload.filename || "notes.mid",
    options,
  );
}

export async function parseTextPrompt(prompt: string, options?: RequestOptions) {
  const res = await fetch(`${API_BASE}/parse/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
    signal: options?.signal,
  });
  if (!res.ok) {
    throw new Error(await readErrorDetail(res, "Failed to parse prompt"));
  }
  return res.json() as Promise<{
    bars: number;
    bpm: number;
    key: string;
    mood: string;
    style: string;
    instrument: string;
    include_chords: boolean;
    include_bass: boolean;
    include_drums: boolean;
    time_signature?: { numerator: number; denominator: number };
    detected: {
      bars: boolean;
      bpm: boolean;
      key: boolean;
      mood: boolean;
      style: boolean;
      instrument: boolean;
      include_chords: boolean;
      include_bass: boolean;
      include_drums: boolean;
      time_signature?: boolean;
    };
  }>;
}

export async function fetchHealth(options?: { probe?: boolean; signal?: AbortSignal }) {
  const probe = options?.probe ? "?probe=1" : "";
  const res = await fetch(`${API_BASE}/health${probe}`, {
    cache: "no-store",
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("API offline");
  return res.json() as Promise<{
    status: string;
    version: string;
    ai?: {
      provider: string;
      model: string;
      model_path?: string;
      configured: boolean;
      online?: boolean;
      temperature?: number;
      n_ctx?: number;
      n_threads?: number;
      n_gpu_layers?: number;
    };
  }>;
}

export async function fetchMeta(options?: RequestOptions) {
  const [instrumentsRes, stylesRes] = await Promise.all([
    fetch(`${API_BASE}/meta/instruments`, { signal: options?.signal }),
    fetch(`${API_BASE}/meta/styles`, { signal: options?.signal }),
  ]);
  if (!instrumentsRes.ok || !stylesRes.ok) {
    throw new Error("Failed to load meta endpoints");
  }
  const [instruments, styles] = await Promise.all([
    instrumentsRes.json(),
    stylesRes.json(),
  ]);
  return { instruments, styles, apiBase: API_BASE };
}
