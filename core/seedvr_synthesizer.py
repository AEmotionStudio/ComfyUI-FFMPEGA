# coding: utf-8
"""SeedVR2 diffusion-based video/image upscaler integration for FFMPEGA.

Provides AI-powered super-resolution using ByteDance's SeedVR2 one-step
diffusion model.  Supports 3B (FP8) and 7B (GGUF Q4) model variants with
temporal consistency across video frames.

Architecture follows the same synthesizer pattern as upscaler.py / VDA:
- In-process execution with GPU↔CPU pipeline offloading
- Cached model state with explicit load/cleanup
- ``comfy.model_management`` VRAM coordination
- FFmpeg frame extraction / re-encoding

Vendored from: https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler
License: Apache-2.0 (see core/seedvr/LICENSE_SEEDVR2)
"""

import gc
import logging
import os
import shutil
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
#  Model configurations
# ---------------------------------------------------------------------------

SEEDVR_CONFIGS = {
    "seedvr2_3b_fp8": {
        "description": "SeedVR2 3B FP8 — fast diffusion upscaler, great quality",
        "dit_model": "seedvr2_ema_3b_fp8_e4m3fn.safetensors",
        "vae_model": "ema_vae_fp16.safetensors",
        "size": "3B",
        "download_size": "~3 GB",
        "vram": "~8-12 GB",
    },
    "seedvr2_3b_gguf": {
        "description": "SeedVR2 3B GGUF Q4 — lowest VRAM, good quality",
        "dit_model": "seedvr2_ema_3b-Q4_K_M.gguf",
        "vae_model": "ema_vae_fp16.safetensors",
        "size": "3B",
        "download_size": "~2 GB",
        "vram": "~6-8 GB (with BlockSwap)",
    },
    "seedvr2_7b_fp8": {
        "description": "SeedVR2 7B FP8 — highest quality, needs more VRAM",
        "dit_model": "seedvr2_ema_7b_fp8_e4m3fn.safetensors",
        "vae_model": "ema_vae_fp16.safetensors",
        "size": "7B",
        "download_size": "~8 GB",
        "vram": "~16-24 GB",
    },
    "seedvr2_7b_gguf": {
        "description": "SeedVR2 7B GGUF Q4 — highest quality, quantized for lower VRAM",
        "dit_model": "seedvr2_ema_7b-Q4_K_M.gguf",
        "vae_model": "ema_vae_fp16.safetensors",
        "size": "7B",
        "download_size": "~4 GB",
        "vram": "~8-12 GB (with BlockSwap)",
    },
}

# ---------------------------------------------------------------------------
#  Cached model state
# ---------------------------------------------------------------------------

_runner = None
_runner_model: Optional[str] = None
_ctx = None

# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Free GPU VRAM from other FFMPEGA modules before loading SeedVR2."""
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="seedvr_synthesizer")


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
#  Model loading
# ---------------------------------------------------------------------------

def _get_seedvr_dir() -> Path:
    """Get the vendored SeedVR2 source directory."""
    return Path(__file__).resolve().parent / "seedvr"


