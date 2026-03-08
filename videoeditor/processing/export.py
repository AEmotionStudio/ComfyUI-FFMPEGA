"""Final render pipeline — chains all video edits into FFmpeg commands.

Orchestrates the full edit pipeline: trim → per-segment speed →
transitions → text overlays → crop → audio.  Uses ``core.bin_paths``
for FFmpeg binary resolution.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading

from ._bin import get_ffmpeg_bin, get_ffprobe_bin
from .audio import build_audio_filter, get_audio_args
from .crop import apply_crop
from .speed import build_speed_filters
from .text_overlay import build_drawtext_filters
from .transitions import apply_transitions, parse_transitions
from .trim import _parse_segments

log = logging.getLogger("ffmpega.videoeditor")


def render_edits(
    source_path: str,
    output_path: str,
    *,
    segments_json: str = "[]",
    crop_json: str = "",
    speed_map_json: str = "{}",
    volume: float = 1.0,
    text_overlays_json: str = "[]",
    transitions_json: str = "[]",
    cancel_event: threading.Event | None = None,
) -> dict:
    """Apply all edits and render to *output_path*.

    Parameters
    ----------
    source_path:
        Path to the source video file.
    output_path:
        Destination path for the rendered video.
    segments_json:
        JSON ``[[start, end], ...]`` segment list.
    crop_json:
        JSON ``{"x":N,"y":N,"w":N,"h":N}`` or empty.
    speed_map_json:
        JSON ``{"segIdx": speed}`` per-segment speed map.
    volume:
        Audio volume (0.0–2.0).
    text_overlays_json:
        JSON array of text overlay configs.
    transitions_json:
        JSON array of transition configs.

    Returns
    -------
    dict
        ``{"success": bool, "output_path": str, "duration": float,
        "file_size": int, "error": str|None}``
    """
    if not os.path.isfile(source_path):
        return _error(f"Source file not found: {source_path}")

    tmp_dir = tempfile.mkdtemp(prefix="ffmpega_export_")

    try:
        # --- Step 1: Parse segments ---
        segments = _parse_segments(segments_json)
        has_edits = bool(segments)
        has_speed = _has_speed_changes(speed_map_json)
        has_crop = bool(crop_json and crop_json.strip() and crop_json != "{}")
        has_text = bool(text_overlays_json and text_overlays_json.strip()
                        and text_overlays_json != "[]")
        transitions = parse_transitions(transitions_json)
        has_transitions = bool(transitions)

        # Fast path: no edits at all → copy source
        if (not has_edits and not has_speed and not has_crop
                and not has_text and not has_transitions):
            shutil.copy2(source_path, output_path)
            return _success(output_path)

        # --- Step 2: Extract segments (with per-segment speed) ---
        if has_edits:
            needs_reencode = has_speed
            seg_files = _extract_segments(
                source_path, segments, speed_map_json,
                tmp_dir,
                reencode=needs_reencode,
            )
        else:
            # No trim — treat entire video as one segment
            seg_files = [source_path]

        if not seg_files:
            return _error("All segments failed to extract")

        # --- Step 3: Apply transitions (or simple concat) ---
        if cancel_event and cancel_event.is_set():
            return _error("Export cancelled")

        used_transitions = has_transitions and len(seg_files) > 1
        if used_transitions:
            joined_path = os.path.join(tmp_dir, "joined.mp4")
            apply_transitions(seg_files, transitions, joined_path)
            current = joined_path
        elif len(seg_files) > 1:
            joined_path = os.path.join(tmp_dir, "joined.mp4")
            current = _concat_segments(seg_files, joined_path)
        else:
            current = seg_files[0]

        # --- Step 3b: Apply text overlays (post-concat so times are global) ---
        if cancel_event and cancel_event.is_set():
            return _error("Export cancelled")

        if has_text:
            text_path = os.path.join(tmp_dir, "text.mp4")
            current = _apply_text_overlays(current, text_overlays_json, text_path)

        # --- Step 4: Apply crop ---
        if cancel_event and cancel_event.is_set():
            return _error("Export cancelled")

        if has_crop:
            cropped_path = os.path.join(tmp_dir, "cropped.mp4")
            current = apply_crop(current, crop_json, cropped_path)

        # --- Step 5: Apply audio adjustments ---
        if cancel_event and cancel_event.is_set():
            return _error("Export cancelled")

        # When transitions were applied, apply_transitions() uses -an
        # (drops audio).  We concat audio from the *extracted segments*
        # (not the original source) so audio stays in sync with any
        # trims, reorders, or speed changes.
        needs_audio_pass = (
            used_transitions
            or abs(volume - 1.0) > 0.01
            or volume < 0.001
        )
        if needs_audio_pass:
            audio_src = None
            video_duration = None
            if used_transitions:
                # Build a matching audio track from the segment files
                audio_concat = os.path.join(tmp_dir, "audio_concat.mp4")
                audio_src = _concat_segments(seg_files, audio_concat)
                # Probe xfade'd video duration so we can truncate audio to
                # match — xfade shortens the total by transition overlap.
                from .transitions import _get_duration
                video_duration = _get_duration(current) or None
            audio_path = os.path.join(tmp_dir, "audio_adj.mp4")
            current = _apply_audio(
                current, volume, audio_path, audio_src,
                match_duration=video_duration,
            )

        # --- Step 6: Move final to output ---
        if current != output_path:
            if os.path.isfile(current):
                shutil.copy2(current, output_path)
            else:
                return _error("Final render file not found")

        return _success(output_path)

    except Exception as e:
        log.exception("[VideoEditor] Export failed")
        return _error(str(e))

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _extract_segments(
    source_path: str,
    segments: list[tuple[float, float]],
    speed_map_json: str,
    tmp_dir: str,
    *,
    reencode: bool = False,
) -> list[str]:
    """Extract individual segments, applying per-segment speed filters."""
    ffmpeg = get_ffmpeg_bin()
    seg_files: list[str] = []

    for idx, (start, end) in enumerate(segments):
        duration = end - start
        if duration <= 0:
            continue

        seg_out = os.path.join(tmp_dir, f"seg_{idx:04d}.mp4")
        vf, af_speed = build_speed_filters(speed_map_json, idx)

        needs_reencode = reencode or bool(vf) or bool(af_speed)

        cmd: list[str] = [
            ffmpeg, "-y",
            "-ss", f"{start:.6f}",
            "-i", source_path,
            "-t", f"{duration:.6f}",
        ]

        if needs_reencode:
            if vf:
                cmd += ["-vf", vf]
            cmd += [
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-pix_fmt", "yuv420p",
            ]
            if af_speed:
                cmd += ["-af", af_speed, "-c:a", "aac", "-b:a", "192k"]
            else:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]

        cmd += ["-v", "warning", seg_out]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            log.warning(
                "[VideoEditor] Segment %d extract failed: %s",
                idx, result.stderr[:300],
            )
            continue

        seg_files.append(seg_out)

    return seg_files


def _apply_text_overlays(
    source_path: str,
    text_overlays_json: str,
    output_path: str,
) -> str:
    """Apply text overlays to the concatenated video.

    Text overlay times are relative to the final output timeline,
    so this must run *after* concat/transitions.
    """
    text_filters = build_drawtext_filters(text_overlays_json)
    if not text_filters:
        return source_path

    ffmpeg = get_ffmpeg_bin()
    cmd = [
        ffmpeg, "-y",
        "-i", source_path,
        "-vf", ",".join(text_filters),
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-v", "warning",
        output_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning(
            "[VideoEditor] Text overlay failed: %s", result.stderr[:300],
        )
        return source_path  # graceful fallback

    return output_path


def _concat_segments(segment_files: list[str], output_path: str) -> str:
    """Concatenate segment files via concat demuxer."""
    from .concat import concat_segments
    return concat_segments(segment_files, output_path, raise_on_error=True)


def _apply_audio(
    source_path: str,
    volume: float,
    output_path: str,
    audio_source: str | None = None,
    match_duration: float | None = None,
) -> str:
    """Apply audio volume adjustment.

    Parameters
    ----------
    source_path:
        Video file to process (may lack audio after transitions).
    volume:
        Desired volume level (0.0–2.0).
    output_path:
        Destination path.
    audio_source:
        If provided, mux audio from this file instead of *source_path*.
        Used after ``apply_transitions`` which strips audio (``-an``).
    match_duration:
        If provided, truncate the audio to this duration (seconds) to
        prevent A/V desync after xfade shortens the video.
    """
    ffmpeg = get_ffmpeg_bin()
    filt, muted = build_audio_filter(volume)

    if audio_source:
        # Mux: take video from source_path, audio from audio_source.
        # Use filter_complex with explicit stream labels to avoid
        # ambiguous -af stream selection.
        audio_input_args = ["-i", audio_source]
        if match_duration is not None and match_duration > 0:
            # Truncate audio input to match the xfade'd video length
            audio_input_args = [
                "-t", f"{match_duration:.3f}",
            ] + audio_input_args

        if muted:
            cmd = [
                ffmpeg, "-y",
                "-i", source_path,
            ] + audio_input_args + [
                "-map", "0:v",
                "-c:v", "copy",
                "-an",
                "-v", "warning", output_path,
            ]
        elif filt:
            # Volume change — use filter_complex to target stream 1 audio
            cmd = [
                ffmpeg, "-y",
                "-i", source_path,
            ] + audio_input_args + [
                "-filter_complex", f"[1:a]{filt}[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-v", "warning", output_path,
            ]
        else:
            # No volume change — just mux
            cmd = [
                ffmpeg, "-y",
                "-i", source_path,
            ] + audio_input_args + [
                "-map", "0:v",
                "-map", "1:a?",
                "-c:v", "copy",
                "-c:a", "copy",
                "-v", "warning", output_path,
            ]
    else:
        audio_args = get_audio_args(volume)
        cmd = [
            ffmpeg, "-y",
            "-i", source_path,
            "-c:v", "copy",
        ] + audio_args + ["-v", "warning", output_path]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning("[VideoEditor] Audio adjust failed: %s", result.stderr[:300])
        raise RuntimeError(
            f"Audio adjust failed (rc={result.returncode}): {result.stderr[:300]}"
        )

    return output_path


def _has_speed_changes(speed_map_json: str) -> bool:
    """Check if any segment has a non-1.0 speed."""
    if not speed_map_json or not speed_map_json.strip():
        return False
    try:
        data = json.loads(speed_map_json)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    return any(abs(float(v) - 1.0) > 0.01 for v in data.values())


def _success(output_path: str) -> dict:
    """Build a success result dict."""
    file_size = 0
    duration = 0.0
    try:
        file_size = os.path.getsize(output_path)
    except OSError:
        pass

    # Probe duration
    ffprobe = get_ffprobe_bin()
    try:
        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-print_format", "csv=p=0",
            output_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
    except Exception:
        pass

    return {
        "success": True,
        "output_path": output_path,
        "duration": duration,
        "file_size": file_size,
        "error": None,
    }


def _error(message: str) -> dict:
    """Build an error result dict."""
    return {
        "success": False,
        "output_path": "",
        "duration": 0.0,
        "file_size": 0,
        "error": message,
    }
