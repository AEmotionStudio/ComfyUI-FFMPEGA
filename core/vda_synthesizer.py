# coding: utf-8
"""Video Depth Anything integration for FFMPEGA.

Provides temporally-consistent video depth estimation using the
Video Depth Anything (VDA) model (CVPR 2025 Highlight). Unlike
per-frame models like Marigold, VDA has native temporal attention
layers that produce flicker-free depth videos.

Architecture follows the LivePortrait/Marigold synthesizer pattern:
- In-process execution with GPU↔CPU pipeline offloading
- Cached model state with explicit load/cleanup
- ``comfy.model_management`` VRAM coordination

Based on: https://github.com/DepthAnything/Video-Depth-Anything

License:
    Apache License 2.0 (Bytedance)
"""

import gc
import logging
import os
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import cv2
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
#  Model configurations
# ---------------------------------------------------------------------------

MODEL_CONFIGS = {
    "vits": {
        "encoder": "vits",
        "features": 64,
        "out_channels": [48, 96, 192, 384],
        "hf_repo": "depth-anything/Video-Depth-Anything-Small",
        "mirror_repo": "AEmotionStudio/Video-Depth-Anything-Small",
        "filename": "video_depth_anything_vits.safetensors",
        "fallback_filename": "video_depth_anything_vits.pth",
        "size": "~102 MB",
    },
    "vitb": {
        "encoder": "vitb",
        "features": 128,
        "out_channels": [96, 192, 384, 768],
        "hf_repo": "depth-anything/Video-Depth-Anything-Base",
        "mirror_repo": "AEmotionStudio/Video-Depth-Anything-Base",
        "filename": "video_depth_anything_vitb.safetensors",
        "fallback_filename": "video_depth_anything_vitb.pth",
        "size": "~390 MB",
    },
    "vitl": {
        "encoder": "vitl",
        "features": 256,
        "out_channels": [256, 512, 1024, 1024],
        "hf_repo": "depth-anything/Video-Depth-Anything-Large",
        "mirror_repo": "AEmotionStudio/Video-Depth-Anything-Large",
        "filename": "video_depth_anything_vitl.safetensors",
        "fallback_filename": "video_depth_anything_vitl.pth",
        "size": "~670 MB",
    },
}

# ---------------------------------------------------------------------------
#  Cached model state
# ---------------------------------------------------------------------------

_model: Optional[object] = None
_model_encoder: Optional[str] = None


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Aggressively free GPU VRAM before loading VDA model.

    Delegates to the shared ``_vram_utils.free_for_module``.
    """
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="vda_synthesizer")


def _get_device() -> torch.device:
    """Get the best available device via ComfyUI model management."""
    try:
        import comfy.model_management as mm
        return mm.get_torch_device()
    except (ImportError, AttributeError):
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")


def _get_offload_device() -> torch.device:
    """Get the ComfyUI offload device (usually CPU)."""
    try:
        import comfy.model_management as mm
        return mm.unet_offload_device()
    except (ImportError, AttributeError):
        return torch.device("cpu")


# ---------------------------------------------------------------------------
#  Model loading
# ---------------------------------------------------------------------------


def _download_checkpoint(encoder: str) -> str:
    """Download VDA checkpoint from HuggingFace, mirror first.

    Tries safetensors first from mirror, then falls back to .pth from upstream.

    Returns:
        Local path to the downloaded checkpoint file.
    """
    cfg = MODEL_CONFIGS[encoder]

    # Check download permission
    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed
    require_downloads_allowed("video_depth")

    from huggingface_hub import hf_hub_download

    # Try mirror with safetensors first
    try:
        log.info("[VDA] Trying safetensors from: %s", cfg["mirror_repo"])
        path = hf_hub_download(
            repo_id=cfg["mirror_repo"],
            filename=cfg["filename"],
        )
        log.info("[VDA] Checkpoint downloaded: %s", path)
        return path
    except Exception as exc:
        log.debug("[VDA] Mirror safetensors failed: %s", exc)

    # Try mirror with .pth fallback
    try:
        log.info("[VDA] Trying .pth from: %s", cfg["mirror_repo"])
        path = hf_hub_download(
            repo_id=cfg["mirror_repo"],
            filename=cfg["fallback_filename"],
        )
        log.info("[VDA] Checkpoint downloaded (pth): %s", path)
        return path
    except Exception as exc:
        log.debug("[VDA] Mirror pth failed: %s", exc)

    # Fallback to upstream .pth
    try:
        log.info("[VDA] Trying upstream: %s", cfg["hf_repo"])
        path = hf_hub_download(
            repo_id=cfg["hf_repo"],
            filename=cfg["fallback_filename"],
        )
        log.info("[VDA] Checkpoint downloaded (upstream): %s", path)
        return path
    except Exception as exc:
        log.debug("[VDA] Upstream failed: %s", exc)

    raise RuntimeError(
        f"Failed to download VDA {encoder} checkpoint from both "
        f"{cfg['mirror_repo']} and {cfg['hf_repo']}. "
        f"Check your internet connection."
    )


def _load_state_dict_from_file(path: str) -> dict:
    """Load state dict using ComfyUI's loader (handles safetensors + pth)."""
    try:
        from comfy.utils import load_torch_file
        return load_torch_file(path)
    except ImportError:
        # Fallback if comfy not available (testing)
        if path.endswith(".safetensors"):
            from safetensors.torch import load_file
            return load_file(path, device="cpu")
        else:
            return torch.load(path, map_location="cpu", weights_only=True)