def _load_model(model_name: str = "seedvr2_3b_fp8", blockswap_blocks: int = 0):
    """Load (or reuse cached) SeedVR2 runner.

    Args:
        model_name: Model variant key from SEEDVR_CONFIGS.
        blockswap_blocks: Number of DiT blocks to offload to CPU (0 = disabled).

    Returns the configured VideoDiffusionInfer runner and generation context.
    """
    global _runner, _runner_model, _ctx

    if _runner is not None and _runner_model == model_name:
        log.info("[SeedVR2] Reusing cached %s runner", model_name)
        return _runner, _ctx

    # Unload previous model if name changed
    if _runner is not None:
        cleanup()

    if model_name not in SEEDVR_CONFIGS:
        raise ValueError(
            f"Invalid SeedVR2 model '{model_name}'. "
            f"Must be one of: {list(SEEDVR_CONFIGS.keys())}"
        )

    cfg = SEEDVR_CONFIGS[model_name]
    log.info("[SeedVR2] Loading %s (%s, %s)...",
             model_name, cfg["size"], cfg["download_size"])

    # Free VRAM from other models BEFORE loading
    _free_vram()

    # Check download permission
    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed  # type: ignore
    require_downloads_allowed("seedvr2")

    # Import vendored SeedVR2 modules
    from .seedvr.utils.debug import Debug
    from .seedvr.utils.downloads import download_weight
    from .seedvr.core.generation_utils import (
        setup_generation_context,
        prepare_runner,
        load_text_embeddings,
        script_directory,
    )

    debug = Debug(enabled=False)  # Use our own logging

    # Download models if needed
    dit_model = cfg["dit_model"]
    vae_model = cfg["vae_model"]

    log.info("[SeedVR2] Checking/downloading models...")
    if not download_weight(dit_model=dit_model, vae_model=vae_model, debug=debug):
        raise RuntimeError(
            f"Failed to download SeedVR2 models. "
            f"DiT: {dit_model}, VAE: {vae_model}. "
            f"Check your internet connection."
        )

    device = _get_device()

    # BlockSwap config — user-controlled via widget (0 = disabled)
    block_swap_config = None
    use_blockswap = blockswap_blocks > 0
    if use_blockswap:
        block_swap_config = {
            "blocks_to_swap": blockswap_blocks,
            "swap_io_components": blockswap_blocks >= 8,
        }
        log.info("[SeedVR2] BlockSwap enabled: %d blocks (user setting)",
                 blockswap_blocks)

    # Determine VAE tiling based on VRAM (automatic — separate concern)
    decode_tiled = False
    encode_tiled = False
    if torch.cuda.is_available():
        try:
            total_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            if total_vram < 16:
                decode_tiled = True
                encode_tiled = True
                log.info("[SeedVR2] VAE tiling enabled (%.1f GiB VRAM)", total_vram)
        except Exception:
            pass

    # BlockSwap requires dit_offload_device != dit_device, so set to CPU
    # when enabled; otherwise None (keeps everything on the inference device).
    dit_offload = torch.device("cpu") if use_blockswap else None
    vae_offload = torch.device("cpu") if (decode_tiled or encode_tiled) else None

    # Setup generation context
    ctx = setup_generation_context(
        dit_device=device,
        vae_device=device,
        dit_offload_device=dit_offload,
        vae_offload_device=vae_offload,
        tensor_offload_device=torch.device("cpu"),
        debug=debug,
    )

    # Prepare runner
    from .seedvr.utils.constants import get_base_cache_dir

    runner, cache_context = prepare_runner(
        dit_model=dit_model,
        vae_model=vae_model,
        model_dir=get_base_cache_dir(),
        debug=debug,
        ctx=ctx,
        dit_cache=False,
        vae_cache=False,
        block_swap_config=block_swap_config,
        encode_tiled=encode_tiled,
        encode_tile_size=(512, 512) if encode_tiled else None,
        encode_tile_overlap=(64, 64) if encode_tiled else None,
        decode_tiled=decode_tiled,
        decode_tile_size=(512, 512) if decode_tiled else None,
        decode_tile_overlap=(64, 64) if decode_tiled else None,
    )

    ctx['cache_context'] = cache_context

    # Load text embeddings
    seedvr_dir = str(_get_seedvr_dir())
    ctx['text_embeds'] = load_text_embeddings(
        seedvr_dir, ctx['dit_device'], ctx['compute_dtype'], debug
    )

    _runner = runner
    _runner_model = model_name
    _ctx = ctx

    # Post-load VRAM flush: clear fragmentation left by pipeline + model load
    # so the subsequent VAE encode has enough contiguous memory (FLUX Klein pattern)
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    if torch.cuda.is_available():
        used = torch.cuda.memory_allocated() / (1024**3)
        log.info("[SeedVR2] %s loaded (%.2f GiB VRAM)", model_name, used)
    else:
        log.info("[SeedVR2] %s loaded on CPU", model_name)

    return _runner, _ctx


def cleanup() -> None:
    """Free GPU memory and clear cached SeedVR2 model."""
    global _runner, _runner_model, _ctx

    if _runner is None:
        return

    try:
        from .seedvr.optimization.memory_manager import complete_cleanup
        from .seedvr.utils.debug import Debug
        debug = Debug(enabled=False)
        complete_cleanup(runner=_runner, debug=debug, dit_cache=False, vae_cache=False)
    except Exception as exc:
        log.debug("[SeedVR2] Cleanup error: %s", exc)

    _runner = None
    _runner_model = None
    _ctx = None

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    try:
        import comfy.model_management as mm
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass

    log.info("[SeedVR2] Model unloaded")


# ---------------------------------------------------------------------------
#  Frame I/O helpers (shared with upscaler.py)
# ---------------------------------------------------------------------------

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


