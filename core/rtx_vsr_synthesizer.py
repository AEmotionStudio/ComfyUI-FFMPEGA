# coding: utf-8
"""NVIDIA RTX Video Super Resolution integration for FFMPEGA.

Provides hardware-accelerated AI upscaling, denoising, and deblurring using
NVIDIA's Video Effects SDK (nvvfx).  Runs entirely on RTX GPU Tensor Cores
for near-real-time performance.

Requirements:
- NVIDIA RTX GPU (Turing/Ampere/Ada/Blackwell)
- Driver 570+ (Linux) / 570.65+ (Windows)
- pip install nvidia-vfx

Architecture follows the same synthesizer pattern as seedvr_synthesizer.py:
- In-process execution on GPU
- FFmpeg frame extraction / re-encoding for video
- Graceful error if nvidia-vfx is not installed
"""

import gc
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import torch

try:
    from .bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin
except ImportError:
    from core.bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin  # type: ignore
try:
    from .bin_paths import get_ffprobe_bin as _get_ffprobe_bin
except ImportError:
    from core.bin_paths import get_ffprobe_bin as _get_ffprobe_bin  # type: ignore

log = logging.getLogger("ffmpega")


# ---------------------------------------------------------------------------
#  Quality level mapping
# ---------------------------------------------------------------------------

# Lazy-loaded to avoid import error when nvidia-vfx is not installed
_QUALITY_MAP: Optional[dict] = None


def _get_quality_map() -> dict:
    """Build quality enum mapping on first use."""
    global _QUALITY_MAP
    if _QUALITY_MAP is not None:
        return _QUALITY_MAP

    try:
        from nvvfx import VideoSuperRes  # type: ignore[import-not-found]
    except ImportError:
        raise RuntimeError(
            "nvidia-vfx is not installed.  Install with: "
            "pip install nvidia-vfx"
        )

    ql = VideoSuperRes.QualityLevel
    _QUALITY_MAP = {
        # Standard upscaling
        "ULTRA": ql.ULTRA,
        "HIGH": ql.HIGH,
        "MEDIUM": ql.MEDIUM,
        "LOW": ql.LOW,
        # Same-resolution denoise
        "DENOISE_ULTRA": ql.DENOISE_ULTRA,
        "DENOISE_HIGH": ql.DENOISE_HIGH,
        "DENOISE_MEDIUM": ql.DENOISE_MEDIUM,
        "DENOISE_LOW": ql.DENOISE_LOW,
        # Same-resolution deblur
        "DEBLUR_ULTRA": ql.DEBLUR_ULTRA,
        "DEBLUR_HIGH": ql.DEBLUR_HIGH,
        "DEBLUR_MEDIUM": ql.DEBLUR_MEDIUM,
        "DEBLUR_LOW": ql.DEBLUR_LOW,
    }
    return _QUALITY_MAP


def _is_denoise_or_deblur(quality: str) -> bool:
    """Check if the quality mode is same-resolution (denoise/deblur)."""
    return quality.startswith("DENOISE_") or quality.startswith("DEBLUR_")


# ---------------------------------------------------------------------------
#  Core upscale function (operates on a single frame tensor)
# ---------------------------------------------------------------------------

