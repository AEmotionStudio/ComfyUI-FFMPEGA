"""MiniMax-Remover — video object removal using MiniMax inpainting.

Uses the vendored MiniMax-Remover pipeline (code: Apache 2.0, model weights: CC-BY-NC-4.0) for high-quality
video object removal.  The model processes 81-frame batches with
6–12 inference steps using a simplified DiT architecture.

Architecture
~~~~~~~~~~~~
- core/minimax/transformer_minimax_remover.py — Transformer3DModel
- core/minimax/pipeline_minimax_remover.py   — Minimax_Remover_Pipeline
- This file                                   — download, load, run, cleanup

Slot in the removal tier hierarchy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. MiniMax-Remover  (this, ~5–8 GB VRAM, toggle ``use_minimax_remover``)
2. FLUX Klein       (~8–15 GB VRAM, toggle ``use_flux_klein``)
3. LaMa             (~200 MB VRAM, always available)
4. Black fill       (0 VRAM, FFmpeg fallback)

Paper: "MiniMax-Remover: Taming Bad Noise Helps Video Object Removal"
Upstream: https://github.com/zibojia/MiniMax-Remover
"""

from __future__ import annotations

import gc
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger("ffmpega")


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

_HF_REPO = "zibojia/minimax-remover"
_MIRROR_REPO = "AEmotionStudio/minimax-remover"
_MODEL_DIR_NAME = "minimax_remover"

# Default inference settings
_NUM_INFERENCE_STEPS = 12
_NUM_ITERATIONS = 6        # mask dilation iterations
_BATCH_SIZE = 81           # max frames per batch (model native)
_BATCH_OVERLAP = 8         # overlap frames for temporal consistency
_DEFAULT_HEIGHT = 480
_DEFAULT_WIDTH = 832
_RANDOM_SEED = 42

# Cached pipeline
_pipeline = None

# License logging (once per session, matching MMAudio's pattern)
_license_logged = False


def _log_license_notice():
    """Log the CC-BY-NC license notice (once per session)."""
    global _license_logged
    if _license_logged:
        return
    _license_logged = True
    log.info(
        "⚠️  MiniMax-Remover model weights are licensed CC-BY-NC 4.0 (non-commercial). "
        "By using these models you agree to: https://creativecommons.org/licenses/by-nc/4.0/"
    )


# ---------------------------------------------------------------------------
#  Path validation helpers (reuse from flux_klein_editor)
# ---------------------------------------------------------------------------

try:
    from .sanitize import validate_video_path, validate_output_file_path
except ImportError:
    try:
        from core.sanitize import validate_video_path, validate_output_file_path
    except ImportError:
        def validate_video_path(p):
            return p
        def validate_output_file_path(p):
            return p


# ---------------------------------------------------------------------------
#  Model directory and downloading
# ---------------------------------------------------------------------------

def _get_model_dir() -> Path:
    """Get or create the MiniMax-Remover model directory.

    Checks (in order):
    1. FFMPEGA_MINIMAX_MODEL_DIR env var
    2. ComfyUI/models/minimax_remover/ (standard ComfyUI convention)
    3. Extension's own models/minimax_remover/ (fallback)
    """
    env_dir = os.environ.get("FFMPEGA_MINIMAX_MODEL_DIR")
    if env_dir:
        return Path(env_dir)

    # ComfyUI/models/minimax_remover/
    try:
        import folder_paths  # type: ignore[import-not-found]
        comfy_models = Path(folder_paths.models_dir)
        model_dir = comfy_models / _MODEL_DIR_NAME
        model_dir.mkdir(parents=True, exist_ok=True)
        return model_dir
    except (ImportError, AttributeError):
        pass

    # Extension's own models/
    ext_dir = Path(__file__).resolve().parent.parent / "models" / _MODEL_DIR_NAME
    ext_dir.mkdir(parents=True, exist_ok=True)
    return ext_dir


