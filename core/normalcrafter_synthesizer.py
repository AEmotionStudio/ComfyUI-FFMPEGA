# coding: utf-8
"""NormalCrafter — temporally consistent video normal map generation.

Produces surface normal map videos from arbitrary input videos using
video diffusion priors (SVD-based architecture).  The normals are
temporally consistent across frames without post-hoc smoothing.

Architecture follows the LivePortrait/MMAudio/Marigold synthesizer pattern:
- In-process execution with GPU↔CPU pipeline offloading
- Cached pipeline state with explicit load/cleanup
- ``comfy.model_management`` VRAM coordination

Based on: https://github.com/Binyr/NormalCrafter  (MIT license)

The upstream repo uses ``decord`` + ``mediapy`` for I/O; we replace
both with ``cv2`` + ``ffmpeg`` to avoid extra dependencies and match
the Marigold synthesizer pattern.
"""

import gc
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
from PIL import Image

try:
    from .bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin
except ImportError:
    from core.bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin  # type: ignore

log = logging.getLogger("ffmpega")


# ---------------------------------------------------------------------------
#  HuggingFace checkpoint mapping
# ---------------------------------------------------------------------------

_REPOS = {
    "unet": {
        "mirror_repo": "AEmotionStudio/NormalCrafter",
        "upstream_repo": "Yanrui95/NormalCrafter",
    },
    "base_svd": {
        "mirror_repo": "AEmotionStudio/stable-video-diffusion-img2vid-xt",
        "upstream_repo": "stabilityai/stable-video-diffusion-img2vid-xt",
    },
}

# ---------------------------------------------------------------------------
#  Cached pipeline state
# ---------------------------------------------------------------------------

