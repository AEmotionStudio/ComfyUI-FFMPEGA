# coding: utf-8
"""Marigold dense vision integration for FFMPEGA.

Supports depth estimation, surface normals, and intrinsic image
decomposition (appearance + lighting) using the Marigold family of
diffusion-based pipelines from ``diffusers``.

Architecture follows the LivePortrait/MMAudio synthesizer pattern:
- In-process execution with GPU↔CPU pipeline offloading
- Cached pipeline state with explicit load/cleanup
- ``comfy.model_management`` VRAM coordination

Based on: https://github.com/prs-eth/marigold

License:
    CreativeML Open RAIL++-M (same as Stable Diffusion 2)
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

log = logging.getLogger("ffmpega")


def _get_ffmpeg_bin() -> str:
    """Get the ffmpeg binary path via bin_paths (includes fallback)."""
    try:
        from .bin_paths import get_ffmpeg_bin
    except ImportError:
        from core.bin_paths import get_ffmpeg_bin  # type: ignore
    return get_ffmpeg_bin()


# ---------------------------------------------------------------------------
#  Output type → HuggingFace checkpoint mapping
# ---------------------------------------------------------------------------

_OUTPUT_TYPES = {
    "depth": {
        "mirror_repo": "AEmotionStudio/marigold-depth-v1-1",
        "upstream_repo": "prs-eth/marigold-depth-v1-1",
        "pipeline_cls": "MarigoldDepthPipeline",
        "description": "Monocular depth estimation",
    },
    "normals": {
        "mirror_repo": "AEmotionStudio/marigold-normals-v1-1",
        "upstream_repo": "prs-eth/marigold-normals-v1-1",
        "pipeline_cls": "MarigoldNormalsPipeline",
        "description": "Surface normals estimation",
    },
    "appearance": {
        "mirror_repo": "AEmotionStudio/marigold-iid-appearance-v1-1",
        "upstream_repo": "prs-eth/marigold-iid-appearance-v1-1",
        "pipeline_cls": "MarigoldIntrinsicsPipeline",
        "description": "Intrinsic decomposition: albedo, roughness, metallicity",
    },
    "lighting": {
        "mirror_repo": "AEmotionStudio/marigold-iid-lighting-v1-1",
        "upstream_repo": "prs-eth/marigold-iid-lighting-v1-1",
        "pipeline_cls": "MarigoldIntrinsicsPipeline",
        "description": "Intrinsic decomposition: albedo, shading, residual",
    },
}

# ---------------------------------------------------------------------------
#  Cached pipeline state
# ---------------------------------------------------------------------------

_pipe: Optional[object] = None
_pipe_output_type: Optional[str] = None


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Free GPU VRAM before loading Marigold pipeline.

    Delegates to the shared ``_vram_utils.free_for_module``.
    """
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="marigold_synthesizer")


def _get_device() -> torch.device:
    """Get the best available device via ComfyUI model management."""
    try:
        import comfy.model_management as mm
        return mm.get_torch_device()
    except (ImportError, AttributeError):
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")


# ---------------------------------------------------------------------------
#  Pipeline loading
# ---------------------------------------------------------------------------


def _load_pipeline(output_type: str):
    """Load (or reuse cached) Marigold pipeline for the given output type.

    Caches the pipeline so consecutive runs of the same type skip loading.
    If the output type changes, the old pipeline is unloaded first.

    Returns:
        The loaded diffusers pipeline instance.
    """
    global _pipe, _pipe_output_type

    if _pipe is not None and _pipe_output_type == output_type:
        log.info("[Marigold] Reusing cached %s pipeline", output_type)
        return _pipe

    # Unload previous pipeline if type changed
    if _pipe is not None:
        cleanup()

    cfg = _OUTPUT_TYPES[output_type]
    mirror_repo = cfg["mirror_repo"]
    upstream_repo = cfg["upstream_repo"]
    cls_name = cfg["pipeline_cls"]

    log.info("[Marigold] Loading %s pipeline...", output_type)

    # Free VRAM from other models
    _free_vram()

    # Check download permission
    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed
    require_downloads_allowed("marigold")

    # Import the appropriate pipeline class
    import diffusers
    PipelineClass = getattr(diffusers, cls_name)

    # Try AEmotionStudio mirror first, fall back to upstream
    pipe = None
    for repo in (mirror_repo, upstream_repo):
        try:
            log.info("[Marigold] Trying repo: %s", repo)
            pipe = PipelineClass.from_pretrained(
                repo,
                variant="fp16",
                torch_dtype=torch.float16,
            ).to(_get_device())
            log.info("[Marigold] Loaded from %s", repo)
            break
        except Exception as exc:
            log.debug("[Marigold] Repo %s failed: %s — trying next", repo, exc)
            continue

    if pipe is None:
        raise RuntimeError(
            f"Failed to load Marigold {output_type} pipeline from both "
            f"{mirror_repo} and {upstream_repo}. Check your internet "
            f"connection or install the model manually."
        )

    # Optimise attention
    try:
        from diffusers.models.attention_processor import AttnProcessor2_0
        pipe.vae.set_attn_processor(AttnProcessor2_0())
        pipe.unet.set_attn_processor(AttnProcessor2_0())
    except Exception:
        pass

    pipe.set_progress_bar_config(disable=True)

    _pipe = pipe
    _pipe_output_type = output_type

    log.info("[Marigold] %s pipeline loaded successfully", output_type)
    return pipe


