"""FFmpeg-based relighting for the Video Editor export pipeline.

Provides a directional lighting simulation using FFmpeg filter expressions
without requiring an AI model. The math:

1. Convert to luminance → approximate normals from gradients
2. Compute dot(normal, light_dir) for Lambertian shading
3. Blend the shading map with the original via colorbalance + curves + eq

When ``ai_normals`` is enabled, NormalCrafter generates real surface normals
from the video, and per-pixel dot(normal, light_dir) Lambertian shading is
composited frame-by-frame in Python for physically-accurate relighting.
"""

from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("ffmpega.videoeditor")

# Default relight state — matches RelightPanel.ts defaults
_DEFAULTS = {
    "azimuth": 0.0,      # degrees, 0=front, 90=right, -90=left
    "elevation": 45.0,    # degrees above horizon
    "intensity": 1.0,     # light intensity multiplier
    "ambient": 0.3,       # ambient fill level
    "color_r": 255,       # light color RGB
    "color_g": 255,
    "color_b": 255,
    "ai_normals": False,  # use NormalCrafter for real surface normals
    "enabled": False,
}


def build_relight_filters(relight_json: str) -> list[str]:
    """Build FFmpeg -vf filter chain for directional relighting.

    Uses a combination of:
    - ``eq`` for global brightness/contrast adjustment based on light direction
    - ``colorbalance`` for light color tinting
    - ``curves`` for shading curvature

    When ``ai_normals`` is enabled, returns an empty list — the AI pipeline
    handles compositing separately via :func:`apply_ai_relight`.

    Parameters
    ----------
    relight_json:
        JSON string with azimuth, elevation, intensity, ambient, color fields.

    Returns
    -------
    list[str]
        List of FFmpeg -vf filter strings. Empty if no relighting needed.
    """
    if not relight_json or not relight_json.strip() or relight_json == "{}":
        return []

    try:
        state = json.loads(relight_json)
    except (json.JSONDecodeError, TypeError):
        log.warning("[VideoEditor] Invalid relight JSON: %.100s", relight_json)
        return []

    if not isinstance(state, dict):
        return []

    if not state.get("enabled", False):
        return []

    # AI normals mode — compositing is done by apply_ai_relight(), not filters
    if state.get("ai_normals", False):
        return []

    azimuth = float(state.get("azimuth", 0.0))
    elevation = float(state.get("elevation", 45.0))
    intensity = max(0.0, min(3.0, float(state.get("intensity", 1.0))))
    ambient = max(0.0, min(1.0, float(state.get("ambient", 0.3))))
    color_r = int(state.get("color_r", 255))
    color_g = int(state.get("color_g", 255))
    color_b = int(state.get("color_b", 255))

    filters: list[str] = []

    # Compute light direction vector from azimuth/elevation
    az_rad = math.radians(azimuth)
    el_rad = math.radians(elevation)
    # Light comes FROM the specified direction
    lx = math.sin(az_rad) * math.cos(el_rad)
    ly = -math.sin(el_rad)  # negative = from above
    lz = math.cos(az_rad) * math.cos(el_rad)

    # --- Brightness: simulate directional light ---
    # Higher elevation → less extreme side-lighting
    # Front light (az=0) → neutral brightness
    # Side light → slight brightness reduction simulating shadow side
    brightness_shift = -0.1 * abs(lx) * intensity
    contrast_boost = 1.0 + 0.15 * intensity * (1.0 - ambient)

    eq_parts = []
    if abs(brightness_shift) > 0.01:
        eq_parts.append(f"brightness={brightness_shift:.3f}")
    if abs(contrast_boost - 1.0) > 0.01:
        eq_parts.append(f"contrast={contrast_boost:.3f}")

    if eq_parts:
        filters.append(f"eq={':'.join(eq_parts)}")

    # --- Color tinting from light color ---
    # Normalize to [-1, 1] range for colorbalance
    r_norm = (color_r / 255.0 - 0.5) * 0.4 * intensity
    g_norm = (color_g / 255.0 - 0.5) * 0.4 * intensity
    b_norm = (color_b / 255.0 - 0.5) * 0.4 * intensity

    if abs(r_norm) > 0.01 or abs(g_norm) > 0.01 or abs(b_norm) > 0.01:
        filters.append(
            f"colorbalance="
            f"rm={r_norm:.3f}:gm={g_norm:.3f}:bm={b_norm:.3f}:"
            f"rh={r_norm * 0.5:.3f}:gh={g_norm * 0.5:.3f}:bh={b_norm * 0.5:.3f}"
        )

    # --- Directional shadow simulation via curves ---
    # Side lighting deepens shadows, top lighting is more even
    shadow_depth = max(0.0, abs(lx) * 0.3 * intensity * (1.0 - ambient))
    if shadow_depth > 0.02:
        # Darken shadows using a curves S-curve
        filters.append(
            f"curves=m='0/0 0.25/{max(0, 0.15 - shadow_depth):.2f} "
            f"0.5/0.5 0.75/{min(1, 0.85 + shadow_depth * 0.3):.2f} 1/1'"
        )

    return filters


def has_relight(relight_json: str) -> bool:
    """Quick check whether relighting is enabled."""
    if not relight_json or not relight_json.strip() or relight_json == "{}":
        return False
    try:
        state = json.loads(relight_json)
        return bool(state.get("enabled", False))
    except (json.JSONDecodeError, TypeError):
        return False


def needs_ai_normals(relight_json: str) -> bool:
    """Check whether the relight state requires AI normal map generation."""
    if not relight_json or not relight_json.strip() or relight_json == "{}":
        return False
    try:
        state = json.loads(relight_json)
        return (
            bool(state.get("enabled", False))
            and bool(state.get("ai_normals", False))
        )
    except (json.JSONDecodeError, TypeError):
        return False


