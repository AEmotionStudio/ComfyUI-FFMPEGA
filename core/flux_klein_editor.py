"""FLUX Klein Editor — per-frame image editing and removal using FLUX.2 Klein 4B.

Uses the ``diffusers`` library's ``Flux2KleinPipeline`` for text-guided
image editing via reference-image conditioning.  Each video frame is
processed individually with consistent seeding for temporal coherence.

Key capabilities:
- **Object removal**: mask + reference image → "fill naturally"
- **Text-guided editing**: mask + prompt → "change hair to blonde", etc.

Model: FLUX.2 [klein] 4B (Apache 2.0)
VRAM:  ~8–13 GB (fp16/bf16, with CPU offload)
Speed: 4-step inference, sub-second per frame

License: Apache 2.0 (compatible with GPL-3.0)
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

try:
    from .sanitize import validate_video_path, validate_output_file_path
except ImportError:
    from core.sanitize import validate_video_path, validate_output_file_path  # type: ignore

log = logging.getLogger("ffmpega")

# Cached ffmpeg binary path (resolved once at import time)
_FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

_HF_REPO = "black-forest-labs/FLUX.2-klein-4B"
_MIRROR_REPO = "AEmotionStudio/flux-klein"
_MODEL_DIR_NAME = "flux_klein"

# Default prompt for object removal (narrative prose per BFL best practices)
_REMOVAL_PROMPT = (
    "A clean, natural image where the masked region has been seamlessly "
    "filled with the surrounding background, matching lighting, texture, "
    "and perspective perfectly. No artifacts or visible boundaries."
)

# Pipeline inference defaults
_NUM_STEPS = 4
_GUIDANCE_SCALE = 1.0
_OUTPUT_SIZE = 1024  # Klein generates at 1024x1024

# Cached pipeline
_pipeline = None


# ---------------------------------------------------------------------------
#  Model directory and downloading
# ---------------------------------------------------------------------------

def _get_model_dir() -> Path:
    """Get or create the FLUX Klein model directory.

    Checks (in order):
    1. FFMPEGA_FLUX_KLEIN_MODEL_DIR env var (set by subprocess wrapper)
    2. ComfyUI/models/flux_klein/ (standard ComfyUI convention)
    3. Extension's own models/flux_klein/ (fallback)
    """
    env_dir = os.environ.get("FFMPEGA_FLUX_KLEIN_MODEL_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    for candidate in [
        Path(__file__).resolve().parents[3] / "models" / _MODEL_DIR_NAME,
        Path.home() / "ComfyUI" / "models" / _MODEL_DIR_NAME,
    ]:
        if candidate.parent.is_dir():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate

    fallback = Path.home() / ".cache" / _MODEL_DIR_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _download_model(model_dir: Path) -> None:
    """Download model weights from HuggingFace if not present.

    Tries the AEmotionStudio mirror first, then falls back to the
    official BFL repo.
    """
    # Check if already downloaded (look for model_index.json — diffusers marker)
    if (model_dir / "model_index.json").is_file():
        return

    try:
        from . import model_manager as _mm
    except ImportError:
        from core import model_manager as _mm  # type: ignore

    _mm.require_downloads_allowed("flux_klein")

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise ImportError(
            "huggingface_hub is required to download FLUX Klein. "
            "Install with: pip install huggingface_hub"
        )

    # Try AEmotionStudio mirror first
    log.info("FLUX Klein weights not found. Downloading...")
    try:
        _mm.download_with_progress(
            "flux_klein",
            lambda: snapshot_download(
                repo_id=_MIRROR_REPO,
                local_dir=str(model_dir),
            ),
            extra="~8 GB fp16",
        )
        log.info("FLUX Klein downloaded from AEmotionStudio mirror")
        return
    except Exception as e:
        log.warning("Mirror download failed: %s — trying official repo", e)

    # Fall back to official BFL repo
    _mm.download_with_progress(
        "flux_klein",
        lambda: snapshot_download(
            repo_id=_HF_REPO,
            local_dir=str(model_dir),
        ),
        extra="~8 GB",
    )
    log.info("FLUX Klein downloaded from official repo: %s", _HF_REPO)


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Free all GPU VRAM before loading FLUX Klein.

    Follows WanVideoWrapper's pattern:
    1. Tell ComfyUI to unload ALL cached models from GPU
    2. Free SAM3 models if loaded
    3. Empty CUDA cache
    4. Run garbage collection to release Python-side references
    """
    import torch

    # 1. Unload ComfyUI models (the main VRAM consumer)
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.unload_all_models()
        mm.soft_empty_cache()
        log.debug("Freed ComfyUI GPU VRAM via model_management")
    except (ImportError, AttributeError):
        pass

    # 2. Free SAM3 if loaded
    try:
        try:
            from . import sam3_masker
        except ImportError:
            from core import sam3_masker  # type: ignore
        sam3_masker.cleanup()
    except Exception:
        pass

    # 3. Empty CUDA cache + gc.collect
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()