def _load_model(encoder: str = "vits"):
    """Load (or reuse cached) VDA model.

    Caches the model so consecutive runs with the same encoder skip loading.
    If the encoder changes, the old model is unloaded first.

    The model is loaded in FP16 to minimize VRAM usage.

    Returns:
        The loaded VideoDepthAnything model.
    """
    global _model, _model_encoder

    if _model is not None and _model_encoder == encoder:
        log.info("[VDA] Reusing cached %s model", encoder)
        # Move back to GPU if it was offloaded
        device = _get_device()
        if next(_model.parameters()).device != device:
            _model = _model.to(device)
        return _model

    # Unload previous model if encoder changed
    if _model is not None:
        cleanup()

    if encoder not in MODEL_CONFIGS:
        raise ValueError(
            f"Invalid encoder '{encoder}'. "
            f"Must be one of: {list(MODEL_CONFIGS.keys())}"
        )

    cfg = MODEL_CONFIGS[encoder]
    log.info("[VDA] Loading %s model (%s)...", encoder, cfg["size"])

    # Free VRAM from other models BEFORE loading
    _free_vram()

    # Download checkpoint
    ckpt_path = _download_checkpoint(encoder)

    # Import and instantiate model
    try:
        from .video_depth_anything.video_depth import VideoDepthAnything
    except ImportError:
        from core.video_depth_anything.video_depth import VideoDepthAnything

    model = VideoDepthAnything(
        encoder=cfg["encoder"],
        features=cfg["features"],
        out_channels=cfg["out_channels"],
    )

    state_dict = _load_state_dict_from_file(ckpt_path)
    model.load_state_dict(state_dict, strict=True)
    del state_dict
    gc.collect()

    # Keep model in FP32 — VDA's infer_video_depth uses torch.autocast
    # for FP16 during inference. Forcing FP16 on weights causes dtype
    # mismatch in DPT head which does .float() on activations mid-forward.
    device = _get_device()
    model = model.to(device).eval()

    _model = model
    _model_encoder = encoder

    if torch.cuda.is_available():
        used = torch.cuda.memory_allocated() / (1024**3)
        log.info("[VDA] %s model loaded (%.2f GiB VRAM)", encoder, used)
    else:
        log.info("[VDA] %s model loaded on CPU", encoder)

    return model