def _download_model(model_dir: Path) -> None:
    """Download model weights from HuggingFace if not present.

    Tries the AEmotionStudio mirror first, then falls back to the
    official repo.
    """
    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed  # type: ignore
    require_downloads_allowed("minimax_remover")

    # Check if components already exist
    vae_dir = model_dir / "vae"
    transformer_dir = model_dir / "transformer"
    scheduler_dir = model_dir / "scheduler"

    if (vae_dir.is_dir() and transformer_dir.is_dir() and scheduler_dir.is_dir()):
        log.info("MiniMax-Remover model already downloaded: %s", model_dir)
        return

    try:
        from .model_manager import log_download_start, log_download_complete
    except ImportError:
        from core.model_manager import log_download_start, log_download_complete  # type: ignore

    log_download_start("minimax_remover")

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise ImportError(
            "huggingface_hub is required to download MiniMax-Remover. "
            "Install with: pip install huggingface_hub"
        )

    # Try mirror first, then official
    for repo_id in [_MIRROR_REPO, _HF_REPO]:
        try:
            log.info("Downloading MiniMax-Remover from %s...", repo_id)
            snapshot_download(
                repo_id=repo_id,
                local_dir=str(model_dir),
                allow_patterns=["vae/*", "transformer/*", "scheduler/*"],
            )
            log_download_complete("minimax_remover", str(model_dir))
            _log_license_notice()
            return
        except Exception as e:
            log.warning("Download from %s failed: %s", repo_id, e)
            continue

    raise RuntimeError(
        f"Failed to download MiniMax-Remover from both {_MIRROR_REPO} "
        f"and {_HF_REPO}. Check your internet connection or download "
        f"manually: huggingface-cli download {_HF_REPO} "
        f"--include vae transformer scheduler --local-dir {model_dir}"
    )


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Aggressively free all GPU VRAM before loading MiniMax-Remover.

    Delegates to the shared ``_vram_utils.free_for_module``.
    """
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="minimax_remover")


# ---------------------------------------------------------------------------
#  Pipeline loading
# ---------------------------------------------------------------------------

def load_pipeline():
    """Load and cache the MiniMax-Remover pipeline.

    Returns:
        Minimax_Remover_Pipeline instance ready for inference.

    Raises:
        ImportError: If diffusers or dependencies are not installed.
        RuntimeError: If model download fails.
    """
    global _pipeline

    if _pipeline is not None:
        return _pipeline

    import torch

    # Free VRAM first
    _free_vram()

    # Get and ensure model directory
    model_dir = _get_model_dir()
    _download_model(model_dir)

    log.info("Loading MiniMax-Remover pipeline from %s", model_dir)
    _log_license_notice()

    # Import vendored pipeline components
    try:
        from .minimax.pipeline_minimax_remover import Minimax_Remover_Pipeline
        from .minimax.transformer_minimax_remover import Transformer3DModel
    except ImportError:
        from core.minimax.pipeline_minimax_remover import Minimax_Remover_Pipeline  # type: ignore
        from core.minimax.transformer_minimax_remover import Transformer3DModel  # type: ignore

    from diffusers.models import AutoencoderKLWan
    from diffusers.schedulers import UniPCMultistepScheduler

    vae_dir = model_dir / "vae"
    transformer_dir = model_dir / "transformer"
    scheduler_dir = model_dir / "scheduler"

    log.info("Loading VAE from %s", vae_dir)
    vae = AutoencoderKLWan.from_pretrained(
        str(vae_dir), torch_dtype=torch.float16
    )

    log.info("Loading Transformer from %s", transformer_dir)
    transformer = Transformer3DModel.from_pretrained(
        str(transformer_dir), torch_dtype=torch.float16
    )

    log.info("Loading Scheduler from %s", scheduler_dir)
    scheduler = UniPCMultistepScheduler.from_pretrained(str(scheduler_dir))

    pipe = Minimax_Remover_Pipeline(
        vae=vae,
        transformer=transformer,
        scheduler=scheduler,
    )

    # Use CPU offloading — keeps parameters on CPU and moves to GPU
    # layer-by-layer during forward pass.  The pipeline already declares
    # model_cpu_offload_seq = "transformer->vae" so diffusers handles
    # the sequencing.  This is critical for ≤12 GB GPUs.
    if torch.cuda.is_available():
        try:
            pipe.enable_model_cpu_offload()
            log.info("MiniMax-Remover pipeline loaded with CPU offloading")
        except (AttributeError, NotImplementedError):
            # Fallback for older diffusers without offloading support
            pipe = pipe.to("cuda")
            log.info("MiniMax-Remover pipeline loaded on GPU (no offloading)")
    else:
        log.warning("MiniMax-Remover: no CUDA — running on CPU (very slow)")

    _pipeline = pipe
    return _pipeline


def cleanup() -> None:
    """Free GPU memory and clear cached pipeline.

    Follows the same cleanup pattern as other FFMPEGA core modules.
    """
    global _pipeline
    if _pipeline is not None:
        try:
            import torch
            pipe = _pipeline
            _pipeline = None
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
            log.info("MiniMax-Remover pipeline freed")
        except Exception as e:
            _pipeline = None
            log.warning("MiniMax-Remover cleanup error: %s", e)


# ---------------------------------------------------------------------------
#  Frame I/O helpers (consistent with flux_klein_editor / lama_inpainter)
# ---------------------------------------------------------------------------

def _load_video_frames(video_path: str):
    """Load video frames as PIL Images.

    Returns:
        (frames_pil, fps)
    """
    from PIL import Image
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frames = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        frames.append(pil)

    cap.release()
    log.info("Loaded %d frames from %s (%.1f fps)", len(frames), video_path, fps)
    return frames, fps


def _load_mask_frames(mask_video_path: str, num_frames: int,
                      frame_size: tuple[int, int] | None = None):
    """Load mask frames as PIL Images (mode 'L').

    Args:
        mask_video_path: path to the mask video.
        num_frames: expected number of frames (will pad/truncate).
        frame_size: (width, height) of the video frames.  Used only as
                    a fallback when the mask video has zero frames.

    Returns:
        list of PIL Images in mode 'L'.
    """
    from PIL import Image
    import cv2

    cap = cv2.VideoCapture(mask_video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open mask video: {mask_video_path}")

    masks = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        masks.append(Image.fromarray(gray))

    cap.release()

    # Pad or truncate to match video frame count
    if len(masks) < num_frames:
        if masks:
            last = masks[-1]
        else:
            # No mask frames — create a blank mask at the video's resolution
            fallback_size = frame_size or (640, 480)
            last = Image.new("L", fallback_size, 0)
        masks.extend([last.copy() for _ in range(num_frames - len(masks))])
    elif len(masks) > num_frames:
        masks = masks[:num_frames]

    log.info("Loaded %d mask frames from %s", len(masks), mask_video_path)
    return masks


def _encode_video(frames: list, output_path: str, fps: float) -> str:
    """Encode PIL frames to a video file.

    Writes frames as PNGs to a temp directory and encodes once with
    ffmpeg (libx264).  This avoids the previous two-pass approach
    (cv2.VideoWriter mp4v → ffmpeg re-encode) which wasted encoding time.

    Args:
        frames: list of PIL.Image.Image
        output_path: output video file path
        fps: frame rate

    Returns:
        Path to the encoded video.
    """
    if not frames:
        raise ValueError("No frames to encode")

    try:
        from .bin_paths import get_ffmpeg_bin
    except ImportError:
        from core.bin_paths import get_ffmpeg_bin  # type: ignore
    ffmpeg = get_ffmpeg_bin()

    frames_dir = tempfile.mkdtemp(prefix="ffmpega_minimax_enc_")
    try:
        for i, frame in enumerate(frames):
            frame.save(os.path.join(frames_dir, f"{i:06d}.png"))

        # Use integer framerate for ffmpeg compatibility
        fps_str = str(int(round(fps))) if round(fps, 2) == int(round(fps)) else f"{fps:.2f}"
        cmd = [
            ffmpeg, "-y",
            "-framerate", fps_str,
            "-i", os.path.join(frames_dir, "%06d.png"),
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "medium",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(
                "[MiniMax] ffmpeg encode failed (exit %d): %s",
                result.returncode, result.stderr[:500] if result.stderr else "",
            )
            raise RuntimeError(
                f"ffmpeg video encoding failed (exit {result.returncode})"
            )
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)

    return output_path


# ---------------------------------------------------------------------------
#  Temporal smoothing (reused from flux_klein_editor pattern)
# ---------------------------------------------------------------------------

def _temporal_smooth(
    frames: list,
    masks: list,
    window: int = 5,
):
    """Apply temporal Gaussian smoothing to inpainted regions only."""
    import numpy as np
    from scipy.ndimage import gaussian_filter1d

    if len(frames) < 3:
        return frames

    arrays = [np.array(f).astype(np.float32) for f in frames]
    mask_arrays = [np.array(m).astype(np.float32) / 255.0 for m in masks]

    stack = np.stack(arrays, axis=0)  # (T, H, W, C)
    smooth = gaussian_filter1d(stack, sigma=window / 4.0, axis=0)

    result = []
    from PIL import Image
    for i in range(len(frames)):
        mask_2d = mask_arrays[i]
        if mask_2d.ndim == 2:
            mask_3d = mask_2d[:, :, None]
        else:
            mask_3d = mask_2d[:, :, :1]
        blended = arrays[i] * (1 - mask_3d) + smooth[i] * mask_3d
        result.append(Image.fromarray(blended.clip(0, 255).astype(np.uint8)))

    return result


def _temporal_smooth_adaptive(
    frames: list,
    masks: list,
    threshold: float = 30.0,
    window: int = 5,
):
    """Adaptive temporal smoothing — only correct outlier frames."""
    import numpy as np
    from PIL import Image

    if len(frames) < 3:
        return frames

    arrays = [np.array(f).astype(np.float32) for f in frames]
    mask_arrays = [np.array(m).astype(np.float32) / 255.0 for m in masks]

    result = []
    half = window // 2

    for i in range(len(arrays)):
        lo = max(0, i - half)
        hi = min(len(arrays), i + half + 1)
        neighbors = np.stack(arrays[lo:hi], axis=0)
        avg = neighbors.mean(axis=0)

        diff = np.abs(arrays[i] - avg)
        mask_2d = mask_arrays[i]
        if mask_2d.ndim == 2:
            mask_3d = mask_2d[:, :, None]
        else:
            mask_3d = mask_2d[:, :, :1]

        outlier = (diff > threshold).any(axis=-1, keepdims=True).astype(np.float32)
        blend_mask = outlier * mask_3d
        blended = arrays[i] * (1 - blend_mask) + avg * blend_mask
        result.append(Image.fromarray(blended.clip(0, 255).astype(np.uint8)))

    return result


# ---------------------------------------------------------------------------
#  Core removal — process a batch of frames
# ---------------------------------------------------------------------------

def _remove_batch(
    pipe,
    frames_pil: list,
    masks_pil: list,
    seed: int = _RANDOM_SEED,
) -> list:
    """Process a single batch through MiniMax-Remover.

    Args:
        pipe: Minimax_Remover_Pipeline instance
        frames_pil: list of PIL Images (RGB)
        masks_pil: list of PIL Images (L, where 255 = inpaint)
        seed: random seed for reproducibility

    Returns:
        list of PIL Images (RGB) — inpainted results
    """
    import torch
    import numpy as np
    from PIL import Image

    num_frames = len(frames_pil)

    # ── temporal VAE alignment ──
    # The VAE temporally downsamples: num_latent = (F-1)//factor + 1
    # then decodes to (num_latent-1)*factor + 1 frames, which can be
    # *fewer* than input.  Pad to the next aligned count so no frames
    # are lost.  factor = 2^sum(temperal_downsample) = 4 for this model.
    #
    # NOTE: Repeating the last frame as padding is the standard approach
    # for this model architecture.  The last few *real* frames may show
    # minor temporal artifacts because the model "sees" duplicated context
    # at the boundary — this is expected and inherent to the upstream
    # MiniMax-Remover design.  Output is trimmed to ``num_frames`` below.
    _VAE_TEMPORAL_FACTOR = 4
    aligned_frames = ((num_frames - 1 + _VAE_TEMPORAL_FACTOR - 1)
                       // _VAE_TEMPORAL_FACTOR) * _VAE_TEMPORAL_FACTOR + 1
    if aligned_frames > num_frames:
        pad_count = aligned_frames - num_frames
        frames_pil = list(frames_pil) + [frames_pil[-1]] * pad_count
        masks_pil = list(masks_pil) + [masks_pil[-1]] * pad_count
        log.debug("Padded %d → %d frames for VAE alignment", num_frames, aligned_frames)

    # Convert PIL → tensors in range [-1, 1] for images, [0, 1] for masks
    images_np = []
    masks_np = []

    for img in frames_pil:
        arr = np.array(img.convert("RGB")).astype(np.float32) / 127.5 - 1.0
        images_np.append(arr)

    for mask in masks_pil:
        arr = np.array(mask.convert("L")).astype(np.float32) / 255.0
        masks_np.append(arr)

    images_tensor = torch.from_numpy(np.stack(images_np, axis=0))  # (F, H, W, 3)
    masks_tensor = torch.from_numpy(np.stack(masks_np, axis=0))    # (F, H, W)
    # expand_masks uses .repeat(1,1,1,3) which requires 4D (F,H,W,1)
    # input — with 3D, PyTorch prepends a dim giving (1,F,H,3*W) instead
    masks_tensor = masks_tensor.unsqueeze(-1)                      # (F, H, W, 1)

    # Capture original resolution for resize-back after processing.
    # The pipeline processes at _DEFAULT_HEIGHT×_DEFAULT_WIDTH (480×832)
    # and we LANCZOS-upscale back to the input resolution.
    orig_w, orig_h = frames_pil[0].size  # PIL: (width, height)

    device = pipe._execution_device

    result = pipe(
        images=images_tensor,
        masks=masks_tensor,
        num_frames=aligned_frames,
        height=_DEFAULT_HEIGHT,
        width=_DEFAULT_WIDTH,
        num_inference_steps=_NUM_INFERENCE_STEPS,
        generator=torch.Generator(device=device).manual_seed(seed),
        iterations=_NUM_ITERATIONS,
    )

    # Convert output back to PIL at original resolution
    output_frames = []
    video_np = result.frames[0]  # list of numpy arrays or numpy array

    if isinstance(video_np, list):
        for frame_np in video_np:
            if isinstance(frame_np, np.ndarray):
                frame_uint8 = (frame_np * 255).clip(0, 255).astype(np.uint8)
                pil = Image.fromarray(frame_uint8).resize((orig_w, orig_h), Image.LANCZOS)
                output_frames.append(pil)
    elif isinstance(video_np, np.ndarray):
        if video_np.ndim == 4:  # (F, H, W, C)
            for i in range(video_np.shape[0]):
                frame_uint8 = (video_np[i] * 255).clip(0, 255).astype(np.uint8)
                pil = Image.fromarray(frame_uint8).resize((orig_w, orig_h), Image.LANCZOS)
                output_frames.append(pil)
        elif video_np.ndim == 3:  # (H, W, C) single frame
            frame_uint8 = (video_np * 255).clip(0, 255).astype(np.uint8)
            pil = Image.fromarray(frame_uint8).resize((orig_w, orig_h), Image.LANCZOS)
            output_frames.append(pil)

    # Trim to original frame count (discard padding frames)
    return output_frames[:num_frames]


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def remove_object(
    video_path: str,
    mask_video_path: str,
    smoothing: str = "none",
    output_path: Optional[str] = None,
) -> str:
    """Remove an object from a video using MiniMax-Remover.

    This is the main entry point called by the auto_mask handler when
    effect="remove" and MiniMax-Remover is enabled.

    Args:
        video_path: path to source video
        mask_video_path: path to mask video (white = remove)
        smoothing: temporal smoothing mode ("none", "gaussian", "adaptive")
        output_path: output path (auto-generated if None)

    Returns:
        Path to the inpainted video.
    """
    video_path = validate_video_path(video_path)

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix="_minimax_removed.mp4")
        os.close(fd)
    else:
        output_path = validate_output_file_path(output_path)

    log.info("MiniMax-Remover: starting removal")
    log.info("  Video: %s", video_path)
    log.info("  Mask:  %s", mask_video_path)

    pipe = load_pipeline()

    # Load frames and masks
    frames_pil, fps = _load_video_frames(video_path)
    # Pass frame dimensions so fallback masks match the video resolution
    frame_size = frames_pil[0].size if frames_pil else None
    masks_pil = _load_mask_frames(mask_video_path, len(frames_pil),
                                  frame_size=frame_size)

    try:
        import numpy as np
        from PIL import Image

        total_frames = len(frames_pil)
        log.info("MiniMax-Remover: %d frames @ %.1f fps", total_frames, fps)

        # Process in batches with sliding window
        all_output_frames = [None] * total_frames

        if total_frames <= _BATCH_SIZE:
            # Single batch — process all at once
            batch_results = _remove_batch(pipe, frames_pil, masks_pil)
            for i, frame in enumerate(batch_results[:total_frames]):
                all_output_frames[i] = frame
        else:
            # Sliding window batching
            batch_start = 0
            batch_idx = 0

            while batch_start < total_frames:
                batch_end = min(batch_start + _BATCH_SIZE, total_frames)
                batch_frames = frames_pil[batch_start:batch_end]
                batch_masks = masks_pil[batch_start:batch_end]

                # Pad to _BATCH_SIZE if needed (last batch)
                if len(batch_frames) < _BATCH_SIZE:
                    pad_count = _BATCH_SIZE - len(batch_frames)
                    batch_frames = batch_frames + [batch_frames[-1]] * pad_count
                    batch_masks = batch_masks + [batch_masks[-1]] * pad_count

                log.info(
                    "MiniMax-Remover: batch %d — frames %d-%d (of %d)",
                    batch_idx, batch_start, batch_end - 1, total_frames,
                )

                batch_results = _remove_batch(pipe, batch_frames, batch_masks)

                # Place results, handling overlap blending
                actual_count = batch_end - batch_start
                for i in range(actual_count):
                    frame_idx = batch_start + i
                    result_frame = batch_results[i] if i < len(batch_results) else batch_frames[i]

                    if all_output_frames[frame_idx] is None:
                        all_output_frames[frame_idx] = result_frame
                    else:
                        # Overlap region — blend with previous batch result
                        prev = np.array(all_output_frames[frame_idx]).astype(np.float32)
                        curr = np.array(result_frame).astype(np.float32)
                        # Linear blend: earlier batch has more weight at start of overlap
                        overlap_pos = i  # 0 = start of this batch's contribution
                        alpha = overlap_pos / _BATCH_OVERLAP if _BATCH_OVERLAP > 0 else 1.0
                        alpha = min(1.0, alpha)
                        blended = prev * (1 - alpha) + curr * alpha
                        all_output_frames[frame_idx] = Image.fromarray(
                            blended.clip(0, 255).astype(np.uint8)
                        )

                batch_idx += 1
                batch_start += _BATCH_SIZE - _BATCH_OVERLAP

        # Fill any None frames (shouldn't happen, but be safe)
        for i in range(total_frames):
            if all_output_frames[i] is None:
                all_output_frames[i] = frames_pil[i]

        # Apply temporal smoothing if requested
        if smoothing == "gaussian":
            log.info("Applying Gaussian temporal smoothing")
            all_output_frames = _temporal_smooth(all_output_frames, masks_pil)
        elif smoothing == "adaptive":
            log.info("Applying adaptive temporal smoothing")
            all_output_frames = _temporal_smooth_adaptive(all_output_frames, masks_pil)

        # Encode output video
        _encode_video(all_output_frames, output_path, fps)
        log.info("MiniMax-Remover: output saved to %s", output_path)

        return output_path

    finally:
        # Free pipeline memory after use
        cleanup()