# ---------------------------------------------------------------------------
#  Pipeline loading
# ---------------------------------------------------------------------------

def load_pipeline():
    """Load and cache the FLUX Klein pipeline.

    Returns:
        Flux2KleinPipeline instance ready for inference.

    Raises:
        ImportError: If diffusers is not installed or too old.
        RuntimeError: If model download fails.
    """
    global _pipeline

    if _pipeline is not None:
        return _pipeline

    try:
        from diffusers import Flux2KleinPipeline  # type: ignore[attr-defined]
    except ImportError:
        raise ImportError(
            "diffusers with FLUX.2 Klein support is required. "
            "Install with: pip install git+https://github.com/huggingface/diffusers.git"
        )

    model_dir = _get_model_dir()
    _download_model(model_dir)
    _free_vram()

    log.info("Loading FLUX Klein pipeline from %s", model_dir)

    import torch

    # Use bfloat16 for best quality on supported hardware,
    # fall back to float16 if bfloat16 is not supported
    dtype = torch.bfloat16
    if torch.cuda.is_available():
        cap = torch.cuda.get_device_capability()
        if cap[0] < 8:  # Pre-Ampere GPUs don't support bfloat16 well
            dtype = torch.float16
            log.info("Using float16 (GPU compute capability %d.%d)", *cap)

    pipe = Flux2KleinPipeline.from_pretrained(
        str(model_dir),
        torch_dtype=dtype,
    )
    pipe.enable_model_cpu_offload()  # Save VRAM by offloading to CPU

    _pipeline = pipe
    log.info("FLUX Klein pipeline loaded successfully (dtype=%s)", dtype)
    return _pipeline


def cleanup() -> None:
    """Free GPU memory and clear cached pipeline.

    Follows WanVideoWrapper's cleanup pattern: release pipeline,
    empty CUDA cache, run gc, and tell ComfyUI to reclaim memory.
    """
    global _pipeline
    _pipeline = None
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    gc.collect()
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass
    log.info("FLUX Klein pipeline unloaded")


# ---------------------------------------------------------------------------
#  Frame I/O helpers (shared with lama_inpainter)
# ---------------------------------------------------------------------------

def _load_video_frames(video_path: str):
    """Load video frames as PIL Images.

    Returns:
        (frames_pil, fps, tmpdir)
    """
    from PIL import Image

    tmpdir = tempfile.mkdtemp(prefix="fk_frames_")
    _ffmpeg = _FFMPEG_BIN
    subprocess.run(
        [
            _ffmpeg, "-i", video_path,
            "-q:v", "2",
            os.path.join(tmpdir, "%06d.png"),
        ],
        capture_output=True,
        check=True,
    )

    frame_files = sorted(Path(tmpdir).glob("*.png"))
    frames = [Image.open(f).convert("RGB") for f in frame_files]

    # Get FPS
    try:
        from .sam3_masker import _get_video_fps
    except ImportError:
        from core.sam3_masker import _get_video_fps  # type: ignore
    fps = _get_video_fps(video_path)

    if not frames:
        raise RuntimeError(f"No frames extracted from {video_path}")

    return frames, fps, tmpdir