def cleanup() -> None:
    """Free GPU memory and clear cached VDA model."""
    global _model, _model_encoder

    if _model is None:
        return

    model = _model
    _model = None
    _model_encoder = None

    try:
        model.cpu()
    except Exception:
        pass
    del model

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    try:
        import comfy.model_management as mm
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass

    log.info("[VDA] Model unloaded")


def offload_to_cpu() -> None:
    """Offload cached model to CPU/offload device without destroying it."""
    if _model is None:
        return
    offload_dev = _get_offload_device()
    try:
        _model.to(offload_dev)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        log.info("[VDA] Model offloaded to %s", offload_dev)
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  Frame I/O helpers
# ---------------------------------------------------------------------------


def _read_video_frames(video_path: str, max_res: int = 1280):
    """Read video frames as numpy array using cv2.

    Returns:
        (frames_array, fps) where frames_array is np.ndarray [N, H, W, 3] RGB.
    """
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

    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if scale < 1.0:
            frame = cv2.resize(frame, (new_w, new_h),
                               interpolation=cv2.INTER_AREA)
        # BGR → RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frames.append(rgb)

    cap.release()

    if not frames:
        raise RuntimeError(f"No frames extracted from video: {video_path}")

    return np.stack(frames, axis=0), fps


def _depth_to_colormap(depth_array: np.ndarray) -> np.ndarray:
    """Convert a single depth frame to a colormap visualization.

    Args:
        depth_array: 2D numpy array [H, W] with depth values.

    Returns:
        RGB numpy array [H, W, 3] uint8 with colormap applied.
    """
    # Normalize to 0-255
    d_min, d_max = depth_array.min(), depth_array.max()
    if d_max - d_min > 1e-6:
        normalized = ((depth_array - d_min) / (d_max - d_min) * 255).astype(np.uint8)
    else:
        normalized = np.zeros_like(depth_array, dtype=np.uint8)

    # Apply inferno colormap (similar to VDA's default)
    colored = cv2.applyColorMap(normalized, cv2.COLORMAP_INFERNO)
    # BGR → RGB
    colored = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
    return colored


def _save_depth_video(depths: np.ndarray, output_path: str,
                      fps: float, colormap: str = "gray") -> None:
    """Save depth frames as an MP4 video.

    Args:
        depths: numpy array [N, H, W] with depth values per frame.
        output_path: path to save the output video.
        fps: frames per second.
        colormap: 'gray' for B&W depth, or a named colormap
                  (inferno, turbo, plasma, magma, viridis, hot, bone).
    """
    # Map colormap names to OpenCV constants
    _COLORMAP_LUT = {
        "inferno": cv2.COLORMAP_INFERNO,
        "turbo": cv2.COLORMAP_TURBO,
        "plasma": cv2.COLORMAP_PLASMA,
        "magma": cv2.COLORMAP_MAGMA,
        "viridis": cv2.COLORMAP_VIRIDIS,
        "hot": cv2.COLORMAP_HOT,
        "bone": cv2.COLORMAP_BONE,
    }
    use_grayscale = colormap == "gray"
    cv_colormap = _COLORMAP_LUT.get(colormap)
    tmp_dir = tempfile.mkdtemp(prefix="vda_")

    try:
        for i, depth in enumerate(depths):
            # Normalize to 0-255
            d_min, d_max = depth.min(), depth.max()
            if d_max - d_min > 1e-6:
                normalized = ((depth - d_min) / (d_max - d_min) * 255).astype(np.uint8)
            else:
                normalized = np.zeros_like(depth, dtype=np.uint8)

            if use_grayscale:
                cv2.imwrite(os.path.join(tmp_dir, f"{i:06d}.png"), normalized)
            elif cv_colormap is not None:
                colored = cv2.applyColorMap(normalized, cv_colormap)
                cv2.imwrite(os.path.join(tmp_dir, f"{i:06d}.png"), colored)
            else:
                # Fallback to grayscale for unknown colormaps
                cv2.imwrite(os.path.join(tmp_dir, f"{i:06d}.png"), normalized)

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
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error("[VDA] ffmpeg failed (exit %d): %s",
                      result.returncode, result.stderr)
            raise RuntimeError(
                f"ffmpeg depth video encoding failed (exit {result.returncode}): "
                f"{result.stderr[:500] if result.stderr else 'no stderr'}"
            )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------