def apply_ai_relight(
    video_path: str,
    relight_json: str,
    output_path: str | None = None,
) -> str:
    """Apply physically-based relighting using NormalCrafter normal maps.

    Pipeline:
    1. Run NormalCrafter to get per-frame normal vectors (T, H, W, 3)
    2. Read original video frames
    3. For each frame, compute per-pixel Lambertian shading:
       ``shade = ambient + intensity * max(0, dot(normal, light_dir))``
    4. Tint with light color: ``out = original * shade * light_color``
    5. Encode the result via ffmpeg

    Parameters
    ----------
    video_path:
        Path to the input video.
    relight_json:
        JSON string with azimuth, elevation, intensity, ambient, color,
        ai_normals=True.
    output_path:
        Optional output path. If None, generates a temp file.

    Returns
    -------
    str
        Path to the relit output video.
    """
    import cv2
    import numpy as np

    state = json.loads(relight_json)
    azimuth = float(state.get("azimuth", 0.0))
    elevation = float(state.get("elevation", 45.0))
    intensity = max(0.0, min(3.0, float(state.get("intensity", 1.0))))
    ambient = max(0.0, min(1.0, float(state.get("ambient", 0.3))))
    color_r = int(state.get("color_r", 255)) / 255.0
    color_g = int(state.get("color_g", 255)) / 255.0
    color_b = int(state.get("color_b", 255)) / 255.0

    # Compute light direction vector
    az_rad = math.radians(azimuth)
    el_rad = math.radians(elevation)
    light_dir = np.array([
        math.sin(az_rad) * math.cos(el_rad),
        -math.sin(el_rad),
        math.cos(az_rad) * math.cos(el_rad),
    ], dtype=np.float32)

    # --- Get normals from NormalCrafter ---
    log.info("[VideoEditor] Running NormalCrafter for AI relighting...")
    try:
        try:
            from core.normalcrafter_synthesizer import (
                run_normalcrafter_frames,
            )
        except ImportError:
            from ...core.normalcrafter_synthesizer import (  # type: ignore
                run_normalcrafter_frames,
            )
    except ImportError as exc:
        raise RuntimeError(
            "NormalCrafter is not available for AI relighting. "
            "Install with: pip install --no-deps "
            "git+https://github.com/Binyr/NormalCrafter.git"
        ) from exc

    normals, fps = run_normalcrafter_frames(
        video_path=video_path,
        max_res=1024,
    )
    # normals: shape (T, H, W, 3), range [-1, 1]

    # --- Read original video frames ---
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    orig_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # --- Composite each frame ---
    tmp_dir = tempfile.mkdtemp(prefix="relight_ai_")
    n_frames = normals.shape[0]
    normal_h, normal_w = normals.shape[1], normals.shape[2]

    log.info(
        "[VideoEditor] Compositing %d frames with AI normals (%dx%d)",
        n_frames, normal_w, normal_h,
    )

    frame_idx = 0
    written = 0
    while True:
        ret, frame = cap.read()
        if not ret or written >= n_frames:
            break

        # Resize original frame to match normal map resolution if needed
        if frame.shape[1] != normal_w or frame.shape[0] != normal_h:
            frame = cv2.resize(
                frame, (normal_w, normal_h),
                interpolation=cv2.INTER_AREA,
            )

        # Get normal for this frame
        normal = normals[written]  # (H, W, 3), range [-1, 1]

        # Compute per-pixel Lambertian shading
        # dot(normal, light_dir) → (H, W)
        dot_product = np.sum(normal * light_dir, axis=-1)
        dot_product = np.clip(dot_product, 0.0, 1.0)

        # shade = ambient + intensity * dot_product
        shade = ambient + intensity * dot_product
        shade = np.clip(shade, 0.0, 2.0)

        # Apply light color tint
        # shade_rgb shape: (H, W, 3)
        shade_rgb = np.stack([
            shade * color_r,
            shade * color_g,
            shade * color_b,
        ], axis=-1).astype(np.float32)

        # Apply to original frame (BGR → multiply → clip)
        frame_float = frame.astype(np.float32) / 255.0
        relit = frame_float * shade_rgb
        relit = np.clip(relit * 255.0, 0, 255).astype(np.uint8)

        cv2.imwrite(
            os.path.join(tmp_dir, f"{written:06d}.png"),
            relit,
        )
        written += 1

    cap.release()

    log.info("[VideoEditor] Wrote %d relit frames, encoding...", written)

    # --- Encode frames to output ---
    if output_path is None:
        _fd, output_path = tempfile.mkstemp(suffix="_ai_relit.mp4")
        os.close(_fd)

    try:
        from core.bin_paths import get_ffmpeg_bin
    except ImportError:
        from ...core.bin_paths import get_ffmpeg_bin  # type: ignore

    fps_str = f"{fps:.2f}" if fps != int(fps) else str(int(fps))
    cmd = [
        get_ffmpeg_bin(), "-y",
        "-framerate", fps_str,
        "-i", os.path.join(tmp_dir, "%06d.png"),
        "-i", video_path,         # for audio
        "-map", "0:v",
        "-map", "1:a?",
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v", "libx264",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("AI relight encode failed: %s", proc.stderr[-500:])
        raise RuntimeError(f"AI relight ffmpeg encode failed:\n{proc.stderr[-500:]}")

    # Cleanup temp frames
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    log.info("[VideoEditor] AI relight output: %s", output_path)
    return output_path