def _load_mask_frames(mask_video_path: str, num_frames: int):
    """Load mask frames as PIL Images (mode 'L').

    Returns:
        (masks, tmpdir)
    """
    from PIL import Image

    tmpdir = tempfile.mkdtemp(prefix="fk_masks_")
    _ffmpeg = _FFMPEG_BIN
    subprocess.run(
        [
            _ffmpeg, "-i", mask_video_path,
            "-q:v", "2",
            os.path.join(tmpdir, "%06d.png"),
        ],
        capture_output=True,
        check=True,
    )

    mask_files = sorted(Path(tmpdir).glob("*.png"))
    masks = [Image.open(f).convert("L") for f in mask_files[:num_frames]]

    if masks and len(masks) < num_frames:
        while len(masks) < num_frames:
            masks.append(Image.new("L", masks[0].size, 0))

    return masks, tmpdir


def _encode_video(frames: list, output_path: str, fps: float) -> str:
    """Encode PIL frames to a video file."""
    tmpdir = tempfile.mkdtemp(prefix="fk_out_")
    for i, frame in enumerate(frames):
        frame.save(os.path.join(tmpdir, f"{i:06d}.png"))

    _ffmpeg = _FFMPEG_BIN
    subprocess.run(
        [
            _ffmpeg, "-y",
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
    frames: list,
    masks: list,
    window: int = 5,
) -> list:
    """Apply temporal Gaussian smoothing to edited regions only.

    Reduces per-frame flickering by blending neighboring results
    in the masked area. Original pixels are untouched.
    """
    import numpy as np
    from scipy.ndimage import gaussian_filter1d

    n = len(frames)
    if n <= 1:
        return frames

    stack = np.stack(frames).astype(np.float32)
    mask_stack = np.stack(masks)
    sigma = window / 3.0
    smoothed = gaussian_filter1d(stack, sigma=sigma, axis=0)

    result = []
    for i in range(n):
        m = mask_stack[i][:, :, None]
        blended = stack[i] * (1 - m) + smoothed[i] * m
        result.append(np.clip(blended, 0, 255).astype(np.uint8))

    return result


def _temporal_smooth_adaptive(
    frames: list,
    masks: list,
    threshold: float = 30.0,
    window: int = 5,
) -> list:
    """Adaptive temporal smoothing — only correct outlier frames.

    Compares each frame to its temporal neighbors in the masked region.
    If the per-pixel difference exceeds *threshold*, blend with neighbors.
    Otherwise, keep the original frame untouched.

    This preserves sharp per-frame detail while fixing occasional
    flickering artifacts.
    """
    import numpy as np

    n = len(frames)
    if n <= 1:
        return frames

    stack = np.stack(frames).astype(np.float32)
    mask_stack = np.stack(masks)
    # Ensure masks are 2D (H×W) — squeeze trailing channel dim if present
    if mask_stack.ndim == 4:
        mask_stack = mask_stack.squeeze(-1)
    half_w = window // 2

    result = []
    for i in range(n):
        m = mask_stack[i]
        if m.max() < 0.01:
            result.append(frames[i])
            continue

        # Compute mean of neighbors in the window (exclude frame i itself
        # so the outlier doesn't dilute its own deviation signal)
        lo = max(0, i - half_w)
        hi = min(n, i + half_w + 1)
        neighbor_idx = [j for j in range(lo, hi) if j != i]
        if not neighbor_idx:
            result.append(frames[i])
            continue
        neighbors = stack[neighbor_idx]
        neighbor_mean = neighbors.mean(axis=0)

        # Per-pixel diff in masked region
        diff = np.abs(stack[i] - neighbor_mean)
        masked_diff = diff * m[:, :, None]
        avg_diff = masked_diff.sum() / max(m.sum() * 3, 1)

        if avg_diff > threshold:
            # This frame is an outlier — blend with neighbors
            blended = stack[i] * (1 - m[:, :, None]) + neighbor_mean * m[:, :, None]
            result.append(np.clip(blended, 0, 255).astype(np.uint8))
        else:
            result.append(frames[i])

    return result


# ---------------------------------------------------------------------------
#  Per-frame editing
# ---------------------------------------------------------------------------

def _edit_frame(
    pipe,
    image,
    prompt: str,
    seed: int = 42,
):
    """Edit a single frame using FLUX Klein reference-image conditioning.

    Args:
        pipe: Flux2KleinPipeline instance
        image: PIL.Image.Image — source frame (used as reference)
        prompt: Text describing the desired edit
        seed: Random seed for reproducibility

    Returns:
        PIL.Image.Image — edited result at the original resolution
    """
    import torch
    from PIL import Image

    orig_w, orig_h = image.size

    # Resize to model's expected resolution
    ref_image = image.resize((_OUTPUT_SIZE, _OUTPUT_SIZE), Image.LANCZOS)  # type: ignore[attr-defined]

    device = pipe._execution_device if hasattr(pipe, '_execution_device') else "cuda"
    generator = torch.Generator(device=device).manual_seed(seed)

    result = pipe(
        prompt=prompt,
        image=[ref_image],
        height=_OUTPUT_SIZE,
        width=_OUTPUT_SIZE,
        guidance_scale=_GUIDANCE_SCALE,
        num_inference_steps=_NUM_STEPS,
        generator=generator,
    ).images[0]

    # Resize back to original resolution
    if result.size != (orig_w, orig_h):
        result = result.resize((orig_w, orig_h), Image.LANCZOS)  # type: ignore[attr-defined]

    return result


def _remove_frame(
    pipe,
    image,
    mask,
    seed: int = 42,
):
    """Remove masked region from a single frame using FLUX Klein.

    Creates a masked version of the image (region blacked out) as the
    reference, then prompts FLUX Klein to fill naturally.

    Args:
        pipe: Flux2KleinPipeline instance
        image: PIL.Image.Image (RGB)
        mask: PIL.Image.Image (L, 255 = region to remove)
        seed: Random seed

    Returns:
        PIL.Image.Image — result with object removed
    """
    import numpy as np
    import torch
    from PIL import Image

    orig_w, orig_h = image.size

    # Create masked image: black out the region to remove
    img_arr = np.array(image).copy()
    mask_arr = np.array(mask.resize(image.size, Image.NEAREST))  # type: ignore[attr-defined]
    img_arr[mask_arr > 128] = 0
    masked_image = Image.fromarray(img_arr)

    # Resize to model resolution
    ref_image = masked_image.resize((_OUTPUT_SIZE, _OUTPUT_SIZE), Image.LANCZOS)  # type: ignore[attr-defined]

    device = pipe._execution_device if hasattr(pipe, '_execution_device') else "cuda"
    generator = torch.Generator(device=device).manual_seed(seed)

    result = pipe(
        prompt=_REMOVAL_PROMPT,
        image=[ref_image],
        height=_OUTPUT_SIZE,
        width=_OUTPUT_SIZE,
        guidance_scale=_GUIDANCE_SCALE,
        num_inference_steps=_NUM_STEPS,
        generator=generator,
    ).images[0]

    # Resize back to original resolution
    if result.size != (orig_w, orig_h):
        result = result.resize((orig_w, orig_h), Image.LANCZOS)  # type: ignore[attr-defined]

    return result


# ---------------------------------------------------------------------------
#  Compositing
# ---------------------------------------------------------------------------

def _composite_frame(
    original,
    edited,
    mask,
) -> "np.ndarray":  # type: ignore[name-defined]
    """Composite edited pixels onto original using the mask.

    Args:
        original: PIL.Image.Image — original frame
        edited: PIL.Image.Image — edited/inpainted frame
        mask: PIL.Image.Image (L) — mask

    Returns:
        (H, W, 3) uint8 composited result
    """
    import numpy as np
    from PIL import Image

    orig_arr = np.array(original).astype(np.float32)
    edit_arr = np.array(edited).astype(np.float32)
    mask_pil = mask.resize(original.size, Image.NEAREST) if mask.size != original.size else mask  # type: ignore[attr-defined]
    mask_arr = np.array(mask_pil).astype(np.float32) / 255.0
    mask_3ch = mask_arr[:, :, None]

    result = orig_arr * (1 - mask_3ch) + edit_arr * mask_3ch
    return result.astype(np.uint8)


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def remove_object(
    video_path: str,
    mask_video_path: str,
    output_path: Optional[str] = None,
    smoothing: str = "none",
) -> str:
    """Remove an object from a video using FLUX Klein per-frame inpainting.

    This is the main entry point called by the auto_mask handler when
    effect="remove".

    Args:
        video_path: path to the original video
        mask_video_path: path to the mask video (white = object to remove)
        output_path: output path (auto-generated if None)

    Returns:
        Path to the inpainted video.

    Raises:
        ImportError: If diffusers is not installed.
        RuntimeError: If model download or inference fails.
    """
    return edit_video(
        video_path=video_path,
        mask_video_path=mask_video_path,
        prompt=_REMOVAL_PROMPT,
        output_path=output_path,
        mode="remove",
        smoothing=smoothing,
    )


def edit_video(
    video_path: str,
    mask_video_path: str,
    prompt: str,
    output_path: Optional[str] = None,
    mode: str = "edit",
    smoothing: str = "none",
) -> str:
    """Edit a video using FLUX Klein per-frame image editing.

    Supports two modes:
    - "remove": fills masked regions with surrounding context
    - "edit": applies text-guided changes to masked regions

    Args:
        video_path: path to the original video
        mask_video_path: path to the mask video (white = region to edit)
        prompt: text prompt describing the desired edit
        output_path: output path (auto-generated if None)
        mode: "remove" or "edit"
        smoothing: temporal smoothing mode:
            - "none": no smoothing (best for high-quality per-frame edits)
            - "gaussian": full Gaussian blur across time (reduces flicker,
              but can muddy motion)
            - "adaptive": only smooth frames that deviate significantly
              from neighbors (preserves good frames, fixes outliers)

    Returns:
        Path to the edited video.
    """
    video_path = validate_video_path(video_path)
    mask_video_path = validate_video_path(mask_video_path)
    if output_path is not None:
        output_path = validate_output_file_path(output_path)

    import numpy as np
    from PIL import Image

    if output_path is None:
        tmpdir = tempfile.mkdtemp(prefix="fk_result_")
        output_path = os.path.join(tmpdir, "edited.mp4")

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
    masks_tmpdir = None

    try:
        masks, masks_tmpdir = _load_mask_frames(mask_video_path, total_frames)

        # Load pipeline
        pipe = load_pipeline()

        # Use a fixed seed for temporal consistency across frames
        base_seed = 42

        # Per-frame processing
        log.info("Running FLUX Klein %s on %d frames...", mode, total_frames)
        composited_np = []
        mask_np_list = []

        import torch

        for i in range(total_frames):
            if i % 10 == 0:
                log.info("  Frame %d/%d", i + 1, total_frames)

            # Check if mask has any content (skip blank masks)
            mask_arr = np.array(masks[i])
            if mask_arr.max() < 10:
                composited_np.append(np.array(frames[i]))
                mask_np_list.append(
                    np.zeros(
                        (frames[i].height, frames[i].width),
                        dtype=np.float32,
                    )
                )
                continue

            # Edit or remove the frame (no_grad prevents autograd from
            # accumulating graph memory across frames)
            with torch.no_grad():
                if mode == "remove":
                    edited = _remove_frame(pipe, frames[i], masks[i], seed=base_seed)
                else:
                    edited = _edit_frame(pipe, frames[i], prompt, seed=base_seed)

            # Composite
            result = _composite_frame(frames[i], edited, masks[i])
            composited_np.append(result)

            mask_np = np.array(
                masks[i].resize(frames[i].size, Image.NEAREST)  # type: ignore[attr-defined]
                if masks[i].size != frames[i].size
                else masks[i]
            ).astype(np.float32) / 255.0
            mask_np_list.append(mask_np)

            # Periodic VRAM cleanup to prevent fragmentation over long videos
            if i % 5 == 0 and torch.cuda.is_available():
                torch.cuda.empty_cache()

        # Temporal smoothing
        if smoothing == "gaussian":
            log.info("Applying temporal Gaussian smoothing...")
            smoothed = _temporal_smooth(composited_np, mask_np_list, window=5)
        elif smoothing == "adaptive":
            log.info("Applying adaptive temporal smoothing...")
            smoothed = _temporal_smooth_adaptive(
                composited_np, mask_np_list, threshold=30.0, window=5,
            )
        else:
            log.info("Temporal smoothing disabled")
            smoothed = composited_np

        # Convert back to PIL
        result_frames = [Image.fromarray(arr) for arr in smoothed]

        # Encode result
        log.info("Encoding edited video to %s", output_path)
        _encode_video(result_frames, output_path, fps)
    finally:
        import shutil
        for d in (frames_tmpdir, masks_tmpdir):
            if d is None:
                continue
            try:
                shutil.rmtree(d)
            except OSError:
                pass

    # Free VRAM
    cleanup()

    log.info("FLUX Klein %s complete: %s", mode, output_path)
    return output_path

