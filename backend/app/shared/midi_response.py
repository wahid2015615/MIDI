"""Helpers for exporting MIDI HTTP responses."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.engine import CCEvent, MidiEngine, clamp_bpm, normalize_time_signature
from app.core.expression import apply_expression
from app.core.instruments import DRUM_CHANNEL, get_program, is_drum_instrument
from app.core.timing import (
    GRID_BEATS,
    SWING_GRIDS,
    apply_swing,
    humanize_track,
    partition_sustain_events,
    quantize_track,
)
from app.features.generation.composer import (
    MELODIC_MIXER_ROLES,
    MIXER_ROLES,
    _canonical_track_name,
    key_signature_token,
)
from app.shared.schemas import (
    ExpressionOptions,
    FileType,
    TimeSignatureOptions,
    TimingOptions,
    TrackMixOptions,
)
from mido import MetaMessage


EMPTY_EXPORT_MESSAGE = (
    "All tracks are muted or empty — enable at least one track in the mixer"
)


def ensure_exportable(engine: MidiEngine) -> None:
    """Raise if mix/selection left nothing playable to export."""
    active = engine._active_tracks()
    if not active or not any(t.notes for t in active):
        raise ValueError(EMPTY_EXPORT_MESSAGE)


def safe_filename(name: str) -> str:
    name = name.strip() or "midi_output.mid"
    name = re.sub(r"[^\w.\-]+", "_", name)
    if not name.lower().endswith(".mid"):
        name += ".mid"
    return name


def apply_score_meta(
    engine: MidiEngine,
    *,
    time_signature: TimeSignatureOptions | tuple[int, int] | list[int] | None = None,
    key: str | None = None,
) -> None:
    """Apply configurable time signature and key signature to the engine."""
    if time_signature is not None:
        if isinstance(time_signature, TimeSignatureOptions):
            engine.time_signature = time_signature.as_tuple()
        elif isinstance(time_signature, (list, tuple)) and len(time_signature) == 2:
            engine.time_signature = normalize_time_signature(
                time_signature[0], time_signature[1]
            )
        else:
            raise ValueError(
                "time_signature must be {numerator, denominator} or [numerator, denominator]"
            )
    if key is not None and key.strip():
        token = key_signature_token(key)
        try:
            MetaMessage("key_signature", key=token)
            engine.key_signature = token
        except ValueError as exc:
            raise ValueError(f"Unsupported key signature {key!r} ({token!r})") from exc


def apply_track_mix(engine: MidiEngine, mix: TrackMixOptions | None) -> None:
    if not mix:
        return
    mapping = {
        "melody": (
            mix.mute_melody,
            mix.solo_melody,
            mix.volume_melody,
            mix.pan_melody,
            mix.instrument_melody,
            mix.channel_melody,
        ),
        "chords": (
            mix.mute_chords,
            mix.solo_chords,
            mix.volume_chords,
            mix.pan_chords,
            mix.instrument_chords,
            mix.channel_chords,
        ),
        "bass": (
            mix.mute_bass,
            mix.solo_bass,
            mix.volume_bass,
            mix.pan_bass,
            mix.instrument_bass,
            mix.channel_bass,
        ),
        "drums": (
            mix.mute_drums,
            mix.solo_drums,
            mix.volume_drums,
            mix.pan_drums,
            mix.instrument_drums,
            mix.channel_drums,
        ),
    }
    for track in engine.tracks:
        key = _canonical_track_name(track.name).strip().lower()
        if key in mapping:
            muted, solo, volume, pan, instrument, channel = mapping[key]
            apply_instrument = True
        else:
            # Custom notes labels (Violin, Guitar, …) follow Melody mute/solo/vol/pan
            # so Studio mixer controls still work; keep @track instrument/channel.
            muted, solo, volume, pan, _inst, _ch = mapping["melody"]
            instrument = None
            channel = None
            apply_instrument = False
        track.muted = bool(muted)
        track.solo = bool(solo)
        if volume is not None:
            track.volume = volume
        if pan is not None:
            track.pan = pan
        if apply_instrument and instrument:
            get_program(instrument)  # raise on unknown — never silent piano
            # Melodic mixer roles cannot use GM drum kit (would force channel 9
            # and collide with a real Drums track).
            if key in MELODIC_MIXER_ROLES and is_drum_instrument(instrument):
                raise ValueError(
                    f"Role '{key}' cannot use drum instrument '{instrument}' "
                    "(GM drums must stay on the Drums track / channel 10)"
                )
            track.instrument = instrument
            if is_drum_instrument(instrument) and channel is None:
                track.channel = DRUM_CHANNEL
        if apply_instrument and channel is not None:
            if is_drum_instrument(track.instrument):
                track.channel = DRUM_CHANNEL
            elif int(channel) == DRUM_CHANNEL:
                # Melodic roles cannot use the GM drum channel
                free = [
                    i
                    for i in range(16)
                    if i != DRUM_CHANNEL
                    and not any(
                        t is not track
                        and not is_drum_instrument(t.instrument)
                        and int(t.channel) == i
                        for t in engine.tracks
                    )
                ]
                track.channel = free[0] if free else 0
            else:
                track.channel = int(channel)


def apply_track_selection(
    engine: MidiEngine,
    *,
    include_melody: bool | None = None,
    include_chords: bool | None = None,
    include_bass: bool | None = None,
    include_drums: bool | None = None,
) -> None:
    """Mute roles the UI did not request so they never appear in the MIDI file.

    When any include_* flag is provided, tracks whose names do not map to a
    mixer role (Melody/Chords/Bass/Drums) are also muted so AI extras cannot
    escape selection.
    """
    wanted = {
        "melody": include_melody,
        "chords": include_chords,
        "bass": include_bass,
        "drums": include_drums,
    }
    any_specified = any(v is not None for v in wanted.values())
    for track in engine.tracks:
        role = _canonical_track_name(track.name).strip().lower()
        include = wanted.get(role)
        if include is False:
            # Role disabled in the UI / API — exclude fully (solo must not revive it).
            track.muted = True
            track.solo = False
        elif any_specified and role not in MIXER_ROLES:
            track.muted = True
            track.solo = False


def apply_timing(
    engine: MidiEngine,
    timing: TimingOptions | None,
    *,
    seed: int | None = None,
) -> None:
    if not timing:
        return
    # Notes are stored in beats; PPQ only affects tick conversion on export.
    engine.ppq = timing.ppq
    swing_grid = timing.swing_grid or "1/8"
    if timing.swing > 0 and swing_grid not in GRID_BEATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid swing_grid '{swing_grid}'. "
                f"Use one of: {', '.join(SWING_GRIDS)}"
            ),
        )

    humanize_seed = timing.seed if timing.seed is not None else seed

    for index, track in enumerate(engine.tracks):
        if timing.quantize:
            if timing.quantize not in GRID_BEATS:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid quantize grid '{timing.quantize}'. "
                        f"Use one of: {', '.join(GRID_BEATS)}"
                    ),
                )
            quantize_track(
                track,
                grid=timing.quantize,
                swing=timing.swing,
                swing_grid=swing_grid,
                quantize_duration_flag=timing.quantize_duration,
            )
        elif timing.swing > 0:
            # Swing without full quantize: shift off-beats only
            for note in track.notes:
                note.start_beat = apply_swing(
                    note.start_beat, grid=swing_grid, amount=timing.swing
                )
            pairs, rest = partition_sustain_events(track.cc_events)
            new_cc: list[CCEvent] = []
            for on_ev, off_ev in pairs:
                on_t = apply_swing(
                    on_ev.time_beat, grid=swing_grid, amount=timing.swing
                )
                duration = max(off_ev.time_beat - on_ev.time_beat, 1e-4)
                off_t = on_t + duration
                new_cc.append(CCEvent(64, on_ev.value, on_t))
                new_cc.append(CCEvent(64, off_ev.value, off_t))
            for cc in rest:
                if cc.control == 64:
                    new_cc.append(cc)
                else:
                    new_cc.append(
                        CCEvent(
                            cc.control,
                            cc.value,
                            apply_swing(
                                cc.time_beat, grid=swing_grid, amount=timing.swing
                            ),
                        )
                    )
            track.cc_events = new_cc
            for pb in track.pitch_bends:
                pb.time_beat = apply_swing(
                    pb.time_beat, grid=swing_grid, amount=timing.swing
                )

        if timing.humanize:
            track_seed = (
                None if humanize_seed is None else int(humanize_seed) + index * 9973
            )
            humanize_track(
                track,
                timing_beats=timing.humanize_timing,
                velocity_jitter=timing.humanize_velocity,
                duration_beats=timing.humanize_duration,
                controllers=timing.humanize_controllers,
                seed=track_seed,
            )


def apply_expression_options(
    engine: MidiEngine, expression: ExpressionOptions | None
) -> None:
    """Apply sustain / modulation / pitch bend into tracks before export.

    ``None`` is a no-op (same as ``apply_timing(..., None)``). Send an explicit
    ``ExpressionOptions()`` if you want the historical all-toggles-on defaults.
    """
    if expression is None:
        return
    opts = expression
    apply_expression(
        engine,
        sustain=opts.sustain,
        modulation=opts.modulation,
        pitch_bend=opts.pitch_bend,
        sustain_on_value=opts.sustain_on_value,
        sustain_off_value=opts.sustain_off_value,
        sustain_hold_ratio=opts.sustain_hold_ratio,
        modulation_value=opts.modulation_value,
        modulation_interval_bars=opts.modulation_interval_bars,
        modulation_accent_ratio=opts.modulation_accent_ratio,
        pitch_bend_scoop_depth=opts.pitch_bend_scoop_depth,
        pitch_bend_interval_bars=opts.pitch_bend_interval_bars,
        pitch_bend_scoop_beats=opts.pitch_bend_scoop_beats,
    )


def engine_meta(engine: MidiEngine) -> dict:
    return {
        "bpm": engine.bpm,
        "ppq": engine.ppq,
        "time_signature": {
            "numerator": engine.time_signature[0],
            "denominator": engine.time_signature[1],
        },
        "key_signature": engine.key_signature,
        "duration_beats": round(engine.duration_beats(active_only=True), 3),
        "duration_bars": round(engine.duration_bars(active_only=True), 3),
        "tracks": [
            {
                "name": t.name,
                "channel": t.channel,
                "instrument": t.instrument,
                "volume": t.volume,
                "pan": t.pan,
                "muted": t.muted,
                "solo": t.solo,
                "note_count": len(t.notes),
            }
            for t in engine.tracks
        ],
    }


# UI / API exports are also archived here so generated files stay in the project.
GENERATED_DIR = Path(__file__).resolve().parents[2] / "generated"


def _archive_max_files() -> int:
    raw = (os.getenv("GENERATED_ARCHIVE_MAX") or "200").strip()
    try:
        return max(10, int(raw))
    except ValueError:
        return 200


def _prune_generated_archive() -> None:
    """Keep only the newest archive files under generated/."""
    limit = _archive_max_files()
    try:
        files = [
            p
            for p in GENERATED_DIR.iterdir()
            if p.is_file() and p.suffix.lower() == ".mid"
        ]
    except OSError:
        return
    if len(files) <= limit:
        return
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in files[limit:]:
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            continue


def _archive_generated_copy(source: Path, filename: str) -> Path | None:
    """Copy export into backend/generated/ with a timestamp so files do not collide."""
    from datetime import datetime

    try:
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = GENERATED_DIR / f"{stamp}_{filename}"
        shutil.copy2(source, dest)
        _prune_generated_archive()
        return dest
    except OSError:
        # Download must still succeed even if archive write fails.
        return None


def _cleanup_export_tmpdir(tmp_dir: str) -> None:
    """Retry temp deletion — Windows often holds the file until response finishes."""
    for attempt in range(6):
        try:
            shutil.rmtree(tmp_dir)
            return
        except OSError:
            time.sleep(0.05 * (attempt + 1))
    shutil.rmtree(tmp_dir, ignore_errors=True)


def send_midi(
    engine: MidiEngine,
    filename: str,
    file_type: FileType,
    *,
    duplicate_score_meta: bool = False,
) -> FileResponse:
    filename = safe_filename(filename)
    engine.bpm = clamp_bpm(engine.bpm)
    tmp_dir = tempfile.mkdtemp(prefix="midi_export_")
    tmp = Path(tmp_dir) / filename
    try:
        engine.export(
            tmp,
            file_type=file_type,
            duplicate_score_meta=duplicate_score_meta,
        )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    active = engine._active_tracks()
    num, den = engine.time_signature
    headers = {
        "X-MIDI-BPM": str(engine.bpm),
        "X-MIDI-Bars": str(round(engine.duration_bars(active_only=True), 2)),
        "X-MIDI-Tracks": str(len(active)),
        "X-MIDI-PPQ": str(engine.ppq),
        "X-MIDI-Key": str(engine.key_signature or ""),
        "X-MIDI-TimeSig": f"{num}/{den}",
        "Access-Control-Expose-Headers": (
            "X-MIDI-BPM, X-MIDI-Bars, X-MIDI-Tracks, X-MIDI-PPQ, "
            "X-MIDI-Key, X-MIDI-TimeSig, Content-Disposition, X-MIDI-Saved-As"
        ),
    }
    archived = _archive_generated_copy(tmp, filename)
    if archived is not None:
        print(f"[MIDIgen] Saved copy → generated/{archived.name}", flush=True)
        headers["X-MIDI-Saved-As"] = archived.name
    print(f"[MIDIgen] Export ready → download as {filename}", flush=True)
    return FileResponse(
        path=tmp,
        media_type="audio/midi",
        filename=filename,
        headers=headers,
        background=BackgroundTask(_cleanup_export_tmpdir, tmp_dir),
    )
