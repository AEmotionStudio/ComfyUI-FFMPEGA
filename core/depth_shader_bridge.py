"""Depth-shader bridge — orchestrates VDA depth prepass + SAM3 mask composition.

Generates depth maps via Video Depth Anything, combines them with optional
SAM3 object masks, and produces composite blend masks for depth-aware shader
application.

Depth modes:
    foreground_focus — shader strongest on near objects (depth=close → opacity=1)
    background_focus — shader strongest on far objects (inverted)
    depth_outline    — shader on depth discontinuities only (Sobel on depth)
    atmospheric      — gradual depth fade (fog/haze simulation)
    full_depth       — pass raw depth as-is (for custom blending)
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("ffmpega.depth_shader")

DEPTH_MODES = [
    "none",
    "foreground_focus",
    "background_focus",
    "depth_outline",
    "atmospheric",
    "full_depth",
]

DEPTH_ENCODERS = ["vits", "vitb", "vitl"]

# Shader presets that read depth per-pixel via side-by-side packing.
# When these are selected, the pipeline auto-enables VDA + SBS even
# if depth_mode is "none".
DEPTH_NATIVE_SHADERS: set[str] = {
    "toon_3d",
    "depth_fog",
    "focus_pull",
    "relief_sculpt",
    "depth_watercolor",
}


def is_depth_native(preset_name: str) -> bool:
    """Check if a shader preset requires the depth SBS pipeline."""
    return preset_name in DEPTH_NATIVE_SHADERS


def pack_sbs(
    video_path: str,
    depth_path: str | None = None,
    normals_path: str | None = None,
) -> str | None:
    """Pack original + depth and/or normals side-by-side.

    Layouts:
        depth only      → [original | depth]   = 2W×H
        normals only    → [original | normals]  = 2W×H
        depth + normals → [original | depth | normals] = 3W×H

    Args:
        video_path: Path to original video.
        depth_path: Path to grayscale depth video (optional).
        normals_path: Path to RGB normal map video (optional).

    Returns:
        Path to the packed SBS video, or None on failure.
    """
    if not depth_path and not normals_path:
        log.warning("[DepthBridge] pack_sbs called with no depth or normals")
        return None

    ffmpeg = _get_ffmpeg()
    temp_dir = tempfile.mkdtemp(prefix="ffmpega_sbs_pack_")
    packed_path = os.path.join(temp_dir, "sbs_packed.mp4")

    # Probe original dimensions to scale AI outputs to match
    w, h = _probe_dimensions(ffmpeg, video_path)

    inputs = ["-i", video_path]
    panels = ["[0:v]setpts=PTS-STARTPTS[p0]"]
    stack_inputs = ["[p0]"]
    idx = 1

    if depth_path:
        inputs.extend(["-i", depth_path])
        panels.append(
            f"[{idx}:v]setpts=PTS-STARTPTS,scale={w}:{h}:flags=bilinear,"
            f"format=rgb24[p{idx}]"
        )
        stack_inputs.append(f"[p{idx}]")
        idx += 1

    if normals_path:
        inputs.extend(["-i", normals_path])
        panels.append(
            f"[{idx}:v]setpts=PTS-STARTPTS,scale={w}:{h}:flags=bilinear,"
            f"format=rgb24[p{idx}]"
        )
        stack_inputs.append(f"[p{idx}]")
        idx += 1

    n_panels = len(stack_inputs)
    fc = (
        ";".join(panels) + ";"
        + "".join(stack_inputs)
        + f"hstack=inputs={n_panels}[out]"
    )

    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", fc,
        "-map", "[out]",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        packed_path,
    ]

    log.info(
        "[DepthBridge] SBS pack (%d panels): %s",
        n_panels, " ".join(cmd),
    )
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log.error(
                "[DepthBridge] SBS pack failed (rc=%d): %s",
                result.returncode, result.stderr[-500:] if result.stderr else "",
            )
            return None
    except subprocess.TimeoutExpired:
        log.error("[DepthBridge] SBS pack timed out")
        return None

    if os.path.isfile(packed_path) and os.path.getsize(packed_path) > 0:
        log.info("[DepthBridge] SBS packed (%d panels): %s", n_panels, packed_path)
        return packed_path
    return None


def unpack_sbs(
    sbs_path: str,
    original_path: str | None = None,
    panel_count: int = 2,
) -> str | None:
    """Crop the left panel from a multi-panel SBS video.

    Args:
        sbs_path: Path to the shader-processed SBS video.
        original_path: Optional original video for audio copy.
        panel_count: Number of panels (2 or 3). Determines crop width.

    Returns:
        Path to the cropped W×H result, or None on failure.
    """
    ffmpeg = _get_ffmpeg()
    temp_dir = tempfile.mkdtemp(prefix="ffmpega_sbs_unpack_")
    unpacked_path = os.path.join(temp_dir, "sbs_unpacked.mp4")

    # Crop left panel: iw/N : ih : 0 : 0
    vf = f"crop=iw/{panel_count}:ih:0:0"

    cmd = [
        ffmpeg, "-y",
        "-i", sbs_path,
    ]

    if original_path and os.path.isfile(original_path):
        cmd.extend(["-i", original_path])

    cmd.extend([
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
    ])

    if original_path and os.path.isfile(original_path):
        cmd.extend(["-c:a", "copy", "-map", "0:v", "-map", "1:a?"])

    cmd.append(unpacked_path)

    log.info("[DepthBridge] SBS unpack (%d panels): %s", panel_count, " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log.error(
                "[DepthBridge] SBS unpack failed (rc=%d): %s",
                result.returncode, result.stderr[-500:] if result.stderr else "",
            )
            return None
    except subprocess.TimeoutExpired:
        log.error("[DepthBridge] SBS unpack timed out")
        return None

    if os.path.isfile(unpacked_path) and os.path.getsize(unpacked_path) > 0:
        log.info("✅ [DepthBridge] SBS unpacked: %s", unpacked_path)
        return unpacked_path
    return None


def generate_depth_map(
    video_path: str,
    encoder: str = "vits",
    input_size: int = 518,
    max_res: int = 1280,
) -> str | None:
    """Run VDA to produce a grayscale depth video.

    Args:
        video_path: Path to source video.
        encoder: VDA model variant (vits, vitb, vitl).
        input_size: Model input resolution.
        max_res: Maximum video resolution for processing.

    Returns:
        Path to the grayscale depth video, or None on failure.
    """
    try:
        try:
            from .vda_synthesizer import run_video_depth
        except ImportError:
            from core.vda_synthesizer import run_video_depth  # type: ignore
    except ImportError:
        log.error(
            "[DepthBridge] Video Depth Anything not available. "
            "Ensure core/vda_synthesizer.py exists."
        )
        return None

    try:
        depth_path = run_video_depth(
            input_path=video_path,
            encoder=encoder,
            input_size=input_size,
            max_res=max_res,
            colormap="gray",  # Grayscale for mask usage
        )
        if depth_path and os.path.isfile(depth_path):
            log.info("[DepthBridge] VDA depth map: %s", depth_path)
            return depth_path
    except Exception as exc:
        log.error("[DepthBridge] VDA inference failed: %s", exc)

    return None


def generate_normal_map(
    video_path: str,
    max_res: str | int = "auto",
) -> str | None:
    """Run NormalCrafter to produce an RGB normal map video.

    Args:
        video_path: Path to source video.
        max_res: Maximum resolution ("auto" for GPU-tuned, or int).

    Returns:
        Path to the RGB normal map video, or None on failure.
    """
    try:
        try:
            from .normalcrafter_synthesizer import run_normalcrafter
        except ImportError:
            from core.normalcrafter_synthesizer import run_normalcrafter  # type: ignore
    except ImportError:
        log.error(
            "[DepthBridge] NormalCrafter not available. "
            "Ensure core/normalcrafter_synthesizer.py exists."
        )
        return None

    try:
        normals_path = run_normalcrafter(
            video_path=video_path,
            max_res=max_res,
        )
        if normals_path and os.path.isfile(normals_path):
            log.info("[DepthBridge] NormalCrafter normal map: %s", normals_path)
            return normals_path
    except Exception as exc:
        log.error("[DepthBridge] NormalCrafter inference failed: %s", exc)

    return None


def _get_ffmpeg() -> str:
    """Get FFmpeg binary path."""
    try:
        from .bin_paths import get_ffmpeg_bin
    except ImportError:
        from core.bin_paths import get_ffmpeg_bin  # type: ignore
    return get_ffmpeg_bin()


def _probe_dimensions(ffmpeg: str, video_path: str) -> tuple[int, int]:
    """Probe a video file for its width and height.

    Args:
        ffmpeg: Path to ffmpeg binary (ffprobe is sibling).
        video_path: Path to video to probe.

    Returns:
        (width, height) tuple. Falls back to (1280, 720) on failure.
    """
    # Derive ffprobe path from ffmpeg
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    if not os.path.isfile(ffprobe):
        ffprobe = "ffprobe"

    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("x")
            if len(parts) == 2:
                w, h = int(parts[0]), int(parts[1])
                log.info("[DepthBridge] Probed dimensions: %dx%d", w, h)
                return (w, h)
    except Exception as exc:
        log.warning("[DepthBridge] Probe failed: %s", exc)

    log.warning("[DepthBridge] Could not probe dimensions, using 1280x720 fallback")
    return (1280, 720)


def _process_depth_for_mode(
    depth_path: str,
    mode: str,
    strength: float = 1.0,
) -> str:
    """Transform a raw depth video into a blend mask according to mode.

    Args:
        depth_path: Path to grayscale depth video (white=far, black=near).
        mode: Depth mode name.
        strength: How much depth modulates (0–1). At 0 = no depth effect.

    Returns:
        Path to the processed mask video (grayscale, white=apply shader).
    """
    ffmpeg = _get_ffmpeg()
    temp_dir = tempfile.mkdtemp(prefix="ffmpega_depth_mask_")
    mask_path = os.path.join(temp_dir, "depth_mask.mp4")

    # VDA outputs: white=far, black=near (standard depth convention)
    if mode == "foreground_focus":
        # Invert: near=white (apply shader to foreground)
        # Strength: blend between full-white and depth mask
        if strength >= 1.0:
            vf = "negate"
        else:
            vf = (
                f"split[a][b];"
                f"[a]negate[neg];"
                f"[b]color=white:size=2x2,format=gray[white];"
                f"[neg][white]blend=all_mode=normal:all_opacity={strength}"
            )
    elif mode == "background_focus":
        # Keep as-is: far=white (apply shader to background)
        if strength >= 1.0:
            vf = "null"
        else:
            vf = (
                f"split[a][b];"
                f"[a]null[orig];"
                f"[b]color=white:size=2x2,format=gray[white];"
                f"[orig][white]blend=all_mode=normal:all_opacity={strength}"
            )
    elif mode == "depth_outline":
        # Sobel edge detection on depth = outlines at depth discontinuities
        # This is the key technique for toon-style silhouette edges
        vf = (
            "format=gray,"
            "edgedetect=low=0.05:high=0.15:mode=colormix,"
            "format=gray,"
            "eq=contrast=3.0:brightness=0.1"
        )
        if strength < 1.0:
            vf = (
                f"split[a][b];"
                f"[a]format=gray,"
                f"edgedetect=low=0.05:high=0.15:mode=colormix,"
                f"format=gray,"
                f"eq=contrast=3.0:brightness=0.1[edges];"
                f"[b]color=black:size=2x2,format=gray[black];"
                f"[edges][black]blend=all_mode=normal:all_opacity={strength}"
            )
    elif mode == "atmospheric":
        # Gradual fade: gamma-correct depth for natural falloff
        vf = "eq=gamma=0.5:brightness=-0.1"
        if strength < 1.0:
            vf = (
                f"split[a][b];"
                f"[a]eq=gamma=0.5:brightness=-0.1[atmo];"
                f"[b]color=white:size=2x2,format=gray[white];"
                f"[atmo][white]blend=all_mode=normal:all_opacity={strength}"
            )
    elif mode == "full_depth":
        # Raw depth as-is
        vf = "null"
    else:
        log.warning("[DepthBridge] Unknown depth mode '%s', using raw", mode)
        vf = "null"

    # Simple filter (no filter_complex needed for most modes)
    if "split" not in vf:
        cmd = [
            ffmpeg, "-y", "-i", depth_path,
            "-vf", vf,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            mask_path,
        ]
    else:
        cmd = [
            ffmpeg, "-y", "-i", depth_path,
            "-filter_complex", vf,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            mask_path,
        ]

    log.info("[DepthBridge] Processing depth mask (mode=%s): %s", mode, " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log.error(
                "[DepthBridge] Depth mask processing failed (rc=%d): %s",
                result.returncode, result.stderr[-500:] if result.stderr else "",
            )
            return depth_path  # Fall back to raw depth
    except subprocess.TimeoutExpired:
        log.error("[DepthBridge] Depth mask processing timed out")
        return depth_path

    if os.path.isfile(mask_path) and os.path.getsize(mask_path) > 0:
        return mask_path
    return depth_path


def generate_combined_mask(
    video_path: str,
    depth_path: str,
    sam3_mask_path: str | None,
    depth_mode: str = "foreground_focus",
    depth_strength: float = 1.0,
) -> str:
    """Generate a final composite mask from depth and optional SAM3 mask.

    When both SAM3 and depth are provided, the masks are multiplied:
    ``final_mask = sam3_mask × depth_mask``. This gives continuous 0–1
    weighting within the object region.

    Args:
        video_path: Original video path (for metadata/dimensions).
        depth_path: Grayscale depth video from VDA.
        sam3_mask_path: Binary mask from SAM3 (or None if depth-only).
        depth_mode: How to transform depth into a blend mask.
        depth_strength: Strength of depth modulation (0–1).

    Returns:
        Path to the final composite mask video.
    """
    # Process depth according to mode
    processed_depth = _process_depth_for_mode(
        depth_path, depth_mode, depth_strength,
    )

    if sam3_mask_path is None or not os.path.isfile(sam3_mask_path):
        # Depth-only: use processed depth as mask directly
        return processed_depth

    # SAM3 + Depth: multiply the two masks
    ffmpeg = _get_ffmpeg()
    temp_dir = tempfile.mkdtemp(prefix="ffmpega_combo_mask_")
    combined_path = os.path.join(temp_dir, "combined_mask.mp4")

    # Probe original video to get reference dimensions
    w, h = _probe_dimensions(ffmpeg, video_path)

    # Multiply: sam3_mask × depth_mask
    # Both inputs are scaled to match original dimensions, then blended.
    fc = (
        f"[0:v]format=gray,scale={w}:{h}:flags=bilinear[mask];"
        f"[1:v]format=gray,scale={w}:{h}:flags=bilinear[depth];"
        f"[mask][depth]blend=all_mode=multiply[out]"
    )

    cmd = [
        ffmpeg, "-y",
        "-i", sam3_mask_path,     # [0] SAM3 binary mask
        "-i", processed_depth,    # [1] processed depth mask
        "-filter_complex", fc,
        "-map", "[out]",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        combined_path,
    ]

    log.info("[DepthBridge] Combining SAM3 + depth masks: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log.error(
                "[DepthBridge] Mask combination failed (rc=%d): %s",
                result.returncode, result.stderr[-500:] if result.stderr else "",
            )
            return processed_depth
    except subprocess.TimeoutExpired:
        log.error("[DepthBridge] Mask combination timed out")
        return processed_depth

    if os.path.isfile(combined_path) and os.path.getsize(combined_path) > 0:
        log.info("[DepthBridge] Combined mask: %s", combined_path)
        return combined_path

    return processed_depth


def composite_with_depth_mask(
    original_path: str,
    shaded_path: str,
    mask_path: str,
    invert: bool = False,
) -> str | None:
    """Composite shaded video onto original using a depth/combined mask.

    Uses FFmpeg maskedmerge: where mask is white → use shaded,
    where mask is black → use original (or inverted).

    All inputs are scaled to the shaded video's dimensions before merging
    to prevent dimension mismatch errors.

    Args:
        original_path: Path to original video.
        shaded_path: Path to shader-processed video.
        mask_path: Path to depth/combined mask video.
        invert: If True, invert the mask before compositing.

    Returns:
        Path to composited output, or None on failure.
    """
    ffmpeg = _get_ffmpeg()
    temp_dir = tempfile.mkdtemp(prefix="ffmpega_depth_comp_")
    output_path = os.path.join(temp_dir, "depth_composite.mp4")

    # Probe shaded video dimensions as the reference
    w, h = _probe_dimensions(ffmpeg, shaded_path)

    if invert:
        fc = (
            f"[0:v]scale={w}:{h}:flags=bilinear,format=yuv420p[shaded];"
            f"[1:v]format=gray,scale={w}:{h}:flags=bilinear[mask];"
            f"[2:v]scale={w}:{h}:flags=bilinear,format=yuv420p[orig];"
            f"[shaded][orig][mask]maskedmerge[_vout]"
        )
    else:
        fc = (
            f"[0:v]scale={w}:{h}:flags=bilinear,format=yuv420p[shaded];"
            f"[1:v]format=gray,scale={w}:{h}:flags=bilinear[mask];"
            f"[2:v]scale={w}:{h}:flags=bilinear,format=yuv420p[orig];"
            f"[orig][shaded][mask]maskedmerge[_vout]"
        )

    cmd = [
        ffmpeg, "-y",
        "-i", shaded_path,     # [0] shaded video
        "-i", mask_path,       # [1] mask
        "-i", original_path,   # [2] original
        "-filter_complex", fc,
        "-map", "[_vout]",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-map", "0:a?",
        output_path,
    ]

    log.info("[DepthBridge] Depth composite: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            log.error(
                "[DepthBridge] Composite failed (rc=%d): %s",
                result.returncode, result.stderr[-500:] if result.stderr else "",
            )
            return None
    except subprocess.TimeoutExpired:
        log.error("[DepthBridge] Composite timed out")
        return None

    if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
        log.info("✅ [DepthBridge] Depth-composite output: %s", output_path)
        return output_path

    return None