def cleanup() -> None:
    """Free GPU memory and clear cached Marigold pipeline."""
    global _pipe, _pipe_output_type

    if _pipe is None:
        return

    pipe = _pipe
    _pipe = None
    _pipe_output_type = None

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

    log.info("[Marigold] Pipeline unloaded")


# ---------------------------------------------------------------------------
#  Frame processing helpers
# ---------------------------------------------------------------------------


def _process_single_image(pipe, image, output_type: str,
                          num_steps: int, ensemble_size: int) -> dict:
    """Run Marigold inference on a single PIL Image.

    Returns:
        Dict with visualization PIL Image(s) keyed by property name.
    """
    result = pipe(
        image,
        num_inference_steps=num_steps,
        ensemble_size=ensemble_size,
    )

    if output_type == "depth":
        vis_list = pipe.image_processor.visualize_depth(result.prediction)
        return {"depth": vis_list[0]}

    elif output_type == "normals":
        vis_list = pipe.image_processor.visualize_normals(result.prediction)
        return {"normals": vis_list[0]}

    elif output_type in ("appearance", "lighting"):
        vis_list = pipe.image_processor.visualize_intrinsics(
            result.prediction, pipe.target_properties
        )
        return vis_list[0]  # dict with albedo, roughness/metallicity or shading/residual

    return {}