_pipe: Optional[object] = None


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Free GPU VRAM before loading NormalCrafter pipeline."""
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="normalcrafter_synthesizer")


def _get_device() -> torch.device:
    """Get the best available device via ComfyUI model management."""
    try:
        import comfy.model_management as mm
        return mm.get_torch_device()
    except (ImportError, AttributeError):
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")


def _auto_tune_params(
    decode_chunk_size: int = 7,
) -> tuple[int, int]:
    """Detect GPU VRAM and return safe *(max_res, decode_chunk_size)* limits.

    Called when the user selects ``max_res="auto"``.  Returns conservative
    defaults so that VAE encoding doesn't OOM after pipeline weights are
    loaded.

    Returns:
        (max_res, decode_chunk_size) tuned for the detected GPU.
    """
    if not torch.cuda.is_available():
        return 768, min(decode_chunk_size, 4)

    try:
        total_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    except Exception:
        return 768, min(decode_chunk_size, 4)

    if total_gb <= 8:
        res, chunk = 512, min(decode_chunk_size, 2)
    elif total_gb <= 12:
        res, chunk = 768, min(decode_chunk_size, 4)
    else:
        res, chunk = 1024, decode_chunk_size

    log.info(
        "[NormalCrafter] Auto-tuned for %.1f GiB GPU: "
        "max_res=%d, decode_chunk_size=%d",
        total_gb, res, chunk,
    )
    return res, chunk


# ---------------------------------------------------------------------------
#  Pipeline loading
# ---------------------------------------------------------------------------

def _load_pipeline():
    """Load (or reuse cached) NormalCrafter pipeline.

    The pipeline comprises:
    - A custom UNet from the NormalCrafter checkpoint
    - A temporal VAE decoder from SVD
    - The full SVD pipeline base (scheduler, image encoder, etc.)

    Uses ``enable_model_cpu_offload()`` for memory efficiency.

    Returns:
        The loaded NormalCrafterPipeline instance.
    """
    global _pipe

    if _pipe is not None:
        log.info("[NormalCrafter] Reusing cached pipeline")
        return _pipe

    log.info("[NormalCrafter] Loading pipeline...")

    # Free VRAM from other models
    _free_vram()

    # Check download permission
    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed
    require_downloads_allowed("normalcrafter")

    # Import NormalCrafter components
    try:
        from normalcrafter.normal_crafter_ppl import NormalCrafterPipeline
        from normalcrafter.unet import (
            DiffusersUNetSpatioTemporalConditionModelNormalCrafter,
        )
    except ImportError as exc:
        raise RuntimeError(
            "NormalCrafter package is not installed. Install with: "
            "pip install --no-deps git+https://github.com/Binyr/NormalCrafter.git"
        ) from exc

    from diffusers import AutoencoderKLTemporalDecoder

    # Try mirror first, then upstream for UNet
    unet_repo = None
    for key in ("mirror_repo", "upstream_repo"):
        repo = _REPOS["unet"][key]
        try:
            log.info("[NormalCrafter] Trying UNet repo: %s", repo)
            unet = DiffusersUNetSpatioTemporalConditionModelNormalCrafter.from_pretrained(
                repo,
                subfolder="unet",
                low_cpu_mem_usage=True,
            )
            vae = AutoencoderKLTemporalDecoder.from_pretrained(
                repo,
                subfolder="vae",
            )
            unet_repo = repo
            log.info("[NormalCrafter] UNet + VAE loaded from %s", repo)
            break
        except Exception as exc:
            log.debug("[NormalCrafter] Repo %s failed: %s", repo, exc)
            continue

    if unet_repo is None:
        raise RuntimeError(
            "Failed to load NormalCrafter UNet from both "
            f"{_REPOS['unet']['mirror_repo']} and "
            f"{_REPOS['unet']['upstream_repo']}. "
            "Check your internet connection or install manually."
        )

    # Cast to fp16
    weight_dtype = torch.float16
    vae.to(dtype=weight_dtype)
    unet.to(dtype=weight_dtype)

    # Load the full pipeline from SVD base (mirror → upstream)
    pipe = None
    for key in ("mirror_repo", "upstream_repo"):
        repo = _REPOS["base_svd"][key]
        try:
            log.info("[NormalCrafter] Trying SVD base repo: %s", repo)
            pipe = NormalCrafterPipeline.from_pretrained(
                repo,
                unet=unet,
                vae=vae,
                torch_dtype=weight_dtype,
                variant="fp16",
            )
            log.info("[NormalCrafter] Pipeline loaded from %s", repo)
            break
        except Exception as exc:
            log.debug("[NormalCrafter] SVD base %s failed: %s", repo, exc)
            continue

    if pipe is None:
        raise RuntimeError(
            "Failed to load SVD base pipeline from both "
            f"{_REPOS['base_svd']['mirror_repo']} and "
            f"{_REPOS['base_svd']['upstream_repo']}."
        )

    # Sequential offload moves individual *layers* to GPU one at a time,
    # keeping peak VRAM at ~2-3 GB instead of ~8+ GB.
    pipe.enable_sequential_cpu_offload()

    # Try xformers for attention optimization
    try:
        pipe.enable_xformers_memory_efficient_attention()
        log.info("[NormalCrafter] xformers enabled")
    except Exception:
        log.debug("[NormalCrafter] xformers not available, using default attention")

    _pipe = pipe
    log.info("[NormalCrafter] Pipeline loaded successfully")
    return pipe


def cleanup() -> None:
    """Free GPU memory and clear cached NormalCrafter pipeline."""
    global _pipe

    if _pipe is None:
        return

    pipe = _pipe
    _pipe = None

    try:
        pipe.to("cpu")
    except Exception:
        pass
    del pipe

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass

    log.info("[NormalCrafter] Pipeline unloaded")


# ---------------------------------------------------------------------------
#  Video I/O helpers
# ---------------------------------------------------------------------------

def _read_video_frames(
    video_path: str,
    max_res: int = 1024,
    process_length: int = -1,
    target_fps: int = -1,
) -> tuple[list, float]:
    """Read video frames as PIL Images.

    Args:
        video_path: Path to input video.
        max_res: Maximum resolution (longest side).
        process_length: Maximum number of frames (-1 = all).
        target_fps: Target FPS (-1 = use original).

    Returns:
        (frames, fps) — list of PIL Images and the effective FPS.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    orig_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Compute effective FPS and stride
    fps = orig_fps if target_fps <= 0 else target_fps
    stride = max(1, round(orig_fps / fps))

    # Compute resolution scaling
    if max(orig_w, orig_h) > max_res:
        scale = max_res / max(orig_w, orig_h)
        new_w = round(orig_w * scale)
        new_h = round(orig_h * scale)
    else:
        new_w = orig_w
        new_h = orig_h

    frames = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % stride == 0:
            if new_w != orig_w or new_h != orig_h:
                frame = cv2.resize(
                    frame, (new_w, new_h), interpolation=cv2.INTER_AREA,
                )
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb))

            if process_length > 0 and len(frames) >= process_length:
                break

        frame_idx += 1

    cap.release()

    log.info(
        "[NormalCrafter] Read %d frames at %.1f fps (%dx%d)",
        len(frames), fps, new_w, new_h,
    )
    return frames, fps


