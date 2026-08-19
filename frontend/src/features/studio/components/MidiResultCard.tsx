"use client";

import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { triggerMidiDownload } from "../api/studioApi";
import { parseSmf, waveformFromNotes } from "../midi/parseSmf";
import { MidiPreviewPlayer } from "../midi/previewPlayer";
import { TypeIcon } from "../../../shared/ui/TypeIcon";
import type { StudioMidiResult } from "../types";

function formatTime(seconds: number): string {
  const s = Math.max(0, seconds);
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
}

const MODE_LABEL: Record<StudioMidiResult["mode"], string> = {
  text: "MELODY",
  chords: "CHORDS",
  notes: "NOTES",
};

const MODE_TITLE: Record<StudioMidiResult["mode"], string> = {
  text: "Melody",
  chords: "Chords",
  notes: "Notes",
};

export function MidiResultCard({
  result,
  onCreateAnother,
}: {
  result: StudioMidiResult;
  onCreateAnother: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const playerRef = useRef<MidiPreviewPlayer | null>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [parseError, setParseError] = useState<string | null>(null);
  const [canvasSize, setCanvasSize] = useState(0);

  const parsed = useMemo(() => {
    try {
      return parseSmf(result.bytes);
    } catch {
      return null;
    }
  }, [result.bytes]);

  const duration = parsed?.duration ?? 0;
  const waveform = useMemo(
    () => (parsed ? waveformFromNotes(parsed.notes, parsed.duration, 108) : []),
    [parsed],
  );

  useEffect(() => {
    if (!parsed) {
      setParseError("Preview could not read this MIDI file.");
      return;
    }
    setParseError(null);
    const player = new MidiPreviewPlayer();
    player.load(parsed.notes, parsed.duration);
    player.setListener((time, isPlaying) => {
      setCurrent(time);
      setPlaying(isPlaying);
    });
    playerRef.current = player;
    return () => {
      player.dispose();
      playerRef.current = null;
    };
  }, [parsed]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      setCanvasSize((n) => n + 1);
    });
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [parsed]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !waveform.length) return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.clientWidth || 720;
    const cssH = canvas.clientHeight || 118;
    canvas.width = Math.floor(cssW * dpr);
    canvas.height = Math.floor(cssH * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);

    const progress = duration > 0 ? current / duration : 0;
    const gap = 2.2;
    const barW = Math.max(2.2, (cssW - gap * waveform.length) / waveform.length);
    const mid = cssH / 2;

    waveform.forEach((amp, i) => {
      const x = i * (barW + gap);
      const h = Math.max(6, amp * (cssH * 0.88));
      const y = mid - h / 2;
      const played = i / waveform.length <= progress;
      ctx.fillStyle = played ? "#e879f9" : "rgba(167, 139, 250, 0.38)";
      const r = Math.min(2.4, barW / 2);
      ctx.beginPath();
      ctx.roundRect(x, y, barW, h, r);
      ctx.fill();
    });
  }, [waveform, current, duration, playing, canvasSize]);

  async function togglePlay() {
    const player = playerRef.current;
    if (!player) return;
    if (playing) player.pause();
    else await player.play();
  }

  function seekFromClick(e: MouseEvent<HTMLCanvasElement>) {
    if (!duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    playerRef.current?.seek(ratio * duration);
  }

  const durationLabel = `${Math.max(1, Math.round(duration))}s`;
  const title = `${MODE_TITLE[result.mode]} — ${result.selectedKey} (${durationLabel})`;

  function formatBars(value: number): string {
    if (Number.isInteger(value)) return String(value);
    const rounded = Math.round(value * 100) / 100;
    return String(rounded);
  }

  const metaTags = [
    result.selectedKey,
    `${result.selectedBpm} BPM`,
    result.selectedTimeSig,
    result.selectedBars != null
      ? `${formatBars(result.selectedBars)} measures`
      : null,
    parsed ? `${parsed.noteCount} notes` : null,
  ].filter(Boolean) as string[];

  return (
    <section className="midi-player animate-rise">
      <p className="result-quote">“{result.quote}”</p>

      <article className={`result-card${playing ? " is-playing" : ""}`}>
        <header className="result-card-head">
          <h3 className="result-title">{title}</h3>
          <div className="result-tags">
            {result.style && (
              <span className="tag-pill">
                <TypeIcon kind="style" name={result.style} />
                {result.style}
              </span>
            )}
            {result.mood && (
              <span className="tag-pill">
                <TypeIcon kind="mood" name={result.mood} />
                {result.mood}
              </span>
            )}
            {metaTags.map((tag) => (
              <span key={tag} className="tag-pill">
                {tag}
              </span>
            ))}
            <span className="tag-pill tag-pill-accent">
              <TypeIcon kind="mode" name={result.mode} />
              {MODE_LABEL[result.mode]}
            </span>
          </div>
        </header>

        <canvas
          ref={canvasRef}
          className="result-wave"
          onClick={seekFromClick}
          aria-label="MIDI waveform — click to seek"
        />

        {parseError && (
          <p className="mt-2 text-sm text-[var(--warn)]">{parseError}</p>
        )}

        <footer className="result-card-foot">
          <div className="result-play-row">
            <button
              type="button"
              className={`play-btn${playing ? " is-playing" : ""}`}
              onClick={() => void togglePlay()}
              disabled={!parsed}
              aria-label={playing ? "Pause preview" : "Play preview"}
            >
              {playing ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                  <rect x="6" y="5" width="4" height="14" rx="1" />
                  <rect x="14" y="5" width="4" height="14" rx="1" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                  <path d="M8 5.2v13.6l11.2-6.8L8 5.2z" />
                </svg>
              )}
            </button>
            <span className="result-time">
              {formatTime(current)} / {formatTime(duration)}
            </span>
          </div>
          <button
            type="button"
            className="download-midi-btn"
            onClick={() => triggerMidiDownload(result.url, result.filename)}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M12 4v12m0 0l-4.5-4.5M12 16l4.5-4.5M5 20h14"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Download MIDI
          </button>
        </footer>
      </article>

      <div className="result-actions">
        <button type="button" className="create-another-btn" onClick={onCreateAnother}>
          + Create another
        </button>
      </div>
    </section>
  );
}
