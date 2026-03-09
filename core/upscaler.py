# coding: utf-8
"""AI Upscaler integration for FFMPEGA.

Provides AI-powered super-resolution upscaling using spandrel as a
universal model loader.  Supports Real-ESRGAN, Real-HAT-GAN (SOTA),
DAT-2, SwinIR, and anime-optimized variants.

Architecture follows the VDA/Marigold synthesizer pattern:
- In-process execution with GPU↔CPU pipeline offloading
- Cached model state with explicit load/cleanup
- ``comfy.model_management`` VRAM coordination
- Tiled inference with overlap blending for large images

License:
    BSD-3-Clause (Real-ESRGAN), Apache 2.0 (SwinIR),
    see upstream repos for HAT/DAT weights.
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

# ---------------------------------------------------------------------------
#  Model configurations
# ---------------------------------------------------------------------------

MODEL_CONFIGS = {
    "realesrgan_x4plus": {
        "description": "Real-ESRGAN x4+ — fast, general-purpose GAN upscaler",
        "upstream_repo": "xinntao/Real-ESRGAN",
        "mirror_repo": "AEmotionStudio/ai-upscale-models",
        "filename": "RealESRGAN_x4plus.pth",
        "scale": 4,
        "size": "~64 MB",
        "vram": "~2 GB",
    },
    "realesrgan_x4_anime": {
        "description": "Real-ESRGAN x4+ anime — optimized for anime/cartoon",
        "upstream_repo": "xinntao/Real-ESRGAN",
        "mirror_repo": "AEmotionStudio/ai-upscale-models",
        "filename": "RealESRGAN_x4plus_anime_6B.pth",
        "scale": 4,
        "size": "~17 MB",
        "vram": "~1 GB",
    },
    "hat_x4": {
        "description": "Real-HAT-GAN x4 — SOTA quality, hybrid attention transformer",
        "upstream_repo": "XPixelGroup/HAT",
        "mirror_repo": "AEmotionStudio/ai-upscale-models",
        "filename": "Real_HAT_GAN_SRx4.pth",
        "scale": 4,
        "size": "~170 MB",
        "vram": "~4 GB",
    },
    "dat_x4": {
        "description": "DAT-2 x4 — dual aggregation transformer, high quality",
        "upstream_repo": "zhengchen1999/DAT",
        "mirror_repo": "AEmotionStudio/ai-upscale-models",
        "filename": "DAT_2_x4.pth",
        "scale": 4,
        "size": "~134 MB",
        "vram": "~3 GB",
    },
    "swinir_x4": {
        "description": "SwinIR x4 — classical SR, clean image specialist",
        "upstream_repo": "JingyunLiang/SwinIR",
        "mirror_repo": "AEmotionStudio/ai-upscale-models",
        "filename": "003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth",
        "scale": 4,
        "size": "~48 MB",
        "vram": "~3 GB",
    },
}

# ---------------------------------------------------------------------------
#  Cached model state
# ---------------------------------------------------------------------------

_model: Optional[object] = None
_model_name: Optional[str] = None


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Aggressively free GPU VRAM before loading upscaler model.

    Delegates to the shared ``_vram_utils.free_for_module``.
    """
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="upscaler")


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
#  Model download and loading
# ---------------------------------------------------------------------------