def _read_video_frames(video_path: str, max_res: int = 768):
    """Read video frames as PIL Images, respecting max resolution.

    Returns:
        (frames, fps, width, height) where frames is a list of PIL Images.
    """
    from PIL import Image
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Scale to max resolution
    scale = min(max_res / max(orig_w, orig_h), 1.0)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    # Ensure dimensions are divisible by 8 (VAE requirement)
    new_w = (new_w // 8) * 8
    new_h = (new_h // 8) * 8

    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if scale < 1.0:
            frame = cv2.resize(frame, (new_w, new_h),
                               interpolation=cv2.INTER_AREA)
        # BGR → RGB → PIL
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(Image.fromarray(rgb))

    cap.release()
    return frames, fps, new_w, new_h


def _save_frames_as_video(frames, output_path: str, fps: float) -> None:
    """Save PIL Image frames as an MP4 video using ffmpeg."""
    if not frames:
        return

    w, h = frames[0].size
    tmp_dir = tempfile.mkdtemp(prefix="marigold_")

    try:
        for i, frame in enumerate(frames):
            frame.save(os.path.join(tmp_dir, f"{i:06d}.png"))

        # Use integer framerate for ffmpeg compatibility
        fps_str = str(int(round(fps))) if round(fps, 2) == int(round(fps)) else f"{fps:.2f}"
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


def run_marigold(
    input_path: str,
    output_type: str = "depth",
    num_steps: int = 4,
    ensemble_size: int = 1,
    max_res: int = 768,
) -> str:
    """Run Marigold dense vision analysis on an image or video.

    Args:
        input_path: Path to input image or video file.
        output_type: One of 'depth', 'normals', 'appearance', 'lighting'.
        num_steps: Number of denoising steps (1-50, default 4).
        ensemble_size: Number of ensemble predictions (1-10, default 1).
        max_res: Maximum processing resolution (default 768).

    Returns:
        Path to the output file (image or video).

    Raises:
        ValueError: If output_type is invalid.
        RuntimeError: If input file cannot be read.
    """
    if output_type not in _OUTPUT_TYPES:
        raise ValueError(
            f"Invalid output_type '{output_type}'. "
            f"Must be one of: {list(_OUTPUT_TYPES.keys())}"
        )

    if not os.path.isfile(input_path):
        raise RuntimeError(f"Input file not found: {input_path}")

    num_steps = max(1, min(50, int(num_steps)))
    ensemble_size = max(1, min(10, int(ensemble_size)))

    pipe = _load_pipeline(output_type)

    # Determine if input is image or video
    ext = os.path.splitext(input_path)[1].lower()
    _image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
    _video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
                   ".ts", ".m4v"}

    if ext in _image_exts:
        return _process_image(pipe, input_path, output_type,
                              num_steps, ensemble_size)
    elif ext in _video_exts:
        return _process_video(pipe, input_path, output_type,
                              num_steps, ensemble_size, max_res)
    else:
        # Try as image first, fall back to video
        try:
            return _process_image(pipe, input_path, output_type,
                                  num_steps, ensemble_size)
        except Exception:
            return _process_video(pipe, input_path, output_type,
                                  num_steps, ensemble_size, max_res)


def _process_image(pipe, input_path: str, output_type: str,
                   num_steps: int, ensemble_size: int) -> str:
    """Process a single image through Marigold."""
    from PIL import Image

    log.info("[Marigold] Processing image: %s (type=%s, steps=%d, ensemble=%d)",
             input_path, output_type, num_steps, ensemble_size)

    image = Image.open(input_path).convert("RGB")

    with torch.inference_mode():
        vis = _process_single_image(pipe, image, output_type,
                                    num_steps, ensemble_size)

    # Save the primary output
    # For depth/normals: single image. For IID: pick the first key.
    if isinstance(vis, dict):
        primary_key = list(vis.keys())[0]
        primary_img = vis[primary_key]
    else:
        primary_img = vis

    suffix = f"_marigold_{output_type}.png"
    _fd, output_path = tempfile.mkstemp(suffix=suffix)
    os.close(_fd)
    primary_img.save(output_path)

    log.info("[Marigold] Image output saved to %s", output_path)
    return output_path


def _process_video(pipe, input_path: str, output_type: str,
                   num_steps: int, ensemble_size: int,
                   max_res: int) -> str:
    """Process a video through Marigold with temporal consistency.

    Uses exponential moving average (EMA) smoothing on raw prediction
    tensors to reduce inter-frame flickering.  Works for all output
    types (depth, normals, appearance, lighting).
    """
    from PIL import Image

    log.info("[Marigold] Processing video: %s (type=%s, steps=%d, max_res=%d)",
             input_path, output_type, num_steps, max_res)

    frames, fps, w, h = _read_video_frames(input_path, max_res)
    if not frames:
        raise RuntimeError(f"No frames extracted from video: {input_path}")

    log.info("[Marigold] Processing %d frames at %.1f fps (%dx%d)",
             len(frames), fps, w, h)

    # EMA smoothing factor: lower alpha = smoother (more temporal weight).
    # 0.3 keeps 70% of the running average, 30% of the new frame.
    _EMA_ALPHA = 0.3

    # Use a fixed generator for deterministic noise across frames
    generator = torch.Generator(device=_get_device()).manual_seed(42)

    output_frames = []
    ema_prediction = None  # running EMA of raw prediction tensor

    with torch.inference_mode():
        for i, frame in enumerate(frames):
            if (i + 1) % 50 == 0 or i == 0:
                log.info("[Marigold] Frame %d/%d", i + 1, len(frames))

            # Run inference with fixed generator for stable noise
            result = pipe(
                frame,
                num_inference_steps=num_steps,
                ensemble_size=ensemble_size,
                generator=generator,
            )

            # Get raw prediction tensor and apply EMA smoothing
            pred = result.prediction  # shape varies by pipeline

            if ema_prediction is None:
                ema_prediction = pred.copy()
            else:
                # EMA: new_avg = alpha * current + (1 - alpha) * running_avg
                ema_prediction = _EMA_ALPHA * pred + (1.0 - _EMA_ALPHA) * ema_prediction

            # Visualize from the smoothed prediction
            if output_type == "depth":
                vis = pipe.image_processor.visualize_depth(ema_prediction)
                output_frames.append(vis[0])
            elif output_type == "normals":
                vis = pipe.image_processor.visualize_normals(ema_prediction)
                output_frames.append(vis[0])
            elif output_type in ("appearance", "lighting"):
                vis = pipe.image_processor.visualize_intrinsics(
                    ema_prediction, pipe.target_properties
                )
                # vis[0] is a dict with property names as keys
                primary_key = list(vis[0].keys())[0]
                output_frames.append(vis[0][primary_key])

    # Save output video
    suffix = f"_marigold_{output_type}.mp4"
    _fd, output_path = tempfile.mkstemp(suffix=suffix)
    os.close(_fd)
    _save_frames_as_video(output_frames, output_path, fps)

    log.info("[Marigold] Video output saved to %s (%d frames)",
             output_path, len(output_frames))
    return output_path

