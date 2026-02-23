"""LaMa Inpainter — per-frame video object removal using LaMa.

Uses the ``simple-lama-inpainting`` package (Apache-2.0) which wraps the
LaMa (Large Mask Inpainting) model.  The model auto-downloads (~200 MB)
on first use.

This is the **public-facing** remover shipped with FFMPEGA.  For higher
quality, a local-only MiniMax-Remover integration is available via
``core/minimax_remover.py`` (not shipped in the public repo).

License: Apache-2.0 (same as upstream LaMa)
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import torch

log = logging.getLogger("ffmpega")

# Cached model instance
_lama_model = None


# ---------------------------------------------------------------------------
#  Model loading
# ---------------------------------------------------------------------------

def load_model():
    """Load and cache the SimpleLama model.

    Auto-downloads the ~200MB checkpoint on first use.

    Returns:
        SimpleLama instance.

    Raises:
        ImportError: If simple-lama-inpainting is not installed.
    """
    global _lama_model

    if _lama_model is not None:
        return _lama_model

    try:
        from simple_lama_inpainting import SimpleLama
    except ImportError:
        raise ImportError(
            "simple-lama-inpainting is required for AI object removal. "
            "Install with: pip install simple-lama-inpainting"
        )

    _free_vram()

    # Disable TensorFloat-32 and bfloat16 matmul to prevent
    # "Unsupported dtype BFloat16" in LaMa's FFT ops.
    # This must be set BEFORE loading the JIT model.
    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        if hasattr(torch.backends.cuda.matmul, "allow_bf16_reduced_precision_reduction"):
            torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction = False

    log.info("Loading LaMa inpainting model...")
    _lama_model = SimpleLama()

    # Force float32 on the JIT model parameters
    if hasattr(_lama_model, "model"):
        _lama_model.model = _lama_model.model.float()

    log.info("LaMa model loaded successfully")
    return _lama_model


def cleanup() -> None:
    """Free GPU memory and clear cached model."""
    global _lama_model
    _lama_model = None
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    log.info("LaMa model unloaded")


def _free_vram():
    """Free ComfyUI and SAM3 VRAM before loading LaMa."""
    try:
        import comfy.model_management
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()
    except Exception:
        pass

    # Also free SAM3 if loaded
    try:
        from . import sam3_masker
        sam3_masker.cleanup()
    except Exception:
        pass

    if torch.cuda.is_available():
        torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
#  Frame I/O helpers
# ---------------------------------------------------------------------------

def _load_video_frames(video_path: str) -> Tuple[list, float]:
    """Load video frames as PIL Images.

    Returns:
        (frames_pil, fps) where frames_pil is a list of PIL.Image.Image
    """
    from PIL import Image

    tmpdir = tempfile.mkdtemp(prefix="lama_frames_")
    subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-q:v", "2",
            os.path.join(tmpdir, "%06d.png"),
        ],
        capture_output=True,
        check=True,
    )

    frame_files = sorted(Path(tmpdir).glob("*.png"))
    frames = [Image.open(f).convert("RGB") for f in frame_files]

    # Get FPS
    probe = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "csv=p=0",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    fps_str = probe.stdout.strip()
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_str) if fps_str else 30.0

    return frames, fps, tmpdir


def _load_mask_frames(mask_video_path: str, num_frames: int) -> list:
    """Load mask frames as PIL Images (mode 'L').

    Returns:
        List of PIL.Image.Image in mode 'L' (grayscale).
    """
    from PIL import Image

    tmpdir = tempfile.mkdtemp(prefix="lama_masks_")
    subprocess.run(
        [
            "ffmpeg", "-i", mask_video_path,
            "-q:v", "2",
            os.path.join(tmpdir, "%06d.png"),
        ],
        capture_output=True,
        check=True,
    )

    mask_files = sorted(Path(tmpdir).glob("*.png"))
    masks = []
    for f in mask_files[:num_frames]:
        img = Image.open(f).convert("L")
        masks.append(img)

    # Pad if fewer masks than frames
    if masks:
        while len(masks) < num_frames:
            masks.append(Image.new("L", masks[0].size, 0))

    return masks, tmpdir


def _encode_video(
    frames: list,
    output_path: str,
    fps: float,
) -> str:
    """Encode PIL frames to a video file.

    Args:
        frames: list of PIL.Image.Image
        output_path: output video file path
        fps: frame rate

    Returns:
        Path to the encoded video.
    """
    tmpdir = tempfile.mkdtemp(prefix="lama_out_")
    for i, frame in enumerate(frames):
        frame.save(os.path.join(tmpdir, f"{i:06d}.png"))

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", os.path.join(tmpdir, "%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            output_path,
        ],
        capture_output=True,
        check=True,
    )

    # Clean up intermediate PNG frames
    import shutil
    try:
        shutil.rmtree(tmpdir)
    except OSError:
        pass

    return output_path


# ---------------------------------------------------------------------------
#  Temporal smoothing
# ---------------------------------------------------------------------------

def _temporal_smooth(
    frames: list[np.ndarray],
    masks: list[np.ndarray],
    window: int = 5,
) -> list[np.ndarray]:
    """Apply temporal Gaussian smoothing to inpainted regions only.

    This reduces per-frame flickering by blending neighboring inpainted
    results in the masked area. Original pixels are untouched.

    Args:
        frames: list of (H, W, 3) uint8 inpainted frames
        masks: list of (H, W) float32 masks [0, 1]
        window: smoothing window size (odd number)

    Returns:
        Temporally smoothed frames.
    """
    from scipy.ndimage import gaussian_filter1d

    n = len(frames)
    if n <= 1:
        return frames

    # Stack into arrays for efficient processing
    stack = np.stack(frames).astype(np.float32)  # (N, H, W, 3)
    mask_stack = np.stack(masks)  # (N, H, W)

    # Only smooth where mask > threshold
    sigma = window / 3.0

    # Apply temporal Gaussian along axis=0 (frame dimension)
    smoothed = gaussian_filter1d(stack, sigma=sigma, axis=0)

    # Blend: use smoothed only in masked regions
    result = []
    for i in range(n):
        m = mask_stack[i][:, :, None]  # (H, W, 1)
        blended = stack[i] * (1 - m) + smoothed[i] * m
        result.append(np.clip(blended, 0, 255).astype(np.uint8))

    return result


# ---------------------------------------------------------------------------
#  Core inpainting
# ---------------------------------------------------------------------------

def _inpaint_frame(model, image, mask):
    """Inpaint a single frame using LaMa.

    Args:
        model: SimpleLama instance
        image: PIL.Image.Image (RGB)
        mask: PIL.Image.Image (L, where 255 = inpaint)

    Returns:
        PIL.Image.Image — inpainted result
    """
    # Ensure float32 precision — LaMa's FFT ops crash on bfloat16
    with torch.cuda.amp.autocast(enabled=False):
        return model(image, mask)


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def remove_object(
    video_path: str,
    mask_video_path: str,
    output_path: Optional[str] = None,
) -> str:
    """Remove an object from a video using LaMa per-frame inpainting.

    This is the main entry point called by the auto_mask handler when
    effect="remove" and MiniMax-Remover is not available.

    Args:
        video_path: path to the original video
        mask_video_path: path to the mask video (white = object to remove)
        output_path: output path (auto-generated if None)

    Returns:
        Path to the inpainted video.
    """
    from PIL import Image

    if output_path is None:
        tmpdir = tempfile.mkdtemp(prefix="lama_result_")
        output_path = os.path.join(tmpdir, "inpainted.mp4")

    # Load frames
    log.info("Loading video frames from %s", video_path)
    frames, fps, frames_tmpdir = _load_video_frames(video_path)
    total_frames = len(frames)
    log.info(
        "Loaded %d frames at %.1f FPS (%dx%d)",
        total_frames, fps, frames[0].width, frames[0].height,
    )

    # Load masks
    log.info("Loading mask frames from %s", mask_video_path)
    masks, masks_tmpdir = _load_mask_frames(mask_video_path, total_frames)

    # Load model
    model = load_model()

    # Per-frame inpainting
    log.info("Running LaMa inpainting on %d frames...", total_frames)
    inpainted_frames = []
    for i in range(total_frames):
        if i % 20 == 0:
            log.info("  Frame %d/%d", i + 1, total_frames)

        # Check if mask has any content (skip blank masks)
        mask_arr = np.array(masks[i])
        if mask_arr.max() < 10:
            # No mask content — keep original frame
            inpainted_frames.append(frames[i])
            continue

        result = _inpaint_frame(model, frames[i], masks[i])
        inpainted_frames.append(result)

    # Composite: use inpainted pixels only where mask > 0
    log.info("Compositing inpainted regions onto original frames...")
    composited = []
    composited_np = []
    mask_np_list = []

    for i in range(total_frames):
        orig_arr = np.array(frames[i]).astype(np.float32)
        inp_arr = np.array(inpainted_frames[i]).astype(np.float32)
        mask_arr = np.array(masks[i]).astype(np.float32) / 255.0

        mask_np_list.append(mask_arr)

        # Composite
        mask_3ch = mask_arr[:, :, None]
        result = orig_arr * (1 - mask_3ch) + inp_arr * mask_3ch
        composited_np.append(result.astype(np.uint8))

    # Temporal smoothing to reduce flicker
    log.info("Applying temporal smoothing...")
    smoothed = _temporal_smooth(composited_np, mask_np_list, window=5)

    # Convert back to PIL
    for arr in smoothed:
        composited.append(Image.fromarray(arr))

    # Encode result
    log.info("Encoding inpainted video to %s", output_path)
    _encode_video(composited, output_path, fps)

    # Clean up intermediate temp directories
    import shutil
    for d in (frames_tmpdir, masks_tmpdir):
        try:
            shutil.rmtree(d)
        except OSError:
            pass

    # Free VRAM
    cleanup()

    log.info("LaMa object removal complete: %s", output_path)
    return output_path