def run_video_depth(
    input_path: str,
    encoder: str = "vits",
    input_size: int = 518,
    max_res: int = 1280,
    colormap: str = "gray",
) -> str:
    """Run Video Depth Anything on a video file.

    Args:
        input_path: Path to input video file.
        encoder: Model variant — 'vits' (Small, ~7 GB), 'vitb' (Base),
                 or 'vitl' (Large, ~24 GB). Default 'vits'.
        input_size: Input resolution for the model (default 518).
        max_res: Maximum video resolution (default 1280).
        colormap: Depth visualization: 'gray' for B&W, or a named
                  colormap (inferno, turbo, plasma, magma, viridis, hot, bone).

    Returns:
        Path to the output depth video file.

    Raises:
        ValueError: If encoder is invalid.
        RuntimeError: If input file cannot be read.
    """
    if encoder not in MODEL_CONFIGS:
        raise ValueError(
            f"Invalid encoder '{encoder}'. "
            f"Must be one of: {list(MODEL_CONFIGS.keys())}"
        )

    if not os.path.isfile(input_path):
        raise RuntimeError(f"Input file not found: {input_path}")

    # ── VRAM-aware auto-adjustment ──────────────────────────────────────
    # VDA processes 32 frames simultaneously through DINOv2 attention.
    # Activation memory (NOT model weights) dominates VRAM usage:
    #   vits @ 518px ≈  6-7 GiB activations
    #   vitb @ 518px ≈ 10-12 GiB activations
    #   vitl @ 518px ≈ 20-24 GiB activations
    if torch.cuda.is_available():
        total_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        free_gb = torch.cuda.mem_get_info()[0] / (1024**3)
        log.info("[VDA] GPU: %.1f GiB total, %.1f GiB free", total_gb, free_gb)

        # Reduce input_size for tight VRAM
        if free_gb < 10 and input_size > 308:
            old_size = input_size
            input_size = 308
            log.info("[VDA] Only %.1f GiB free — reducing input_size %d → %d",
                     free_gb, old_size, input_size)
        elif free_gb < 14 and input_size > 392:
            old_size = input_size
            input_size = 392
            log.info("[VDA] Only %.1f GiB free — reducing input_size %d → %d",
                     free_gb, old_size, input_size)

        # Cap max_res for tight VRAM (reduces frame memory)
        if free_gb < 10 and max_res > 720:
            old_res = max_res
            max_res = 720
            log.info("[VDA] Reducing max_res %d → %d for VRAM safety",
                     old_res, max_res)

    model = _load_model(encoder)
    device = str(_get_device())

    # Read video frames
    log.info("[VDA] Reading video: %s", input_path)
    frames, fps = _read_video_frames(input_path, max_res)
    log.info("[VDA] Read %d frames at %.1f fps", len(frames), fps)

    # Run inference (VDA handles temporal consistency internally)
    log.info("[VDA] Running depth estimation (encoder=%s, input_size=%d)...",
             encoder, input_size)
    try:
        depths, out_fps = model.infer_video_depth(
            frames, fps, input_size=input_size, device=device,
        )
    finally:
        # Offload model to CPU after inference to free VRAM but keep model
        # in RAM for fast re-use (unlike MiniMax/Upscaler which fully cleanup
        # after each run).  _vram_utils.free_for_module() will call cleanup()
        # if another synthesizer needs VRAM later.
        offload_to_cpu()

    # Save output video
    suffix = f"_vda_depth_{encoder}.mp4"
    _fd, output_path = tempfile.mkstemp(suffix=suffix)
    os.close(_fd)
    _save_depth_video(depths, output_path, out_fps, colormap=colormap)

    log.info("[VDA] Output saved to %s (%d frames)", output_path, len(depths))
    return output_path