def _upscale_frames(
    frames: list[torch.Tensor],
    scale: int = 4,
    quality: str = "ULTRA",
) -> list[torch.Tensor]:
    """Upscale a list of frame tensors using RTX Video Super Resolution.

    Args:
        frames: List of (H, W, 3) float32 [0,1] tensors (CPU or GPU).
        scale: Scale factor (1-4). Ignored for denoise/deblur modes.
        quality: Quality preset string (maps to VideoSuperRes.QualityLevel).

    Returns:
        List of upscaled (H', W', 3) float32 [0,1] tensors on CPU.
    """
    from nvvfx import VideoSuperRes  # type: ignore[import-not-found]

    if not frames:
        return []

    qmap = _get_quality_map()
    ql = qmap.get(quality)
    if ql is None:
        log.warning("[RTX-VSR] Unknown quality '%s', falling back to ULTRA", quality)
        ql = qmap["ULTRA"]

    h, w = frames[0].shape[:2]

    # For denoise/deblur: output = input dimensions
    if _is_denoise_or_deblur(quality):
        out_w, out_h = w, h
        log.info("[RTX-VSR] Same-resolution %s: %dx%d", quality, w, h)
    else:
        out_w = max(8, round((w * scale) / 8) * 8)
        out_h = max(8, round((h * scale) / 8) * 8)
        log.info("[RTX-VSR] Upscaling %dx%d → %dx%d (%dx, %s)",
                 w, h, out_w, out_h, scale, quality)

    results = []

    with VideoSuperRes(quality=ql) as sr:
        sr.output_width = out_w
        sr.output_height = out_h
        sr.load()

        for i, frame in enumerate(frames):
            # Convert (H, W, 3) → (3, H, W) float32 on CUDA
            frame_cuda = frame.cuda().permute(2, 0, 1).contiguous()

            # Run VSR
            dlpack_out = sr.run(frame_cuda).image
            output = torch.from_dlpack(dlpack_out).clone()

            # Convert (3, H', W') → (H', W', 3) on CPU
            output = output.permute(1, 2, 0).cpu()
            results.append(output)

            if (i + 1) % 10 == 0 or i == len(frames) - 1:
                log.info("[RTX-VSR] Processed frame %d/%d", i + 1, len(frames))

    return results


# ---------------------------------------------------------------------------
#  VRAM flush
# ---------------------------------------------------------------------------

def _flush_vram() -> None:
    """Flush GPU memory between operations."""
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
#  Public API: upscale_image
# ---------------------------------------------------------------------------