def _get_model_dir() -> Path:
    """Get or create the upscaler model directory."""
    # 1. Environment variable override
    env_dir = os.environ.get("FFMPEGA_UPSCALE_MODEL_DIR")
    if env_dir:
        d = Path(env_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # 2. ComfyUI standard path
    ext_dir = Path(__file__).resolve().parent.parent
    comfyui_dir = ext_dir.parent.parent
    models_dir = comfyui_dir / "models" / "upscale_models"
    if models_dir.exists():
        return models_dir
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


def _download_model(model_name: str) -> str:
    """Download upscaler model weights from HuggingFace, mirror first.

    Returns:
        Local path to the downloaded checkpoint file.
    """
    cfg = MODEL_CONFIGS[model_name]
    model_dir = _get_model_dir()
    local_path = model_dir / cfg["filename"]

    # Already downloaded
    if local_path.is_file() and local_path.stat().st_size > 1024:
        log.info("[Upscaler] Model already exists: %s", local_path)
        return str(local_path)

    # Check download permission
    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed  # type: ignore
    require_downloads_allowed("ai_upscale")

    from huggingface_hub import hf_hub_download

    # Try AEmotionStudio mirror first
    try:
        log.info("[Upscaler] Downloading %s from %s...",
                 cfg["filename"], cfg["mirror_repo"])
        path = hf_hub_download(
            repo_id=cfg["mirror_repo"],
            filename=cfg["filename"],
            local_dir=str(model_dir),
        )
        log.info("[Upscaler] Download complete: %s", path)
        return path
    except Exception as exc:
        log.debug("[Upscaler] Mirror download failed: %s", exc)

    raise RuntimeError(
        f"Failed to download upscaler model '{model_name}' "
        f"({cfg['filename']}) from {cfg['mirror_repo']}. "
        f"Check your internet connection or download manually from "
        f"https://huggingface.co/{cfg['mirror_repo']}"
    )


def _load_model(model_name: str = "realesrgan_x4plus"):
    """Load (or reuse cached) upscaler model via spandrel.

    Caches the model so consecutive runs with the same model skip loading.
    If the model changes, the old model is unloaded first.

    Returns:
        spandrel ModelDescriptor with .model and .scale attributes.
    """
    global _model, _model_name

    if _model is not None and _model_name == model_name:
        log.info("[Upscaler] Reusing cached %s model", model_name)
        device = _get_device()
        try:
            _model.to(device)
        except Exception:
            pass
        return _model

    # Unload previous model if name changed
    if _model is not None:
        cleanup()

    if model_name not in MODEL_CONFIGS:
        raise ValueError(
            f"Invalid model '{model_name}'. "
            f"Must be one of: {list(MODEL_CONFIGS.keys())}"
        )

    cfg = MODEL_CONFIGS[model_name]
    log.info("[Upscaler] Loading %s (%s)...", model_name, cfg["size"])

    # Free VRAM from other models BEFORE loading
    _free_vram()

    # Download checkpoint
    ckpt_path = _download_model(model_name)

    # Load via spandrel — auto-detects architecture
    try:
        import spandrel
    except ImportError:
        raise ImportError(
            "spandrel is required for AI upscaling. "
            "It should already be installed as part of ComfyUI."
        )

    model_desc = spandrel.ModelLoader().load_from_file(ckpt_path)

    # Move to GPU with half precision for VRAM efficiency
    device = _get_device()
    model_desc = model_desc.to(device)
    if device.type == "cuda":
        model_desc.model.half()

    model_desc.model.eval()

    _model = model_desc
    _model_name = model_name

    if torch.cuda.is_available():
        used = torch.cuda.memory_allocated() / (1024**3)
        log.info("[Upscaler] %s loaded (%.2f GiB VRAM)", model_name, used)
    else:
        log.info("[Upscaler] %s loaded on CPU", model_name)

    return _model


def cleanup() -> None:
    """Free GPU memory and clear cached upscaler model."""
    global _model, _model_name

    if _model is None:
        return

    model_desc = _model
    _model = None
    _model_name = None

    try:
        model_desc.model.cpu()
    except Exception:
        pass
    del model_desc

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    try:
        import comfy.model_management as mm
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass

    log.info("[Upscaler] Model unloaded")


# ---------------------------------------------------------------------------
#  Tiled inference
# ---------------------------------------------------------------------------

def _upscale_tensor(model_desc, img_tensor: torch.Tensor,
                    tile_size: int = 512) -> torch.Tensor:
    """Upscale an image tensor using tiled inference with overlap blending.

    Args:
        model_desc: spandrel ModelDescriptor
        img_tensor: [1, C, H, W] float32 tensor in [0, 1]
        tile_size: size of each tile (default 512)

    Returns:
        [1, C, H*scale, W*scale] float32 tensor in [0, 1]
    """
    _, c, h, w = img_tensor.shape
    scale = model_desc.scale

    # Auto-reduce tile_size if total VRAM usage would exceed available memory.
    # Total cost = fixed output+weight tensors + per-tile inference peak.
    # We can only reduce per-tile cost by shrinking tile_size.
    if torch.cuda.is_available() and img_tensor.device.type == "cuda":
        try:
            free_mem = torch.cuda.mem_get_info()[0]
            # Fixed cost: output accumulation (1,C,H*s,W*s) + weight (1,1,H*s,W*s)
            out_bytes = (c + 1) * h * scale * w * scale * 4
            budget = free_mem * 0.8 - out_bytes
            # Per-tile peak: input tile + output tile, both in float16 (2 bytes)
            # with ~3x overhead for intermediate activations.
            # Halve tile_size until per-tile peak fits the budget.
            while budget > 0 and tile_size > 128:
                tile_peak = 3 * 2 * c * (tile_size * scale) ** 2 * 2
                if tile_peak <= budget:
                    break
                tile_size = max(128, tile_size // 2)
                log.info("[Upscaler] Auto-reduced tile_size to %d (free=%.1f GiB, "
                         "budget=%.1f GiB, tile_peak=%.1f GiB)", tile_size,
                         free_mem / (1024**3), budget / (1024**3),
                         tile_peak / (1024**3))
        except Exception:
            pass

    # Small enough for single-pass — avoid tiling overhead
    if h <= tile_size and w <= tile_size:
        with torch.no_grad():
            return model_desc(img_tensor)

    # Tiled processing with overlap
    overlap = 32
    stride = tile_size - overlap
    out_h = h * scale
    out_w = w * scale
    out_overlap = overlap * scale
    out_stride = stride * scale
    out_tile = tile_size * scale

    output = torch.zeros(1, c, out_h, out_w, device=img_tensor.device,
                         dtype=img_tensor.dtype)
    weight = torch.zeros(1, 1, out_h, out_w, device=img_tensor.device,
                         dtype=img_tensor.dtype)

    # Create blending weight mask (linear ramp on edges)
    tile_weight = torch.ones(1, 1, out_tile, out_tile,
                             device=img_tensor.device, dtype=img_tensor.dtype)
    ramp = out_overlap
    for i in range(ramp):
        v = (i + 1) / ramp
        tile_weight[:, :, i, :] *= v      # top edge
        tile_weight[:, :, -1-i, :] *= v    # bottom edge
        tile_weight[:, :, :, i] *= v       # left edge
        tile_weight[:, :, :, -1-i] *= v    # right edge

    y_tiles = list(range(0, max(h - tile_size, 0) + 1, stride))
    if y_tiles[-1] + tile_size < h:
        y_tiles.append(h - tile_size)
    x_tiles = list(range(0, max(w - tile_size, 0) + 1, stride))
    if x_tiles[-1] + tile_size < w:
        x_tiles.append(w - tile_size)

    total_tiles = len(y_tiles) * len(x_tiles)
    tile_idx = 0

    for y in y_tiles:
        for x in x_tiles:
            tile_idx += 1
            if tile_idx % 10 == 1:
                log.info("[Upscaler] Tile %d/%d", tile_idx, total_tiles)

            # Extract tile
            tile = img_tensor[:, :, y:y+tile_size, x:x+tile_size]

            # Pad if tile is smaller than tile_size (edges)
            pad_h = tile_size - tile.shape[2]
            pad_w = tile_size - tile.shape[3]
            if pad_h > 0 or pad_w > 0:
                tile = torch.nn.functional.pad(tile, (0, pad_w, 0, pad_h),
                                               mode="reflect")

            # Upscale tile
            with torch.no_grad():
                sr_tile = model_desc(tile)

            # Remove padding from output
            if pad_h > 0:
                sr_tile = sr_tile[:, :, :sr_tile.shape[2]-pad_h*scale, :]
            if pad_w > 0:
                sr_tile = sr_tile[:, :, :, :sr_tile.shape[3]-pad_w*scale]

            # Determine output region
            oy = y * scale
            ox = x * scale
            oh = sr_tile.shape[2]
            ow = sr_tile.shape[3]

            # Adjust weight mask for edge tiles
            tw = tile_weight[:, :, :oh, :ow]

            output[:, :, oy:oy+oh, ox:ox+ow] += sr_tile * tw
            weight[:, :, oy:oy+oh, ox:ox+ow] += tw

            del tile, sr_tile

    # Normalize by weight
    output = output / weight.clamp(min=1e-6)

    return output.clamp(0, 1)


# ---------------------------------------------------------------------------
#  Frame I/O helpers
# ---------------------------------------------------------------------------

def _image_to_tensor(image_path: str, device: torch.device) -> torch.Tensor:
    """Load an image as a [1, 3, H, W] float32 tensor in [0, 1].

    Kept as float32 — the model is loaded in half precision and
    spandrel / torch autocast handles the conversion during inference.
    """
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)
    return tensor.to(device)


def _tensor_to_image(tensor: torch.Tensor, output_path: str) -> None:
    """Save a [1, 3, H, W] tensor to an image file."""
    from PIL import Image

    arr = tensor.squeeze(0).permute(1, 2, 0).cpu().float().numpy()
    arr = (arr.clip(0, 1) * 255).astype(np.uint8)
    Image.fromarray(arr).save(output_path)


def _get_ffmpeg_bin() -> str:
    """Get the ffmpeg binary path."""
    try:
        from .bin_paths import get_ffmpeg_bin
    except ImportError:
        from core.bin_paths import get_ffmpeg_bin  # type: ignore
    return get_ffmpeg_bin()


def _get_ffprobe_bin() -> str:
    """Get the ffprobe binary path."""
    try:
        from .bin_paths import get_ffprobe_bin
    except ImportError:
        from core.bin_paths import get_ffprobe_bin  # type: ignore
    return get_ffprobe_bin()


def _get_video_fps(video_path: str) -> float:
    """Get video FPS using ffprobe."""
    try:
        result = subprocess.run(
            [
                _get_ffprobe_bin(), "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "csv=p=0",
                video_path,
            ],
            capture_output=True, text=True, check=True,
        )
        rate = result.stdout.strip()
        if "/" in rate:
            num, den = rate.split("/")
            return float(num) / float(den)
        return float(rate)
    except Exception:
        return 24.0


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def upscale_image(
    input_path: str,
    model_name: str = "realesrgan_x4plus",
    scale_factor: int = 4,
    tile_size: int = 512,
) -> str:
    """Upscale a single image using AI super-resolution.

    Args:
        input_path: Path to source image.
        model_name: Model to use (see MODEL_CONFIGS).
        scale_factor: Output scale factor (2 or 4).
        tile_size: Tile size for processing (256-1024).

    Returns:
        Path to the upscaled image.
    """
    from PIL import Image

    if not os.path.isfile(input_path):
        raise RuntimeError(f"Input file not found: {input_path}")

    log.info("[Upscaler] Upscaling image: %s (model=%s, scale=%dx)",
             input_path, model_name, scale_factor)

    model_desc = _load_model(model_name)
    device = _get_device()

    # Load and upscale
    img_tensor = _image_to_tensor(input_path, device)
    sr_tensor = _upscale_tensor(model_desc, img_tensor, tile_size=tile_size)
    del img_tensor

    # If user wants 2x but model does 4x, downscale
    if scale_factor == 2 and model_desc.scale == 4:
        _, _, sh, sw = sr_tensor.shape
        sr_tensor = torch.nn.functional.interpolate(
            sr_tensor, size=(sh // 2, sw // 2),
            mode="bicubic", align_corners=False,
        ).clamp(0, 1)

    # Save output
    ext = Path(input_path).suffix or ".png"
    _fd, output_path = tempfile.mkstemp(suffix=f"_upscaled{ext}", prefix="ffmpega_")
    os.close(_fd)
    _tensor_to_image(sr_tensor, output_path)
    del sr_tensor

    # Unload model after processing — matches upscale_video / VDA patterns
    cleanup()

    log.info("[Upscaler] Image upscaled: %s", output_path)
    return output_path


def upscale_video(
    input_path: str,
    model_name: str = "realesrgan_x4plus",
    scale_factor: int = 4,
    tile_size: int = 512,
) -> str:
    """Upscale a video using AI super-resolution (per-frame).

    Args:
        input_path: Path to source video.
        model_name: Model to use (see MODEL_CONFIGS).
        scale_factor: Output scale factor (2 or 4).
        tile_size: Tile size for processing (256-1024).

    Returns:
        Path to the upscaled video.
    """
    if not os.path.isfile(input_path):
        raise RuntimeError(f"Input file not found: {input_path}")

    log.info("[Upscaler] Upscaling video: %s (model=%s, scale=%dx)",
             input_path, model_name, scale_factor)

    model_desc = _load_model(model_name)
    device = _get_device()

    # Extract frames
    frames_dir = tempfile.mkdtemp(prefix="upscale_in_")
    out_dir = tempfile.mkdtemp(prefix="upscale_out_")
    ffmpeg = _get_ffmpeg_bin()
    fps = _get_video_fps(input_path)

    try:
        subprocess.run(
            [ffmpeg, "-i", input_path, "-q:v", "2",
             os.path.join(frames_dir, "%06d.png")],
            capture_output=True, check=True,
        )

        frame_files = sorted(Path(frames_dir).glob("*.png"))
        total = len(frame_files)
        if total == 0:
            raise RuntimeError(f"No frames extracted from: {input_path}")
        log.info("[Upscaler] Extracted %d frames at %.1f FPS", total, fps)

        # Per-frame upscaling
        for i, frame_path in enumerate(frame_files):
            if i % 10 == 0:
                log.info("[Upscaler] Frame %d/%d", i + 1, total)

            img_tensor = _image_to_tensor(str(frame_path), device)
            sr_tensor = _upscale_tensor(model_desc, img_tensor,
                                        tile_size=tile_size)
            del img_tensor

            # Downscale for 2x output
            if scale_factor == 2 and model_desc.scale == 4:
                _, _, sh, sw = sr_tensor.shape
                sr_tensor = torch.nn.functional.interpolate(
                    sr_tensor, size=(sh // 2, sw // 2),
                    mode="bicubic", align_corners=False,
                ).clamp(0, 1)

            out_frame = os.path.join(out_dir, f"{i:06d}.png")
            _tensor_to_image(sr_tensor, out_frame)
            del sr_tensor

            # Per-frame VRAM cleanup
            if i % 5 == 0:
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        # Encode video from upscaled frames
        _fd, output_path = tempfile.mkstemp(
            suffix=f"_upscaled_{model_name}.mp4", prefix="ffmpega_"
        )
        os.close(_fd)
        # Use integer framerate for ffmpeg compatibility
        fps_str = str(int(round(fps))) if fps == int(fps) else f"{fps:.2f}"
        encode_cmd = [
            ffmpeg, "-y",
            "-framerate", fps_str,
            "-start_number", "0",
            "-i", os.path.join(out_dir, "%06d.png"),
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        result = subprocess.run(encode_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg encoding failed: {result.stderr[:500]}"
            )

        # Mux audio from original input (upscaling drops audio)
        ffprobe = _get_ffprobe_bin()
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
            if mux_result.returncode == 0 and os.path.isfile(muxed_path):
                os.replace(muxed_path, output_path)
                log.info("[Upscaler] Audio muxed from original")
            else:
                # Clean up failed mux attempt, keep video-only output
                try:
                    os.remove(muxed_path)
                except OSError:
                    pass
                log.warning("[Upscaler] Audio mux failed — output is video-only")

    finally:
        import shutil
        for d in (frames_dir, out_dir):
            try:
                shutil.rmtree(d)
            except OSError:
                pass

        # Unload model after processing — matches VDA/Marigold patterns
        # where models are fully cleaned up after use to free VRAM.
        cleanup()

    log.info("[Upscaler] Video upscaled: %s (%d frames)", output_path, total)
    return output_path