def _frames_to_tensor(frame_paths: list) -> torch.Tensor:
    """Load frames as a [N, H, W, C] float32 tensor in [0, 1] (ComfyUI format)."""
    import cv2

    frames = []
    for fp in frame_paths:
        bgr = cv2.imread(str(fp), cv2.IMREAD_COLOR)
        if bgr is None:
            raise RuntimeError(f"Cannot read frame: {fp}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        arr = rgb.astype(np.float32) / 255.0
        frames.append(torch.from_numpy(arr))
    return torch.stack(frames)  # [N, H, W, 3]


def _tensor_to_frames(tensor: torch.Tensor, out_dir: str) -> list:
    """Save a [N, H, W, C] tensor to PNG frames. Returns list of paths."""
    import cv2

    paths = []
    arr = tensor.cpu().float().numpy()
    arr = (arr.clip(0, 1) * 255).astype(np.uint8)
    for i in range(arr.shape[0]):
        rgb = arr[i]
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        path = os.path.join(out_dir, f"{i + 1:06d}.png")
        cv2.imwrite(path, bgr)
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
#  Core diffusion upscale
# ---------------------------------------------------------------------------

def _flush_vram() -> None:
    """Aggressive inter-phase VRAM flush (FLUX Klein pattern).

    Called between pipeline phases to prevent VRAM fragmentation and
    tensor accumulation.  Adds ~10-50 ms overhead but prevents OOM
    on 8-12 GB cards.
    """
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _run_seedvr2_pipeline(
    image_tensor: torch.Tensor,
    runner,
    ctx: dict,
    resolution: int = 1080,
    batch_size: int = 5,
    seed: int = 42,
    color_correction: str = "lab",
) -> torch.Tensor:
    """Run the SeedVR2 4-phase pipeline on a tensor of frames.

    Uses ``torch.no_grad()`` to prevent autograd graph accumulation and
    aggressive inter-phase VRAM flushing (matching FLUX Klein patterns)
    to minimise OOM risk on consumer GPUs.

    Args:
        image_tensor: [N, H, W, C] float32 in [0, 1]
        runner: VideoDiffusionInfer instance
        ctx: Generation context
        resolution: Target shortest-edge resolution
        batch_size: Frames per batch (must follow 4n+1 rule)
        seed: Random seed
        color_correction: Color correction method

    Returns:
        [N, H', W', C] float32 tensor in [0, 1]
    """
    from .seedvr.core.generation_phases import (
        encode_all_batches,
        upscale_all_batches,
        decode_all_batches,
        postprocess_all_batches,
    )
    from .seedvr.core.generation_utils import compute_generation_info
    from .seedvr.utils.debug import Debug

    debug = Debug(enabled=False)

    # Reset context lists for this run
    ctx['all_latents'] = []
    ctx['all_upscaled_latents'] = []
    ctx['batch_samples'] = []
    ctx['final_video'] = None
    ctx['video_transform'] = None

    # Compute generation info
    image_tensor, gen_info = compute_generation_info(
        ctx=ctx,
        images=image_tensor,
        resolution=resolution,
        batch_size=batch_size,
        seed=seed,
        debug=debug,
    )

    log.info("[SeedVR2] Processing %d frames: %dx%d → %dx%d",
             gen_info['total_frames'],
             gen_info['input_w'], gen_info['input_h'],
             gen_info['true_w'], gen_info['true_h'])

    # Wrap entire pipeline in no_grad to prevent autograd graph accumulation
    # across phases — matching FLUX Klein's per-frame torch.no_grad() pattern.
    with torch.no_grad():
        # Phase 1: Encode (VAE encode → latent space)
        ctx = encode_all_batches(
            runner, ctx=ctx, images=image_tensor, debug=debug,
            batch_size=batch_size, seed=seed,
            resolution=resolution, color_correction=color_correction,
        )
        # Release input tensor — no longer needed after encoding
        del image_tensor
        _flush_vram()

        # Phase 2: Upscale (DiT diffusion in latent space)
        ctx = upscale_all_batches(
            runner, ctx=ctx, debug=debug, seed=seed,
        )
        # Release encoded latents — DiT produced upscaled versions
        ctx['all_latents'] = []
        _flush_vram()

        # Phase 3: Decode (VAE decode → pixel space)
        ctx = decode_all_batches(
            runner, ctx=ctx, debug=debug,
        )
        # Release upscaled latents — decoded to pixels
        ctx['all_upscaled_latents'] = []
        _flush_vram()

        # Phase 4: Post-processing (color correction, trimming)
        ctx = postprocess_all_batches(
            ctx=ctx, debug=debug,
            color_correction=color_correction,
            batch_size=batch_size,
        )
        # Release batch samples — final_video is assembled
        ctx['batch_samples'] = []
        _flush_vram()

    result = ctx['final_video']
    if result is None:
        raise RuntimeError("SeedVR2 pipeline returned no output")

    # Ensure float32 CPU — move off GPU before returning
    if torch.is_tensor(result):
        result = result.cpu().float()

    # Clear context refs to allow GC of any remaining GPU tensors
    ctx['final_video'] = None
    ctx['video_transform'] = None
    _flush_vram()

    return result


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def upscale_image(
    input_path: str,
    model_name: str = "seedvr2_3b_fp8",
    resolution: int = 1080,
    seed: int = 42,
    color_correction: str = "lab",
    blockswap_blocks: int = 0,
    **kwargs,
) -> str:
    """Upscale a single image using SeedVR2 diffusion.

    Args:
        input_path: Path to source image.
        model_name: SeedVR2 model variant (see SEEDVR_CONFIGS).
        resolution: Target shortest-edge resolution.
        seed: Random seed for reproducibility.
        color_correction: Color correction method.
        blockswap_blocks: DiT blocks to offload to CPU (0 = disabled).

    Returns:
        Path to the upscaled image.
    """
    if not os.path.isfile(input_path):
        raise RuntimeError(f"Input file not found: {input_path}")

    log.info("[SeedVR2] Upscaling image: %s (model=%s, resolution=%d)",
             input_path, model_name, resolution)

    runner, ctx = _load_model(model_name, blockswap_blocks=blockswap_blocks)

    # Load single image as 1-frame tensor
    image_tensor = _frames_to_tensor([input_path])

    # Run pipeline with batch_size=1 (single image)
    result = _run_seedvr2_pipeline(
        image_tensor, runner, ctx,
        resolution=resolution,
        batch_size=1,
        seed=seed,
        color_correction=color_correction,
    )

    # Save output
    ext = Path(input_path).suffix or ".png"
    _fd, output_path = tempfile.mkstemp(suffix=f"_seedvr2{ext}", prefix="ffmpega_")
    os.close(_fd)

    out_dir = tempfile.mkdtemp(prefix="seedvr_out_")
    try:
        paths = _tensor_to_frames(result, out_dir)
        if paths:
            shutil.copy2(paths[0], output_path)
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        del result

    # Unload model after processing
    cleanup()

    log.info("[SeedVR2] Image upscaled: %s", output_path)
    return output_path


def upscale_video(
    input_path: str,
    model_name: str = "seedvr2_3b_fp8",
    resolution: int = 1080,
    batch_size: int = 5,
    seed: int = 42,
    color_correction: str = "lab",
    blockswap_blocks: int = 0,
    **kwargs,
) -> str:
    """Upscale a video using SeedVR2 diffusion.

    Args:
        input_path: Path to source video.
        model_name: SeedVR2 model variant (see SEEDVR_CONFIGS).
        resolution: Target shortest-edge resolution.
        batch_size: Frames per batch (follows 4n+1 rule: 1, 5, 9, 13...).
        seed: Random seed for reproducibility.
        color_correction: Color correction method.
        blockswap_blocks: DiT blocks to offload to CPU (0 = disabled).

    Returns:
        Path to the upscaled video.
    """
    if not os.path.isfile(input_path):
        raise RuntimeError(f"Input file not found: {input_path}")

    log.info("[SeedVR2] Upscaling video: %s (model=%s, batch=%d, resolution=%d)",
             input_path, model_name, batch_size, resolution)

    runner, ctx = _load_model(model_name, blockswap_blocks=blockswap_blocks)

    ffmpeg = _get_ffmpeg_bin()
    fps = _get_video_fps(input_path)
    frames_dir = tempfile.mkdtemp(prefix="seedvr_in_")
    out_dir = tempfile.mkdtemp(prefix="seedvr_out_")

    try:
        # Extract frames
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
        log.info("[SeedVR2] Extracted %d frames at %.1f FPS", total, fps)

        # Load all frames as tensor
        image_tensor = _frames_to_tensor([str(f) for f in frame_files])

        # Ensure batch_size follows 4n+1 rule
        if batch_size % 4 != 1:
            batch_size = max(1, ((batch_size - 1) // 4) * 4 + 1)
            log.info("[SeedVR2] Adjusted batch_size to %d (4n+1 rule)", batch_size)

        # Run SeedVR2 pipeline
        result = _run_seedvr2_pipeline(
            image_tensor, runner, ctx,
            resolution=resolution,
            batch_size=batch_size,
            seed=seed,
            color_correction=color_correction,
        )
        del image_tensor

        # Save upscaled frames
        _tensor_to_frames(result, out_dir)
        del result

        # Encode video from upscaled frames
        _fd, output_path = tempfile.mkstemp(
            suffix=f"_seedvr2_{model_name}.mp4", prefix="ffmpega_"
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
                log.info("[SeedVR2] Audio muxed from original")
            else:
                try:
                    os.remove(muxed_path)
                except OSError:
                    pass
                log.warning("[SeedVR2] Audio mux failed — output is video-only")

    finally:
        for d in (frames_dir, out_dir):
            try:
                shutil.rmtree(d)
            except OSError:
                pass
        cleanup()

    log.info("[SeedVR2] Video upscaled: %s (%d frames)", output_path, total)
    return output_path