def _save_normal_video(
    normals: np.ndarray,
    output_path: str,
    fps: float,
) -> None:
    """Save normal map array as an MP4 video using ffmpeg.

    Args:
        normals: Normal map array in range [-1, 1], shape (T, H, W, 3).
        output_path: Path for the output video.
        fps: Frame rate.
    """
    # Visualize: map [-1, 1] → [0, 1] → [0, 255]
    vis = np.clip(normals * 0.5 + 0.5, 0, 1)
    vis = (vis * 255).astype(np.uint8)

    tmp_dir = tempfile.mkdtemp(prefix="normalcrafter_")
    try:
        for i, frame in enumerate(vis):
            cv2.imwrite(
                os.path.join(tmp_dir, f"{i:06d}.png"),
                cv2.cvtColor(frame, cv2.COLOR_RGB2BGR),
            )

        fps_str = (
            str(int(round(fps)))
            if round(fps, 2) == int(round(fps))
            else f"{fps:.2f}"
        )
        cmd = [
            _get_ffmpeg_bin(), "-y",
            "-framerate", fps_str,
            "-i", os.path.join(tmp_dir, "%06d.png"),
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def run_normalcrafter(
    video_path: str,
    max_res: "int | str" = "auto",
    window_size: int = 14,
    process_length: int = -1,
    target_fps: int = -1,
    seed: int = 42,
    decode_chunk_size: int = 7,
    time_step_size: int = 10,
) -> str:
    """Run NormalCrafter on a video to produce temporally consistent normals.

    Args:
        video_path: Path to input video.
        max_res: Maximum processing resolution.  Pass ``"auto"`` to let
            the synthesizer pick a safe value based on GPU VRAM, or an
            integer (512, 768, 1024) to use a specific resolution.
        window_size: Temporal window size for sliding inference.
        process_length: Max frames to process (-1 = all).
        target_fps: Target FPS for processing (-1 = original).
        seed: Random seed for reproducibility.
        decode_chunk_size: VAE decode chunk size (lower = less VRAM).
        time_step_size: Temporal step between windows.

    Returns:
        Path to the output normal map video.

    Raises:
        RuntimeError: If video cannot be read or inference fails.
    """
    if not os.path.isfile(video_path):
        raise RuntimeError(f"Input video not found: {video_path}")

    # Resolve max_res: "auto" → GPU detection, string number → int
    if isinstance(max_res, str):
        if max_res == "auto":
            max_res, decode_chunk_size = _auto_tune_params(decode_chunk_size)
        else:
            max_res = int(max_res)

    # Clamp parameters
    max_res = max(256, min(1024, max_res))
    window_size = max(2, min(60, window_size))
    decode_chunk_size = max(1, min(14, decode_chunk_size))
    time_step_size = max(1, min(window_size, time_step_size))

    pipe = _load_pipeline()

    # Clear caches after pipeline load to maximise free VRAM for inference
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Read frames
    frames, fps = _read_video_frames(
        video_path,
        max_res=max_res,
        process_length=process_length,
        target_fps=target_fps,
    )
    if not frames:
        raise RuntimeError(f"No frames extracted from video: {video_path}")

    log.info(
        "[NormalCrafter] Running inference: %d frames, window=%d, "
        "time_step=%d, max_res=%d",
        len(frames), window_size, time_step_size, max_res,
    )

    # Set seed
    from diffusers.training_utils import set_seed
    set_seed(seed)

    try:
        # Run pipeline
        with torch.inference_mode():
            result = pipe(
                frames,
                decode_chunk_size=decode_chunk_size,
                time_step_size=time_step_size,
                window_size=window_size,
            ).frames[0]  # shape: (T, H, W, 3), range [-1, 1]

        # Save output
        _fd, output_path = tempfile.mkstemp(suffix="_normalcrafter.mp4")
        os.close(_fd)
        _save_normal_video(result, output_path, fps)

        log.info(
            "[NormalCrafter] Output saved to %s (%d frames)",
            output_path, len(result),
        )
        return output_path
    finally:
        cleanup()


def run_normalcrafter_frames(
    video_path: str,
    max_res: "int | str" = "auto",
    window_size: int = 14,
    process_length: int = -1,
    target_fps: int = -1,
    seed: int = 42,
    decode_chunk_size: int = 7,
    time_step_size: int = 10,
) -> tuple[np.ndarray, float]:
    """Run NormalCrafter and return raw normal arrays instead of a video.

    Used by the relight pipeline which needs per-frame normal data.

    Returns:
        (normals, fps) — normals array shape (T, H, W, 3) range [-1, 1],
        and the effective FPS.
    """
    if not os.path.isfile(video_path):
        raise RuntimeError(f"Input video not found: {video_path}")

    # Resolve max_res: "auto" → GPU detection, string number → int
    if isinstance(max_res, str):
        if max_res == "auto":
            max_res, decode_chunk_size = _auto_tune_params(decode_chunk_size)
        else:
            max_res = int(max_res)

    max_res = max(256, min(1024, max_res))
    window_size = max(2, min(60, window_size))
    decode_chunk_size = max(1, min(14, decode_chunk_size))
    time_step_size = max(1, min(window_size, time_step_size))

    pipe = _load_pipeline()

    # Clear caches after pipeline load to maximise free VRAM for inference
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    frames, fps = _read_video_frames(
        video_path,
        max_res=max_res,
        process_length=process_length,
        target_fps=target_fps,
    )
    if not frames:
        raise RuntimeError(f"No frames extracted from video: {video_path}")

    log.info(
        "[NormalCrafter] Running inference for relight: %d frames",
        len(frames),
    )

    from diffusers.training_utils import set_seed
    set_seed(seed)

    try:
        with torch.inference_mode():
            result = pipe(
                frames,
                decode_chunk_size=decode_chunk_size,
                time_step_size=time_step_size,
                window_size=window_size,
            ).frames[0]

        return result, fps
    finally:
        cleanup()
