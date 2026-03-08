"""Spatial crop via FFmpeg crop filter.

Applies a ``crop=w:h:x:y`` video filter.  Coordinates are clamped to
the source video dimensions to prevent FFmpeg errors.
"""

from __future__ import annotations

import json
import logging
import subprocess

try:
    from ...core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
except (ImportError, ValueError):
    import shutil
    def get_ffmpeg_bin() -> str:
        return shutil.which("ffmpeg") or "ffmpeg"
    def get_ffprobe_bin() -> str:
        return shutil.which("ffprobe") or "ffprobe"

log = logging.getLogger("ffmpega.videoeditor")


def apply_crop(
    source_path: str,
    crop_json: str,
    output_path: str,
) -> str:
    """Crop *source_path* according to the rectangle in *crop_json*.

    Parameters
    ----------
    source_path:
        Input video file.
    crop_json:
        JSON string ``{"x": N, "y": N, "w": N, "h": N}`` or empty
        string for no crop.
    output_path:
        Destination file path.

    Returns
    -------
    str
        *output_path* on success, *source_path* if no crop applied.
    """
    rect = _parse_crop_rect(crop_json)
    if rect is None:
        return source_path

    x, y, w, h = rect

    # Clamp to source dimensions
    src_w, src_h = _probe_dimensions(source_path)
    if src_w > 0 and src_h > 0:
        x = max(0, min(x, src_w - 1))
        y = max(0, min(y, src_h - 1))
        w = min(w, src_w - x)
        h = min(h, src_h - y)

    if w <= 0 or h <= 0:
        return source_path

    # Ensure even dimensions (required for yuv420p)
    w = w if w % 2 == 0 else w - 1
    h = h if h % 2 == 0 else h - 1

    ffmpeg = get_ffmpeg_bin()
    cmd = [
        ffmpeg, "-y",
        "-i", source_path,
        "-vf", f"crop={w}:{h}:{x}:{y}",
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
        log.warning("[VideoEditor] Crop failed: %s", result.stderr[:300])
        return source_path

    return output_path


def _parse_crop_rect(
    crop_json: str,
) -> tuple[int, int, int, int] | None:
    """Parse crop JSON into (x, y, w, h) or None."""
    if not crop_json or not crop_json.strip():
        return None
    try:
        data = json.loads(crop_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    try:
        x = int(data["x"])
        y = int(data["y"])
        w = int(data["w"])
        h = int(data["h"])
    except (KeyError, ValueError, TypeError):
        return None

    if w <= 0 or h <= 0:
        return None

    return (x, y, w, h)


def _probe_dimensions(video_path: str) -> tuple[int, int]:
    """Probe video width and height.  Returns (0, 0) on failure."""
    ffprobe = get_ffprobe_bin()
    try:
        cmd = [
            ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-print_format", "csv=p=0:s=x",
            video_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and "x" in result.stdout:
            parts = result.stdout.strip().split("x")
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 0, 0