def upscale_image(
    input_path: str,
    scale: int = 4,
    quality: str = "ULTRA",
    **kwargs,
) -> str:
    """Upscale a single image using RTX Video Super Resolution.

    Args:
        input_path: Path to source image.
        scale: Scale factor (2 or 4).
        quality: Quality preset (ULTRA, HIGH, MEDIUM, LOW, DENOISE_*, DEBLUR_*).

    Returns:
        Path to the upscaled image.
    """
    import cv2

    if not os.path.isfile(input_path):
        raise RuntimeError(f"Input file not found: {input_path}")

    log.info("[RTX-VSR] Upscaling image: %s (scale=%d, quality=%s)",
             input_path, scale, quality)

    # Load image
    bgr = cv2.imread(input_path)
    if bgr is None:
        raise RuntimeError(f"Cannot read image: {input_path}")

    # BGR → RGB, normalize to [0,1] float32
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    frame = torch.from_numpy(rgb).float().div_(255.0)

    _flush_vram()

    # Upscale
    results = _upscale_frames([frame], scale=scale, quality=quality)

    _flush_vram()

    if not results:
        raise RuntimeError("RTX VSR produced no output")

    # Save output
    ext = Path(input_path).suffix or ".png"
    _fd, output_path = tempfile.mkstemp(suffix=f"_rtx_vsr{ext}", prefix="ffmpega_")
    os.close(_fd)

    out_np = (results[0].numpy() * 255.0).clip(0, 255).astype(np.uint8)
    out_bgr = cv2.cvtColor(out_np, cv2.COLOR_RGB2BGR)
    cv2.imwrite(output_path, out_bgr)

    log.info("[RTX-VSR] Image upscaled: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
#  Public API: upscale_video
# ---------------------------------------------------------------------------

def upscale_video(
    input_path: str,
    scale: int = 4,
    quality: str = "ULTRA",
    **kwargs,
) -> str:
    """Upscale a video using RTX Video Super Resolution.

    Args:
        input_path: Path to source video.
        scale: Scale factor (2 or 4).
        quality: Quality preset (ULTRA, HIGH, MEDIUM, LOW, DENOISE_*, DEBLUR_*).

    Returns:
        Path to the upscaled video.
    """
    import cv2

    if not os.path.isfile(input_path):
        raise RuntimeError(f"Input file not found: {input_path}")

    log.info("[RTX-VSR] Upscaling video: %s (scale=%d, quality=%s)",
             input_path, scale, quality)

    ffmpeg = _get_ffmpeg_bin()
    ffprobe = _get_ffprobe_bin()

    # Get FPS
    try:
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate",
             "-of", "csv=p=0", input_path],
            capture_output=True, text=True, check=True,
        )
        num, den = probe.stdout.strip().split("/")
        fps = float(num) / float(den)
    except Exception:
        fps = 24.0
        log.warning("[RTX-VSR] Could not probe FPS, defaulting to %.1f", fps)

    # Extract frames
    frames_dir = tempfile.mkdtemp(prefix="rtx_vsr_in_")
    out_dir = tempfile.mkdtemp(prefix="rtx_vsr_out_")

    try:
        subprocess.run(
            [ffmpeg, "-i", input_path, "-q:v", "2",
             "-start_number", "1",
             os.path.join(frames_dir, "%06d.png")],
            capture_output=True, check=True,
        )

        frame_files = sorted(Path(frames_dir).glob("*.png"))
        total = len(frame_files)
        if total == 0:
            raise RuntimeError(f"No frames extracted from: {input_path}")
        log.info("[RTX-VSR] Extracted %d frames at %.1f FPS", total, fps)

        # Load all frames as tensors
        frames = []
        for f in frame_files:
            bgr = cv2.imread(str(f))
            if bgr is None:
                continue
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            tensor = torch.from_numpy(rgb).float().div_(255.0)
            frames.append(tensor)

        _flush_vram()

        # Process all frames
        results = _upscale_frames(frames, scale=scale, quality=quality)
        del frames

        _flush_vram()

        # Save upscaled frames
        for i, result in enumerate(results):
            out_np = (result.numpy() * 255.0).clip(0, 255).astype(np.uint8)
            out_bgr = cv2.cvtColor(out_np, cv2.COLOR_RGB2BGR)
            path = os.path.join(out_dir, f"{i + 1:06d}.png")
            cv2.imwrite(path, out_bgr)
        del results

        # Encode video from upscaled frames
        _fd, output_path = tempfile.mkstemp(
            suffix="_rtx_vsr.mp4", prefix="ffmpega_"
        )
        os.close(_fd)

        fps_str = str(int(round(fps))) if round(fps, 2) == int(round(fps)) else f"{fps:.2f}"
        encode_cmd = [
            ffmpeg, "-y",
            "-framerate", fps_str,
            "-start_number", "1",
            "-i", os.path.join(out_dir, "%06d.png"),
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        result = subprocess.run(encode_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg encoding failed: {result.stderr[:500]}")

        # Mux audio from original input
        try:
            probe = subprocess.run(
                [ffprobe, "-v", "quiet", "-select_streams", "a:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                 input_path],
                capture_output=True, text=True, timeout=10,
            )
            has_audio = probe.returncode == 0 and "audio" in probe.stdout
        except Exception:
            has_audio = False

        if has_audio:
            muxed_path = str(Path(output_path).with_suffix(".muxed.mp4"))
            mux_result = subprocess.run(
                [ffmpeg, "-y",
                 "-i", output_path, "-i", input_path,
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                 "-map", "0:v:0", "-map", "1:a:0",
                 "-shortest",
                 muxed_path],
                capture_output=True, text=True,
            )
            if mux_result.returncode == 0:
                os.replace(muxed_path, output_path)
                log.info("[RTX-VSR] Audio muxed from original")
            else:
                # Clean up failed mux attempt
                if os.path.exists(muxed_path):
                    os.remove(muxed_path)
                log.warning("[RTX-VSR] Audio mux failed, video-only output")

        log.info("[RTX-VSR] Video upscaled: %s (%d frames)", output_path, total)
        return output_path

    finally:
        # Cleanup temp frame directories
        import shutil
        shutil.rmtree(frames_dir, ignore_errors=True)
        shutil.rmtree(out_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
#  Cleanup
# ---------------------------------------------------------------------------

def cleanup() -> None:
    """Release GPU resources."""
    _flush_vram()
    log.info("[RTX-VSR] Cleanup complete")
