"""Transition effects between segments via FFmpeg xfade filter.

Supports crossfade and dip-to-black (fade) transitions with
configurable duration.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile

try:
    from ...core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
except (ImportError, ValueError):
    def get_ffmpeg_bin() -> str:
        return shutil.which("ffmpeg") or "ffmpeg"
    def get_ffprobe_bin() -> str:
        return shutil.which("ffprobe") or "ffprobe"

log = logging.getLogger("ffmpega.videoeditor")

# Supported transition types (maps to FFmpeg xfade transition names)
TRANSITION_TYPES = {
    "crossfade": "fade",       # xfade's "fade" = crossfade
    "dip_to_black": "fadeblack",
    "fadewhite": "fadewhite",
    "wipeleft": "wipeleft",
    "wiperight": "wiperight",
    "slideup": "slideup",
    "slidedown": "slidedown",
}

_DEFAULT_TRANSITION_DURATION = 0.5  # seconds


def parse_transitions(transitions_json: str) -> list[dict]:
    """Parse a transitions JSON config.

    Parameters
    ----------
    transitions_json:
        JSON array of transition objects::

            [
                {
                    "after_segment": 0,    // transition between seg 0 and seg 1
                    "type": "crossfade",   // or "dip_to_black", etc.
                    "duration": 0.5        // seconds
                },
                ...
            ]

    Returns
    -------
    list[dict]
        Parsed and validated transition dicts.
    """
    if not transitions_json or not transitions_json.strip():
        return []
    try:
        data = json.loads(transitions_json)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(data, list):
        return []

    result: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        t_type = str(item.get("type", "crossfade"))
        if t_type not in TRANSITION_TYPES:
            t_type = "crossfade"
        try:
            duration = float(item.get("duration", _DEFAULT_TRANSITION_DURATION))
        except (ValueError, TypeError):
            duration = _DEFAULT_TRANSITION_DURATION
        duration = max(0.1, min(5.0, duration))

        try:
            after_seg = int(item["after_segment"])
        except (KeyError, ValueError, TypeError):
            continue

        result.append({
            "after_segment": after_seg,
            "type": t_type,
            "duration": duration,
        })

    return result


def apply_transitions(
    segment_files: list[str],
    transitions: list[dict],
    output_path: str,
) -> str:
    """Apply transitions between pre-trimmed segment files.

    Uses FFmpeg ``xfade`` filter to blend consecutive segments.
    If no transitions apply, falls back to simple concat.

    Parameters
    ----------
    segment_files:
        Paths to individual segment video files.
    transitions:
        Parsed transition dicts (from ``parse_transitions``).
    output_path:
        Destination file path.

    Returns
    -------
    str
        *output_path* on success, or first segment file on failure.
    """
    if len(segment_files) < 2 or not transitions:
        return _simple_concat(segment_files, output_path)

    # Index transitions by the segment they follow
    transition_map: dict[int, dict] = {}
    for t in transitions:
        idx = t["after_segment"]
        if 0 <= idx < len(segment_files) - 1:
            transition_map[idx] = t

    if not transition_map:
        return _simple_concat(segment_files, output_path)

    ffmpeg = get_ffmpeg_bin()

    # Build xfade filter chain
    # For N segments with transitions, we chain xfade filters:
    # [0:v][1:v]xfade=...[v01]; [v01][2:v]xfade=...[v012]; etc.
    inputs: list[str] = []
    for sf in segment_files:
        inputs += ["-i", sf]

    filter_parts: list[str] = []
    prev_label = "[0:v]"
    offset = 0.0

    # We need segment durations to compute xfade offsets
    durations = [_get_duration(sf) for sf in segment_files]

    for i in range(len(segment_files) - 1):
        t_info = transition_map.get(i)

        if t_info is None:
            # No transition — just concat (handled differently)
            # For simplicity, use a very short crossfade (0.01s)
            t_type = "fade"
            t_dur = 0.0
        else:
            t_type = TRANSITION_TYPES.get(t_info["type"], "fade")
            t_dur = t_info["duration"]

        # xfade offset = accumulated duration minus transition overlap
        seg_dur = durations[i] if durations[i] > 0 else 1.0
        offset = max(0, offset + seg_dur - t_dur)

        out_label = f"[v{i + 1}]" if i < len(segment_files) - 2 else "[vout]"
        next_input = f"[{i + 1}:v]"

        if t_dur > 0:
            filter_parts.append(
                f"{prev_label}{next_input}xfade="
                f"transition={t_type}:duration={t_dur:.3f}:"
                f"offset={offset:.3f}{out_label}"
            )
        else:
            # No transition, simple concat via overlay at correct offset
            filter_parts.append(
                f"{prev_label}{next_input}xfade="
                f"transition=fade:duration=0.01:"
                f"offset={offset:.3f}{out_label}"
            )

        prev_label = out_label

    filter_complex = ";".join(filter_parts)

    cmd = [ffmpeg, "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",  # audio handling is done separately
        "-v", "warning",
        output_path,
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        log.warning(
            "[VideoEditor] Transition apply failed: %s", result.stderr[:300],
        )
        return _simple_concat(segment_files, output_path)

    return output_path


def _get_duration(video_path: str) -> float:
    """Get video duration in seconds.  Returns 0.0 on failure."""
    ffprobe = get_ffprobe_bin()
    try:
        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-print_format", "csv=p=0",
            video_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0


def _simple_concat(
    segment_files: list[str],
    output_path: str,
) -> str:
    """Concatenate files without transitions using concat demuxer."""
    from .concat import concat_segments
    return concat_segments(segment_files, output_path, raise_on_error=False)
