"""Stable Video Infinity 2.0 Pro — infinite-length video generation.

Vendors the SVI 2.0 Pro algorithm (ICLR 2026 Oral) for ComfyUI-FFMPEGA.
Generates arbitrarily long videos by iteratively producing 81-frame clips
using Wan 2.2 I2V-A14B with two specialized LoRAs (high/low noise).

Algorithm overview (SVI 2.0 Pro):
  1. Encode anchor frame → anchor_latent = VAE.encode(first_frame)
  2. For each clip:
     a. Build image conditioning:
        - First clip: y = concat([anchor_latent, zero_padding])
        - Subsequent: y = concat([anchor_latent, motion_latent, zero_padding])
     b. Denoise with high-noise UNet+LoRA (timesteps 0→boundary)
     c. Switch to low-noise UNet+LoRA (boundary→end)
     d. Save prev_last_latent for next clip
     e. Decode frames via VAE
  3. Stitch clips with configurable overlap
  4. Encode final video via FFmpeg

Model: Wan 2.2 I2V-A14B + SVI LoRAs (Apache 2.0)
Paper: https://github.com/vita-epfl/Stable-Video-Infinity
"""

from __future__ import annotations

import gc
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image

try:
    from .sanitize import validate_output_file_path
except ImportError:
    from core.sanitize import validate_output_file_path  # type: ignore

try:
    from .bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin
except ImportError:
    from core.bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin  # type: ignore

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

_HF_REPO = "vita-video-gen/svi-model"
_HF_LORA_REPO = "AEmotionStudio/svi-loras"
_MODEL_DIR_NAME = "svi"

# LoRA file names (SVI 2.0 Pro)
_LORA_HIGH_PRO = "version-2.0/SVI_Wan2.2-I2V-A14B_high_noise_lora_v2.0_pro.safetensors"
_LORA_LOW_PRO = "version-2.0/SVI_Wan2.2-I2V-A14B_low_noise_lora_v2.0_pro.safetensors"

# LoRA file names (SVI 2.0 Standard)
_LORA_HIGH_STD = "version-2.0/SVI_Wan2.2-I2V-A14B_high_noise_lora_v2.0.safetensors"
_LORA_LOW_STD = "version-2.0/SVI_Wan2.2-I2V-A14B_low_noise_lora_v2.0.safetensors"

# Default generation parameters
_FRAMES_PER_CLIP = 81
_DEFAULT_HEIGHT = 480
_DEFAULT_WIDTH = 832
_DEFAULT_FPS = 15
_DEFAULT_CFG_SCALE = 4.0
_DEFAULT_NUM_CLIPS = 10
_DEFAULT_OVERLAP_FRAMES = 5
_DEFAULT_NUM_MOTION_LATENT = 1
_DEFAULT_SEED_MULTIPLIER = 42
_DEFAULT_SWITCH_BOUNDARY = 0.875
_DEFAULT_NUM_STEPS = 50

# Negative prompt (from SVI reference implementation)
_NEGATIVE_PROMPT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，"
    "整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，"
    "画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，"
    "手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)

# Cached state
_pipeline_loaded = False
_wan_models = None


# ---------------------------------------------------------------------------
#  Model directory and downloading
# ---------------------------------------------------------------------------

def _get_model_dir() -> Path:
    """Get or create the SVI model directory.

    Checks (in order):
    1. FFMPEGA_SVI_MODEL_DIR env var
    2. ComfyUI/models/svi/ (standard ComfyUI convention)
    3. Extension's own models/svi/ (fallback)
    """
    env_dir = os.environ.get("FFMPEGA_SVI_MODEL_DIR")
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


def _resolve_lora_path(lora_filename: str) -> Path:
    """Resolve a LoRA filename to an absolute path.

    Checks ComfyUI loras directory first, then SVI model directory.
    """
    try:
        import folder_paths  # type: ignore[import-not-found]
        full = folder_paths.get_full_path("loras", lora_filename)
        if full and os.path.isfile(full):
            return Path(full)
    except Exception:
        pass

    # Check SVI model directory
    svi_path = _get_model_dir() / "version-2.0" / lora_filename
    if svi_path.is_file():
        return svi_path

    return svi_path  # Return expected path even if not found yet


def _download_lora(lora_filename: str) -> Path:
    """Download a single SVI LoRA file from HuggingFace if not present."""
    path = _resolve_lora_path(lora_filename)
    if path.is_file():
        return path

    try:
        from . import model_manager as _mm
    except ImportError:
        from core import model_manager as _mm  # type: ignore

    _mm.require_downloads_allowed("svi")

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise ImportError(
            "huggingface_hub is required to download SVI LoRAs. "
            "Install with: pip install huggingface_hub"
        )

    model_dir = _get_model_dir()
    hf_filename = f"version-2.0/{lora_filename}"

    log.info("Downloading SVI LoRA %s from %s...", lora_filename, _HF_LORA_REPO)
    path.parent.mkdir(parents=True, exist_ok=True)
    _mm.download_with_progress(
        "svi",
        lambda: hf_hub_download(
            repo_id=_HF_LORA_REPO,
            filename=hf_filename,
            local_dir=str(model_dir),
        ),
        extra=f"LoRA: {lora_filename}",
    )
    log.info("SVI LoRA %s downloaded successfully", lora_filename)
    return _resolve_lora_path(lora_filename)


# ---------------------------------------------------------------------------
#  Extra LoRA resolution
# ---------------------------------------------------------------------------

def _resolve_extra_lora(lora_filename: str) -> Optional[str]:
    """Resolve an extra LoRA filename to a full path via ComfyUI folder_paths."""
    try:
        import folder_paths  # type: ignore[import-not-found]
        full = folder_paths.get_full_path("loras", lora_filename)
        if full and os.path.isfile(full):
            return full
    except Exception:
        pass
    log.warning("Extra LoRA not found: %s", lora_filename)
    return None


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Free all GPU VRAM before loading SVI models."""
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="svi_synthesizer")


def cleanup() -> None:
    """Free GPU memory and clear cached models."""
    global _pipeline_loaded, _wan_models
    _pipeline_loaded = False
    _wan_models = None
    gc.collect()
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.unload_all_models()
        mm.soft_empty_cache()
        if torch.cuda.is_available():
            mm.free_memory(mm.get_free_memory(mm.get_torch_device()), mm.get_torch_device())
    except (ImportError, AttributeError, Exception) as e:
        log.debug("SVI cleanup mm error (non-fatal): %s", e)
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    gc.collect()
    log.info("SVI models unloaded")


# ---------------------------------------------------------------------------
#  ComfyUI Model Loading
# ---------------------------------------------------------------------------

def _load_wan_models(
    variant: str = "pro",
    model_path_high: str = "auto",
    model_path_low: str = "auto",
    lora_high: str = "SVI_Wan2.2-I2V-A14B_high_noise_lora_v2.0_pro.safetensors",
    lora_low: str = "SVI_Wan2.2-I2V-A14B_low_noise_lora_v2.0_pro.safetensors",
    extra_lora_high: Optional[str] = None,
    extra_lora_low: Optional[str] = None,
):
    """Load Wan 2.2 I2V-A14B models with SVI LoRAs via ComfyUI infrastructure.

    Args:
        variant: "pro" or "standard"
        model_path_high: "auto" or path/filename of the high noise Wan 2.2 I2V model
        model_path_low: "auto" or path/filename of the low noise Wan 2.2 I2V model
        lora_high: Filename of the high-noise SVI LoRA
        lora_low: Filename of the low-noise SVI LoRA
        extra_lora_high: Optional filename of an additional LoRA for the high-noise model
        extra_lora_low: Optional filename of an additional LoRA for the low-noise model

    Returns a dict with the loaded pipeline components.
    """
    global _pipeline_loaded, _wan_models

    if _pipeline_loaded and _wan_models is not None:
        return _wan_models

    # Download LoRAs if not present
    high_lora_path = _download_lora(lora_high)
    low_lora_path = _download_lora(lora_low)
    _free_vram()

    log.info(
        "Loading SVI pipeline (variant=%s, high_lora=%s, low_lora=%s)",
        variant, high_lora_path.name, low_lora_path.name,
    )

    try:
        import comfy.sd  # type: ignore[import-not-found]
        import comfy.model_management as mm  # type: ignore[import-not-found]
        import comfy.utils  # type: ignore[import-not-found]
    except ImportError:
        raise ImportError(
            "ComfyUI is required for SVI model loading. "
            "Ensure you're running within ComfyUI."
        )

    # Load LoRA weights as state dicts for later application
    high_lora_sd = comfy.utils.load_torch_file(str(high_lora_path))
    low_lora_sd = comfy.utils.load_torch_file(str(low_lora_path))

    _wan_models = {
        "high_lora_sd": high_lora_sd,
        "low_lora_sd": low_lora_sd,
        "high_lora_path": str(high_lora_path),
        "low_lora_path": str(low_lora_path),
    }
    _pipeline_loaded = True
    log.info("SVI LoRAs loaded successfully")
    return _wan_models


# ---------------------------------------------------------------------------
#  Video encoding helpers
# ---------------------------------------------------------------------------

def _encode_video_from_frames(
    frames: list[Image.Image],
    output_path: str,
    fps: int = 15,
    crf: int = 18,
) -> str:
    """Encode a list of PIL Image frames to an MP4 video.

    Args:
        frames: List of PIL.Image.Image frames
        output_path: Output video file path
        fps: Frames per second
        crf: Quality (0=lossless, 51=worst)

    Returns:
        Path to the encoded video file
    """
    tmpdir = tempfile.mkdtemp(prefix="svi_frames_")
    try:
        for i, frame in enumerate(frames):
            frame.save(os.path.join(tmpdir, f"{i:06d}.png"))

        ffmpeg = _get_ffmpeg_bin()
        cmd = [
            ffmpeg, "-y",
            "-framerate", str(fps),
            "-start_number", "0",
            "-i", os.path.join(tmpdir, "%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-color_range", "pc",
            "-crf", str(crf),
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg encoding failed:\n{proc.stderr[-500:]}")
    finally:
        import shutil
        try:
            shutil.rmtree(tmpdir)
        except OSError:
            pass

    return output_path


# ---------------------------------------------------------------------------
#  Core SVI 2.0 Pro Generation
# ---------------------------------------------------------------------------

def _register_blockswap(model_patcher, blocks_to_swap: int) -> None:
    """Keep ~blocks_to_swap transformer blocks' worth of DiT weights off-GPU."""
    try:
        from .vram_utils import register_blockswap
    except ImportError:
        from core.vram_utils import register_blockswap  # type: ignore

    register_blockswap(
        model_patcher, blocks_to_swap, key="svi_blockswap", label="SVI",
    )


def generate_infinite_video(
    ref_image_path: str,
    prompts: list[str],
    output_path: Optional[str] = None,
    # Generation parameters
    num_clips: int = _DEFAULT_NUM_CLIPS,
    height: int = _DEFAULT_HEIGHT,
    width: int = _DEFAULT_WIDTH,
    fps: int = _DEFAULT_FPS,
    cfg_scale: float = _DEFAULT_CFG_SCALE,
    num_overlap_frame: int = _DEFAULT_OVERLAP_FRAMES,
    num_motion_latent: int = _DEFAULT_NUM_MOTION_LATENT,
    seed_multiplier: int = _DEFAULT_SEED_MULTIPLIER,
    switch_boundary: float = _DEFAULT_SWITCH_BOUNDARY,
    num_inference_steps: int = _DEFAULT_NUM_STEPS,
    frames_per_clip: int = _FRAMES_PER_CLIP,
    variant: str = "pro",
    model_path_high: str = "auto",
    model_path_low: str = "auto",
    lora_high: str = "SVI_Wan2.2-I2V-A14B_high_noise_lora_v2.0_pro.safetensors",
    lora_low: str = "SVI_Wan2.2-I2V-A14B_low_noise_lora_v2.0_pro.safetensors",
    extra_lora_high: Optional[str] = None,
    extra_lora_low: Optional[str] = None,
    vae_path: str = "auto",
    text_encoder_path: str = "auto",
    sampler_name: str = "euler",
    scheduler: str = "normal",
    blockswap_blocks: int = 0,
    tiled_vae: bool = False,
    # Progress callback
    progress_callback=None,
) -> str:
    """Generate an infinite-length video using SVI 2.0 Pro.

    Uses ComfyUI's native Wan 2.2 I2V-A14B infrastructure with SVI LoRAs
    to generate arbitrarily long videos from a reference image and per-clip
    text prompts.

    Args:
        ref_image_path: Path to the reference/anchor image (first frame).
        prompts: List of text prompts, one per clip. If fewer prompts than
            num_clips, the last prompt is repeated.
        output_path: Output video path. Auto-generated if None.
        num_clips: Number of clips to generate (default 10).
        height: Video height in pixels (default 480).
        width: Video width in pixels (default 832).
        fps: Frames per second (default 15).
        cfg_scale: Classifier-free guidance scale (default 4.0).
        num_overlap_frame: Overlap frames between clips (default 5).
        num_motion_latent: Motion latents from previous clip (default 1).
        seed_multiplier: Seed = clip_idx * seed_multiplier (default 42).
        switch_boundary: When to switch from high to low noise model
            as fraction of 1000 (default 0.875).
        num_inference_steps: Denoising steps per clip (default 50).
        frames_per_clip: Frames per clip (default 81).
        variant: "pro" or "standard" (default "pro").
        blockswap_blocks: Wan 2.2 transformer blocks (of 40) worth of DiT
            weights kept off-GPU during sampling (default 0 = disabled).
        tiled_vae: Decode video latents with tiled VAE (default False).
        progress_callback: Optional callback(clip_idx, total_clips, message).

    Returns:
        Path to the generated video.

    Raises:
        FileNotFoundError: If ref_image_path doesn't exist.
        RuntimeError: If model loading or inference fails.
    """
    if not os.path.isfile(ref_image_path):
        raise FileNotFoundError(f"Reference image not found: {ref_image_path}")

    if output_path is not None:
        output_path = validate_output_file_path(output_path)
    else:
        tmpdir = tempfile.mkdtemp(prefix="svi_out_")
        output_path = os.path.join(tmpdir, "svi_output.mp4")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Pad prompts to match num_clips
    if not prompts:
        prompts = ["A beautiful cinematic scene with natural motion"]
    while len(prompts) < num_clips:
        prompts.append(prompts[-1])

    log.info(
        "SVI generation: %d clips, %dx%d, fps=%d, variant=%s",
        num_clips, width, height, fps, variant,
    )

    # Load models
    models = _load_wan_models(
        variant, model_path_high, model_path_low, lora_high, lora_low,
        extra_lora_high=extra_lora_high, extra_lora_low=extra_lora_low,
    )

    try:
        return _run_svi_inference(
            ref_image_path=ref_image_path,
            prompts=prompts,
            output_path=output_path,
            models=models,
            num_clips=num_clips,
            height=height,
            width=width,
            fps=fps,
            cfg_scale=cfg_scale,
            num_overlap_frame=num_overlap_frame,
            num_motion_latent=num_motion_latent,
            seed_multiplier=seed_multiplier,
            switch_boundary=switch_boundary,
            num_inference_steps=num_inference_steps,
            frames_per_clip=frames_per_clip,
            model_path_high=model_path_high,
            model_path_low=model_path_low,
            extra_lora_high=extra_lora_high,
            extra_lora_low=extra_lora_low,
            vae_path=vae_path,
            text_encoder_path=text_encoder_path,
            sampler_name=sampler_name,
            scheduler=scheduler,
            blockswap_blocks=blockswap_blocks,
            tiled_vae=tiled_vae,
            progress_callback=progress_callback,
        )
    finally:
        # Always free VRAM after generation
        cleanup()


def _run_svi_inference(
    *,
    ref_image_path: str,
    prompts: list[str],
    output_path: str,
    models: dict,
    num_clips: int,
    height: int,
    width: int,
    fps: int,
    cfg_scale: float,
    num_overlap_frame: int,
    num_motion_latent: int,
    seed_multiplier: int,
    switch_boundary: float,
    num_inference_steps: int,
    frames_per_clip: int,
    model_path_high: str = "auto",
    model_path_low: str = "auto",
    extra_lora_high: Optional[str] = None,
    extra_lora_low: Optional[str] = None,
    vae_path: str = "auto",
    text_encoder_path: str = "auto",
    sampler_name: str = "euler",
    scheduler: str = "normal",
    blockswap_blocks: int = 0,
    tiled_vae: bool = False,
    progress_callback=None,
) -> str:
    """Internal: Run the SVI 2.0 Pro inference loop.

    This function orchestrates the iterative clip generation using
    ComfyUI's native model infrastructure.
    """
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        import comfy.sd  # type: ignore[import-not-found]
        import comfy.samplers  # type: ignore[import-not-found]
        import comfy.sample  # type: ignore[import-not-found]
        import comfy.utils  # type: ignore[import-not-found]
        from comfy import model_patcher  # type: ignore[import-not-found]
        import comfy_extras.nodes_wan  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(f"ComfyUI modules required for SVI inference: {e}")

    device = mm.get_torch_device()
    dtype = torch.bfloat16

    # Gentle VRAM cleanup (don't unload ComfyUI-managed models)
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Load input image
    input_image = Image.open(ref_image_path).convert("RGB").resize((width, height))

    # We need to find the Wan 2.2 I2V-A14B checkpoint.
    # Look for it in the standard ComfyUI diffusion_models or unet folders
    wan_model_high = _find_wan22_model(model_path_high)
    wan_model_low = _find_wan22_model(model_path_low)
    if wan_model_high is None or wan_model_low is None:
        missing = []
        if wan_model_high is None:
            missing.append("HighNoise")
        if wan_model_low is None:
            missing.append("LowNoise")
        raise RuntimeError(
            f"Wan 2.2 I2V-A14B {'/'.join(missing)} model not found in ComfyUI model directories. "
            "Please download it first (e.g. via ComfyUI Manager or manually). "
            "Expected location: ComfyUI/models/diffusion_models/ or "
            "ComfyUI/models/unet/"
        )

    log.info("Found Wan 2.2 models: high=%s, low=%s", wan_model_high, wan_model_low)

    # Load VAE (Wan 2.1 VAE — shared between Wan 2.1/2.2)
    if vae_path == "auto" or not vae_path or not os.path.isfile(vae_path):
        vae_path_resolved = _find_wan_vae()
        if vae_path != "auto" and vae_path:
            # User specified a filename — search for it
            vae_path_resolved = _find_model_by_name(vae_path, ["vae"])
        if vae_path_resolved is None:
            raise RuntimeError(
                "Wan VAE not found in ComfyUI model directories. "
                "Expected: Wan2.1_VAE.safetensors in ComfyUI/models/vae/"
            )
        vae_path = vae_path_resolved

    log.info("Found Wan VAE: %s", vae_path)

    # Load text encoder (CLIP/T5 for Wan)
    if text_encoder_path == "auto" or not text_encoder_path or not os.path.isfile(text_encoder_path):
        te_resolved = _find_wan_text_encoder()
        if text_encoder_path != "auto" and text_encoder_path:
            # User specified a filename — search for it
            te_resolved = _find_model_by_name(text_encoder_path, ["text_encoders", "clip"])
        if te_resolved is None:
            raise RuntimeError(
                "Wan text encoder not found in ComfyUI model directories. "
                "Expected: umt5-xxl in ComfyUI/models/text_encoders/ or "
                "ComfyUI/models/clip/"
            )
        text_encoder_path = te_resolved

    log.info("Found Wan text encoder: %s", text_encoder_path)

    # --- Load base model + apply high-noise LoRA ---
    log.info("Loading Wan 2.2 base model with SVI high-noise LoRA...")
    high_lora_path = models["high_lora_path"]
    low_lora_path = models["low_lora_path"]

    def _load_unet(model_path: str):
        """Load a UNet model, auto-detecting GGUF vs safetensors."""
        if model_path.lower().endswith(".gguf"):
            # Use UnetLoaderGGUF node class — handles GGML ops, key mapping, patching
            import sys as _sys
            gguf_nodes_mod = None
            for _key, _mod in _sys.modules.items():
                if _mod is None:
                    continue
                _mf = getattr(_mod, "__file__", "") or ""
                if os.path.join("ComfyUI-GGUF", "nodes.py") in _mf:
                    gguf_nodes_mod = _mod
                    break
            if gguf_nodes_mod and hasattr(gguf_nodes_mod, "UnetLoaderGGUF"):
                loader = gguf_nodes_mod.UnetLoaderGGUF()
                unet_name = os.path.basename(model_path)
                return loader.load_unet(unet_name=unet_name)[0]
            else:
                raise RuntimeError(
                    "GGUF model selected but ComfyUI-GGUF extension not available. "
                    "Install it from: https://github.com/city96/ComfyUI-GGUF"
                )
        else:
            # Standard safetensors/bin loading
            return comfy.sd.load_diffusion_model(model_path)

    base_model = _load_unet(wan_model_high)

    # Apply high-noise LoRA
    high_model = _apply_lora_to_model(base_model, high_lora_path)
    # Apply extra LoRA on top if specified
    if extra_lora_high:
        extra_high_path = _resolve_extra_lora(extra_lora_high)
        if extra_high_path:
            log.info("Applying extra high-noise LoRA: %s", extra_high_path)
            high_model = _apply_lora_to_model(high_model, extra_high_path)
    _register_blockswap(high_model, blockswap_blocks)

    # Load a separate copy with low-noise LoRA
    base_model_low = _load_unet(wan_model_low)
    low_model = _apply_lora_to_model(base_model_low, low_lora_path)
    # Apply extra LoRA on top if specified
    if extra_lora_low:
        extra_low_path = _resolve_extra_lora(extra_lora_low)
        if extra_low_path:
            log.info("Applying extra low-noise LoRA: %s", extra_low_path)
            low_model = _apply_lora_to_model(low_model, extra_low_path)
    _register_blockswap(low_model, blockswap_blocks)

    # Load VAE separately
    vae_model = comfy.sd.VAE(sd=comfy.utils.load_torch_file(vae_path))

    # Load CLIP / text encoder
    if text_encoder_path.lower().endswith(".gguf"):
        # Use ComfyUI-GGUF extension to load GGUF text encoder
        import sys as _sys
        gguf_loader_mod = gguf_ops_mod = gguf_nodes_mod = None
        for _key, _mod in _sys.modules.items():
            if _mod is None:
                continue
            _mf = getattr(_mod, "__file__", "") or ""
            if os.path.join("ComfyUI-GGUF", "loader.py") in _mf:
                gguf_loader_mod = _mod
            elif os.path.join("ComfyUI-GGUF", "ops.py") in _mf:
                gguf_ops_mod = _mod
            elif os.path.join("ComfyUI-GGUF", "nodes.py") in _mf:
                gguf_nodes_mod = _mod
        if not (gguf_loader_mod and gguf_ops_mod and gguf_nodes_mod):
            raise RuntimeError(
                "GGUF text encoder selected but ComfyUI-GGUF extension not available. "
                "Install it from: https://github.com/city96/ComfyUI-GGUF"
            )

        # Load GGUF state dict (handles key mapping, architecture detection)
        clip_sd = gguf_loader_mod.gguf_clip_loader(text_encoder_path)

        # CRITICAL: gguf_clip_loader only extracts spiece_model when
        # token_embd shape is (256384,4096) (Comfy-Org variant).
        # Standard T5 GGUF files (shape 32128,4096) have the tokenizer
        # data in GGUF metadata but it never gets extracted. Fix this
        # by manually calling gguf_tokenizer_loader when spiece_model
        # is missing.
        if "spiece_model" not in clip_sd or clip_sd["spiece_model"] is None:
            log.info("spiece_model missing from GGUF — extracting tokenizer from metadata...")
            try:
                from sentencepiece import sentencepiece_model_pb2 as sp_model
                import gguf as _gguf_lib

                reader = _gguf_lib.GGUFReader(text_encoder_path)

                def _get_field(rdr, key, typ):
                    if key not in rdr.fields:
                        return None
                    field = rdr.fields[key]
                    if typ == str:
                        return bytes(field.parts[-1]).decode("utf-8").strip("\x00")
                    elif typ == bool:
                        return bool(field.parts[-1][0])
                    elif typ == int:
                        return int(field.parts[-1][0])
                    return None

                def _get_list_field(rdr, key, typ):
                    if key not in rdr.fields:
                        return []
                    field = rdr.fields[key]
                    if typ == str:
                        return [bytes(field.parts[idx]).decode("utf-8") for idx in field.data]
                    elif typ == float:
                        return [float(field.parts[idx][0]) for idx in field.data]
                    elif typ == int:
                        return [int(field.parts[idx][0]) for idx in field.data]
                    return []

                spm = sp_model.ModelProto()
                spm.trainer_spec.model_type = 1  # Unigram (T5 standard)

                add_prefix = _get_field(reader, "tokenizer.ggml.add_space_prefix", bool)
                if add_prefix is not None:
                    spm.normalizer_spec.add_dummy_prefix = add_prefix
                rm_ws = _get_field(reader, "tokenizer.ggml.remove_extra_whitespaces", bool)
                if rm_ws is not None:
                    spm.normalizer_spec.remove_extra_whitespaces = rm_ws

                tokens = _get_list_field(reader, "tokenizer.ggml.tokens", str)
                scores = _get_list_field(reader, "tokenizer.ggml.scores", float)
                toktypes = _get_list_field(reader, "tokenizer.ggml.token_type", int)

                for token, score, toktype in zip(tokens, scores, toktypes):
                    piece = spm.SentencePiece()
                    piece.piece = token
                    piece.score = score
                    piece.type = toktype
                    spm.pieces.append(piece)

                spm.trainer_spec.byte_fallback = True
                spm.trainer_spec.vocab_size = len(tokens)
                spm.trainer_spec.max_sentence_length = 4096
                eos_id = _get_field(reader, "tokenizer.ggml.eos_token_id", int)
                if eos_id is not None:
                    spm.trainer_spec.eos_id = eos_id
                pad_id = _get_field(reader, "tokenizer.ggml.padding_token_id", int)
                if pad_id is not None:
                    spm.trainer_spec.pad_id = pad_id

                clip_sd["spiece_model"] = torch.ByteTensor(list(spm.SerializeToString()))
                log.info("Tokenizer extracted successfully (%d tokens)", len(tokens))
                del reader
            except ImportError:
                log.warning("sentencepiece/protobuf not available for tokenizer extraction")
            except Exception as e:
                log.warning("Failed to extract tokenizer from GGUF metadata: %s", e)

        import folder_paths  # type: ignore[import-not-found]
        clip_model = comfy.sd.load_text_encoder_state_dicts(
            clip_type=comfy.sd.CLIPType.WAN,
            state_dicts=[clip_sd],
            model_options={
                "custom_operations": gguf_ops_mod.GGMLOps,
                "initial_device": comfy.model_management.text_encoder_offload_device(),
            },
            embedding_directory=folder_paths.get_folder_paths("embeddings"),
        )
        clip_model.patcher = gguf_nodes_mod.GGUFModelPatcher.clone(clip_model.patcher)
    else:
        # Standard safetensors/bin text encoder
        clip_model = comfy.sd.load_clip(
            ckpt_paths=[text_encoder_path],
            embedding_directory=None,
            clip_type=comfy.sd.CLIPType.WAN,
        )

    # --- Encode text prompts ---
    log.info("Encoding text prompts...")
    # Encode prompts using CLIP model — match CLIPTextEncode node behavior
    prompt_conds = []
    for prompt_text in prompts[:num_clips]:
        tokens = clip_model.tokenize(prompt_text)
        cond = clip_model.encode_from_tokens_scheduled(tokens)
        prompt_conds.append(cond)

    neg_tokens = clip_model.tokenize(_NEGATIVE_PROMPT)
    neg_cond = clip_model.encode_from_tokens_scheduled(neg_tokens)

    # All prompts are encoded up-front; evict the text encoder weights now so
    # they don't compete with the UNets + VAE for VRAM during sampling.
    try:
        mm.unload_model_and_clones(clip_model.patcher)  # type: ignore[attr-defined]
        log.info("SVI: Unloaded text encoder after prompt encoding")
    except Exception as e:
        log.warning("SVI: Could not unload text encoder: %s", e)


    # --- Apply sigma_shift for SVI LoRAs ---
    # VERIFIED: With shift=5.0, ComfyUI's 'normal' scheduler produces IDENTICAL
    # sigmas to Kijai's FlowMatchEulerDiscreteScheduler (e.g. 4 steps:
    # [1.0, 0.9375, 0.8333, 0.625]). Native shift=8.0 gives different values
    # [1.0, 0.96, 0.8889, 0.7273] which doesn't match SVI training.
    _SVI_SIGMA_SHIFT = 5.0
    try:
        high_model.model.model_sampling.set_parameters(shift=_SVI_SIGMA_SHIFT)
        if low_model is not high_model:
            low_model.model.model_sampling.set_parameters(shift=_SVI_SIGMA_SHIFT)
        log.info("SVI: Applied sigma_shift=%.1f to model_sampling", _SVI_SIGMA_SHIFT)
    except Exception as e:
        log.warning("SVI: Could not set sigma_shift: %s", e)

    # --- Iterative clip generation ---
    # Write frames to disk incrementally to avoid RAM/VRAM OOM with many clips
    import tempfile, shutil
    frame_dir = tempfile.mkdtemp(prefix="svi_frames_")
    frame_count = 0
    prev_last_latent = None
    total_latents = (frames_per_clip - 1) // 4 + 1

    for clip_idx in range(num_clips):
        msg = f"Generating clip {clip_idx + 1}/{num_clips}..."
        log.info(msg)
        if progress_callback:
            progress_callback(clip_idx, num_clips, msg)

        # --- Free VRAM BEFORE VAE encode ---
        # On clip 2+, UNets from previous sampling are still loaded.
        # Unload everything so VAE encode has room for the 81-frame tensor.
        if clip_idx > 0:
            comfy.model_management.unload_all_models()
            comfy.model_management.soft_empty_cache()
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            if torch.cuda.is_available():
                free_mb = torch.cuda.mem_get_info()[0] / (1024 * 1024)
                log.info("SVI: VRAM before clip %d: %.0f MB free", clip_idx + 1, free_mb)

        seed = clip_idx * seed_multiplier

        # --- Set up I2V conditioning (vendored from WanVideoSVIProEmbeds) ---
        # SVI LoRAs were trained with Kijai's WanVideoWrapper which:
        #  1. VAE-encodes ONLY the anchor image (single frame)
        #  2. Pads image latent with zeros (NOT VAE-encoded gray)
        #  3. Passes raw y = cat(mask, image_latent) directly to transformer
        # ComfyUI's native path is incompatible (encodes full video + normalizes)

        # 1. VAE-encode ONLY the single anchor image
        if prev_last_latent is None:
            anchor_for_vae = input_image.resize((width, height))
            anchor_np = np.array(anchor_for_vae).astype(np.float32) / 255.0
            start_frame = torch.from_numpy(anchor_np).unsqueeze(0)  # [1, H, W, 3]
        else:
            anchor_for_vae = input_image.resize((width, height))
            anchor_np = np.array(anchor_for_vae).astype(np.float32) / 255.0
            start_frame = torch.from_numpy(anchor_np).unsqueeze(0)  # [1, H, W, 3]

        # Encode just the anchor frame → [1, 16, 1, H_lat, W_lat]
        anchor_latent = vae_model.encode(start_frame[:, :, :, :3])
        # anchor_latent shape: [1, C=16, T=1, H_lat, W_lat]
        log.info("SVI anchor_latent: shape=%s mean=%.4f std=%.4f min=%.4f max=%.4f",
                 list(anchor_latent.shape),
                 anchor_latent.float().mean().item(),
                 anchor_latent.float().std().item(),
                 anchor_latent.float().min().item(),
                 anchor_latent.float().max().item())

        lat_h = anchor_latent.shape[-2]
        lat_w = anchor_latent.shape[-1]

        # 2. Build image_latent: anchor [+ motion latents] + zero padding
        #    (matching Kijai's WanVideoSVIProEmbeds)
        #    Shape: [C=16, T=total_latents, H_lat, W_lat] (NO batch dim)
        anchor_lat_unbatched = anchor_latent[0]  # [16, 1, H_lat, W_lat]
        if prev_last_latent is not None and num_motion_latent > 0:
            # Clip 2+: include motion latents from previous clip output
            # This is how SVI Pro creates seamless transitions between clips
            motion_lat = prev_last_latent[0, :, -num_motion_latent:]  # [16, M, H, W]
            motion_lat = motion_lat.to(
                device=anchor_lat_unbatched.device,
                dtype=anchor_lat_unbatched.dtype,
            )
            padding_size = total_latents - anchor_lat_unbatched.shape[1] - motion_lat.shape[1]
            padding = torch.zeros(
                16, padding_size, lat_h, lat_w,
                dtype=anchor_lat_unbatched.dtype, device=anchor_lat_unbatched.device,
            )
            image_latent_y = torch.cat([anchor_lat_unbatched, motion_lat, padding], dim=1)
            log.info("SVI clip %d: y = anchor[%d] + motion[%d] + pad[%d]",
                     clip_idx + 1, anchor_lat_unbatched.shape[1],
                     motion_lat.shape[1], padding_size)
        else:
            # First clip: anchor + zero padding only
            padding_size = total_latents - anchor_lat_unbatched.shape[1]
            padding = torch.zeros(
                16, padding_size, lat_h, lat_w,
                dtype=anchor_lat_unbatched.dtype, device=anchor_lat_unbatched.device,
            )
            image_latent_y = torch.cat([anchor_lat_unbatched, padding], dim=1)
        # image_latent_y: [16, total_latents, H_lat, W_lat]

        # 3. Build mask — Kijai's SVI Pro convention (from WanVideoSVIProEmbeds):
        #    mask=1 for first frame (repeated 4x for 4 channels), 0 elsewhere
        msk = torch.ones(1, frames_per_clip, lat_h, lat_w,
                         device=anchor_lat_unbatched.device,
                         dtype=anchor_lat_unbatched.dtype)
        msk[:, 1:] = 0
        msk = torch.cat([
            torch.repeat_interleave(msk[:, 0:1], repeats=4, dim=1),
            msk[:, 1:]
        ], dim=1)
        msk = msk.view(1, msk.shape[1] // 4, 4, lat_h, lat_w)
        msk = msk.transpose(1, 2)[0]  # [4, total_latents, H_lat, W_lat]

        # 4. Build raw y tensor: [20, T_lat, H_lat, W_lat] (NO batch dim)
        #    = cat(mask[4ch], image_latent[16ch]) along channel dim
        raw_y = torch.cat([msk, image_latent_y], dim=0)
        # Add batch dim for c_concat injection: [1, 20, T_lat, H_lat, W_lat]
        raw_y = raw_y.unsqueeze(0)

        # 5. Create unet_function_wrapper to inject raw y, bypassing
        #    WAN21.concat_cond()'s process_latent_in normalization
        _svi_call_count = [0]

        def svi_wrapper(model_function, kwargs):
            """Bypass concat_cond — inject raw y directly as c_concat."""
            input_x = kwargs["input"]     # [B, 16, T, H, W]
            timestep = kwargs["timestep"]
            c = kwargs.get("c", {})
            B = input_x.shape[0]

            # Remove any normalized c_concat from concat_cond
            c.pop("c_concat", None)

            # Inject raw y as c_concat (will be concatenated to x in
            # _apply_model → torch.cat([xc, c_concat], dim=1))
            y_dev = raw_y.to(device=input_x.device, dtype=input_x.dtype)
            if y_dev.shape[0] != B:
                y_dev = y_dev.expand(B, -1, -1, -1, -1)
            # Match temporal dimension
            if y_dev.shape[2] != input_x.shape[2]:
                y_dev = y_dev[:, :, :input_x.shape[2]]
            c["c_concat"] = y_dev

            _svi_call_count[0] += 1
            if _svi_call_count[0] <= 2:
                def _stats(t, name):
                    return (f"{name}: shape={list(t.shape)} "
                            f"mean={t.float().mean():.4f} "
                            f"std={t.float().std():.4f} "
                            f"min={t.float().min():.4f} "
                            f"max={t.float().max():.4f}")
                log.info("[SVI] call=%d t=%.1f", _svi_call_count[0],
                         timestep.float().mean().item())
                log.info("[SVI]   %s", _stats(input_x, "x"))
                log.info("[SVI]   %s", _stats(y_dev[:, :4], "y_mask"))
                log.info("[SVI]   %s", _stats(y_dev[:, 4:], "y_img"))

            return model_function(input_x, timestep, **c)

        high_model.set_model_unet_function_wrapper(svi_wrapper)
        if low_model is not high_model:
            low_model.set_model_unet_function_wrapper(svi_wrapper)

        # 6. Use text conditioning only (no concat_latent_image/concat_mask)
        positive = prompt_conds[clip_idx]
        negative = neg_cond

        # 5. Starting latent = zeros (noise will be added by sampler)
        latent_image = torch.zeros(
            1, 16, total_latents, height // 8, width // 8,
            device=comfy.model_management.intermediate_device(),
        )

        # Motion conditioning is in y (image_latent_y), NOT in noise.
        # Starting latent is always zeros — noise is added by the sampler.

        # Generate noise
        noise = torch.randn_like(latent_image)

        # Sample with high-noise model first, then switch to low-noise
        boundary_step = int(num_inference_steps * switch_boundary)
        is_single_pass = (boundary_step >= num_inference_steps)

        # Stage 1: High noise model
        latent_high = comfy.sample.sample(
            model=high_model,
            noise=noise,
            positive=positive,
            negative=negative,
            cfg=cfg_scale,
            sampler_name=sampler_name,
            scheduler=scheduler,
            steps=num_inference_steps,
            start_step=0,
            last_step=boundary_step,
            latent_image=latent_image,
            denoise=1.0,
            disable_noise=True,
            force_full_denoise=is_single_pass,
            seed=seed,
        )

        # Stage 2: Low noise model
        # NOTE: inverse_noise_scaling at end of Stage 1 outputs x/(1-sigma),
        # then noise_scaling at start of Stage 2 does (1-sigma) * input.
        # These cancel: (1-sigma) * x/(1-sigma) = x. No pre-scaling needed.
        if not is_single_pass:
            latent_final = comfy.sample.sample(
                model=low_model,
                noise=torch.zeros_like(noise),
                positive=positive,
                negative=negative,
                cfg=cfg_scale,
                sampler_name=sampler_name,
                scheduler=scheduler,
                steps=num_inference_steps,
                start_step=boundary_step,
                last_step=num_inference_steps,
                latent_image=latent_high,
                denoise=1.0,
                disable_noise=True,
                force_full_denoise=True,
                seed=seed,
            )
        else:
            latent_final = latent_high

        # Save last latent for next clip — move to CPU to free GPU
        prev_last_latent = latent_final.detach().clone().cpu()

        # Free sampling intermediates before VAE decode
        # (careful: if single_pass, latent_final IS latent_high)
        del noise
        if is_single_pass:
            del latent_high  # latent_final was aliased to this
        else:
            del latent_high, latent_final
        del positive, negative, image_latent_y, msk, raw_y, anchor_latent, start_frame
        del latent_image
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        comfy.model_management.soft_empty_cache()

        # Decode latent to frames via VAE
        latent_gpu = prev_last_latent.to(comfy.model_management.get_torch_device())
        if tiled_vae:
            decoded = vae_model.decode_tiled(latent_gpu)
        else:
            decoded = vae_model.decode(latent_gpu)
        del latent_gpu
        clip_frames = _tensor_to_pil_frames(decoded)
        del decoded

        # Color-match decoded frames to the reference image.
        # The VAE round-trip introduces color/brightness drift; standard SVI
        # workflows (Kijai WanVideoLooper, KJNodes ColorMatch) compensate by
        # matching the generated frames' histogram to the input image.
        clip_frames = _color_match_frames(clip_frames, input_image)

        # Write frames to disk (not RAM) to avoid OOM on many clips
        if clip_idx == 0:
            for frame in clip_frames:
                frame_path = os.path.join(frame_dir, f"frame_{frame_count:06d}.png")
                frame.save(frame_path)
                frame_count += 1
        else:
            # Crossfade overlap region for smooth clip transitions
            # Read the last num_overlap_frame frames from disk, blend with
            # the first num_overlap_frame frames of this clip
            overlap = min(num_overlap_frame, len(clip_frames))
            for ov_i in range(overlap):
                # Linear blend weight: 0.0 → 1.0 over the overlap region
                alpha = (ov_i + 1) / (overlap + 1)
                prev_frame_idx = frame_count - overlap + ov_i
                prev_path = os.path.join(frame_dir, f"frame_{prev_frame_idx:06d}.png")
                if os.path.exists(prev_path):
                    prev_frame = Image.open(prev_path)
                    new_frame = clip_frames[ov_i]
                    blended = Image.blend(prev_frame, new_frame, alpha)
                    blended.save(prev_path)
                    prev_frame.close()
            # Write the remaining (non-overlap) frames
            for frame in clip_frames[overlap:]:
                frame_path = os.path.join(frame_dir, f"frame_{frame_count:06d}.png")
                frame.save(frame_path)
                frame_count += 1
        del clip_frames

        log.info(
            "Clip %d complete → %d total frames saved to disk",
            clip_idx + 1, frame_count,
        )

        # --- Aggressive VRAM flush between clips ---
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        comfy.model_management.soft_empty_cache()
        if torch.cuda.is_available():
            free_mb = torch.cuda.mem_get_info()[0] / (1024 * 1024)
            log.info("SVI: VRAM after clip %d cleanup: %.0f MB free", clip_idx + 1, free_mb)

    # --- Free all models before video encoding ---
    # Explicitly delete model objects to release VRAM immediately.
    # Without this, Python GC may not collect them before the next run.
    del high_model, low_model, vae_model, clip_model
    del prompt_conds, neg_cond, prev_last_latent
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    comfy.model_management.unload_all_models()
    comfy.model_management.soft_empty_cache()
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        free_mb = torch.cuda.mem_get_info()[0] / (1024 * 1024)
        log.info("SVI: VRAM after model cleanup: %.0f MB free", free_mb)

    # --- Read frames back from disk and encode final video ---
    log.info("Encoding final video: %d frames at %d fps → %s",
             frame_count, fps, output_path)
    all_video_frames = []
    for i in range(frame_count):
        fp = os.path.join(frame_dir, f"frame_{i:06d}.png")
        all_video_frames.append(Image.open(fp).convert("RGB"))
    _encode_video_from_frames(all_video_frames, output_path, fps=fps)
    del all_video_frames

    # Clean up temp frame directory
    shutil.rmtree(frame_dir, ignore_errors=True)

    log.info("SVI generation complete: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
#  ComfyUI model discovery helpers
# ---------------------------------------------------------------------------

def _find_wan22_model(model_path: str = "auto") -> Optional[str]:
    """Find Wan 2.2 I2V-A14B model in ComfyUI model directories.

    Args:
        model_path: "auto" to auto-discover, or a filename/absolute path
    """
    # If user specified a path
    if model_path and model_path != "auto":
        if os.path.isfile(model_path):
            return model_path
        # Try as a filename in ComfyUI model dirs
        try:
            import folder_paths  # type: ignore[import-not-found]
            for folder_name in ["diffusion_models", "unet", "checkpoints"]:
                try:
                    paths = folder_paths.get_folder_paths(folder_name)
                    for d in paths:
                        candidate = os.path.join(d, model_path)
                        if os.path.isfile(candidate):
                            return candidate
                except Exception:
                    pass
        except ImportError:
            pass
        log.warning("User-specified SVI model not found: %s — falling back to auto", model_path)
    try:
        import folder_paths  # type: ignore[import-not-found]
    except ImportError:
        return None

    # Search in diffusion_models and unet folders
    search_dirs = []
    for folder_name in ["diffusion_models", "unet", "checkpoints"]:
        try:
            paths = folder_paths.get_folder_paths(folder_name)
            search_dirs.extend(paths)
        except Exception:
            pass

    # Look for Wan 2.2 model files
    wan22_patterns = [
        "wan2.2", "Wan2.2", "wan22", "Wan22",
        "wan2_2", "Wan2_2",
    ]

    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for root, dirs, files in os.walk(search_dir):
            for f in files:
                if not f.endswith((".safetensors", ".ckpt", ".pt", ".pth")):
                    continue
                # Check if filename matches Wan 2.2 pattern
                f_lower = f.lower()
                if any(pat.lower() in f_lower for pat in wan22_patterns):
                    if "i2v" in f_lower or "14b" in f_lower:
                        return os.path.join(root, f)

    return None


def _find_model_by_name(filename: str, folder_names: list[str]) -> Optional[str]:
    """Find a model file by filename in ComfyUI model directories."""
    try:
        import folder_paths  # type: ignore[import-not-found]
    except ImportError:
        return None

    for folder_name in folder_names:
        try:
            paths = folder_paths.get_folder_paths(folder_name)
        except Exception:
            continue
        for search_dir in paths:
            if not os.path.isdir(search_dir):
                continue
            for root, _dirs, files in os.walk(search_dir):
                for f in files:
                    if f == filename or f.lower() == filename.lower():
                        return os.path.join(root, f)
    return None


def _find_wan_vae() -> Optional[str]:
    """Find Wan VAE in ComfyUI model directories."""
    try:
        import folder_paths  # type: ignore[import-not-found]
    except ImportError:
        return None

    search_dirs = []
    for folder_name in ["vae"]:
        try:
            paths = folder_paths.get_folder_paths(folder_name)
            search_dirs.extend(paths)
        except Exception:
            pass

    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for root, _dirs, files in os.walk(search_dir):
            for f in files:
                f_lower = f.lower()
                if "wan" in f_lower and f.endswith(".safetensors"):
                    return os.path.join(root, f)

    return None


def _find_wan_text_encoder() -> Optional[str]:
    """Find Wan text encoder in ComfyUI model directories."""
    try:
        import folder_paths  # type: ignore[import-not-found]
    except ImportError:
        return None

    search_dirs = []
    for folder_name in ["text_encoders", "clip"]:
        try:
            paths = folder_paths.get_folder_paths(folder_name)
            search_dirs.extend(paths)
        except Exception:
            pass

    # Collect candidates — prefer UMT5 GGUF (works natively with Wan 2.2)
    candidates = []  # (priority, path)
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for root, _dirs, files in os.walk(search_dir):
            for f in files:
                f_lower = f.lower()
                if not f.endswith((".safetensors", ".bin", ".gguf")):
                    continue
                if "t5" not in f_lower:
                    continue
                full_path = os.path.join(root, f)
                # Priority: UMT5 safetensors (0) > UMT5 GGUF (1) > T5 safetensors (2) > T5 GGUF (3)
                if "umt5" in f_lower and f.endswith(".safetensors"):
                    candidates.append((0, full_path))
                elif "umt5" in f_lower and f.endswith(".gguf"):
                    candidates.append((1, full_path))
                elif f.endswith(".safetensors"):
                    candidates.append((2, full_path))
                elif f.endswith(".gguf"):
                    candidates.append((3, full_path))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    return None


# ---------------------------------------------------------------------------
#  LoRA application helper
# ---------------------------------------------------------------------------

def _apply_lora_to_model(model, lora_path: str, strength: float = 1.0):
    """Apply a LoRA to a ComfyUI model patcher.

    Handles key conversion from diffusers format to ComfyUI format:
      diffusers:  blocks.0.cross_attn.k.lora_A.default.weight
      ComfyUI:    diffusion_model.blocks.0.cross_attn.k.lora_A.weight

    Two conversions:
      1. Add 'diffusion_model.' prefix
      2. Remove '.default' from lora_A/lora_B paths

    Args:
        model: ComfyUI ModelPatcher instance
        lora_path: Path to the LoRA safetensors file
        strength: LoRA alpha/strength (default 1.0)

    Returns:
        ModelPatcher with LoRA applied
    """
    try:
        import comfy.sd  # type: ignore[import-not-found]
        import comfy.utils  # type: ignore[import-not-found]
    except ImportError:
        raise ImportError("ComfyUI is required for LoRA application")

    lora_sd = comfy.utils.load_torch_file(lora_path)

    # Auto-detect and convert diffusers-format SVI LoRA keys
    sample_key = next(iter(lora_sd), "")
    if ".lora_" in sample_key and (
        sample_key.startswith("blocks.") or ".default." in sample_key
    ):
        converted = {}
        for k, v in lora_sd.items():
            new_key = k
            # 1. Remove '.default' from LoRA key paths
            new_key = new_key.replace(".lora_A.default.", ".lora_A.")
            new_key = new_key.replace(".lora_B.default.", ".lora_B.")
            # 2. Add 'diffusion_model.' prefix if missing
            if not new_key.startswith("diffusion_model."):
                new_key = f"diffusion_model.{new_key}"
            # 3. Cast bfloat16 → float16 (GGUF patching requires fp16)
            if v.dtype == torch.bfloat16:
                v = v.to(torch.float16)
            converted[new_key] = v
        log.info(
            "SVI LoRA key conversion: %d keys converted "
            "(diffusers → ComfyUI format)", len(converted),
        )
        lora_sd = converted

    # Apply LoRA using ComfyUI's built-in LoRA loader
    key_count_before = len(lora_sd)
    model_lora, _ = comfy.sd.load_lora_for_models(
        model, None, lora_sd, strength, 0,
    )
    # Diagnostic: check how many patches were actually applied
    patches_applied = 0
    if hasattr(model_lora, 'patches') and isinstance(model_lora.patches, dict):
        patches_applied = len(model_lora.patches)
    log.info(
        "SVI LoRA applied: %s — %d input keys, %d model patches",
        os.path.basename(lora_path), key_count_before, patches_applied,
    )
    # Log sample of matched keys for debugging
    if patches_applied > 0:
        sample_keys = list(model_lora.patches.keys())[:3]
        log.info("  Sample patch keys: %s", sample_keys)
    return model_lora


# ---------------------------------------------------------------------------
#  Tensor conversion helpers
# ---------------------------------------------------------------------------

def _pil_to_tensor(image: Image.Image) -> torch.Tensor:
    """Convert PIL Image to ComfyUI IMAGE tensor [1, H, W, 3] float32 0-1."""
    arr = np.array(image).astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)


def _color_match_frames(
    frames: list[Image.Image],
    reference: Image.Image,
) -> list[Image.Image]:
    """Match each frame's color profile to the reference image.

    Uses per-channel histogram matching (cumulative distribution function
    equalization) — the same approach as Kijai's ColorMatch / WanVideoLooper
    built-in color matching.

    Args:
        frames: Generated frames to color-correct.
        reference: The original input image whose colors we want to match.

    Returns:
        New list of color-matched PIL Images.
    """
    ref_np = np.array(reference.convert("RGB")).astype(np.float64)
    matched: list[Image.Image] = []

    for frame in frames:
        src_np = np.array(frame.convert("RGB")).astype(np.float64)
        result = np.empty_like(src_np)

        for ch in range(3):
            # Build CDFs for source and reference channels
            src_vals = src_np[:, :, ch].ravel()
            ref_vals = ref_np[:, :, ch].ravel()

            src_counts, bin_edges = np.histogram(src_vals, bins=256, range=(0, 256))
            ref_counts, _ = np.histogram(ref_vals, bins=256, range=(0, 256))

            src_cdf = np.cumsum(src_counts).astype(np.float64)
            ref_cdf = np.cumsum(ref_counts).astype(np.float64)

            # Normalize CDFs
            src_cdf /= src_cdf[-1] if src_cdf[-1] > 0 else 1.0
            ref_cdf /= ref_cdf[-1] if ref_cdf[-1] > 0 else 1.0

            # Build mapping: for each source intensity, find the closest
            # matching intensity in the reference CDF
            mapping = np.zeros(256, dtype=np.uint8)
            ref_idx = 0
            for src_i in range(256):
                while ref_idx < 255 and ref_cdf[ref_idx] < src_cdf[src_i]:
                    ref_idx += 1
                mapping[src_i] = ref_idx

            result[:, :, ch] = mapping[src_np[:, :, ch].astype(np.uint8)]

        matched.append(Image.fromarray(result.astype(np.uint8)))

    return matched


def _tensor_to_pil_frames(tensor: torch.Tensor) -> list[Image.Image]:
    """Convert ComfyUI decoded video tensor to list of PIL Images.

    Handles various tensor formats from VAE decode:
    - [B, H, W, C] — batch of frames (C=3)
    - [B, C, T, H, W] — video latent format (C=3 or 16)
    - [B, T, H, W, C] — video frames format (C=3)
    - [T, H, W, C] — unbatched video frames
    """
    log.debug("_tensor_to_pil_frames: input shape=%s dtype=%s", tensor.shape, tensor.dtype)

    # Squeeze batch dim if batch=1 and 5D
    if tensor.dim() == 5 and tensor.shape[0] == 1:
        tensor = tensor.squeeze(0)  # → [C/T, T/H, H/W, W/C]

    if tensor.dim() == 4:
        # Determine if [T, H, W, C] or [C, T, H, W]
        if tensor.shape[-1] <= 4:
            # [T, H, W, C] — standard video frames
            frames = []
            for i in range(tensor.shape[0]):
                frame = tensor[i]
                if frame.dtype == torch.float32 or frame.dtype == torch.float16 or frame.dtype == torch.bfloat16:
                    frame = (frame.clamp(0, 1) * 255).byte()
                frames.append(Image.fromarray(frame.cpu().numpy().astype(np.uint8)))
            return frames
        elif tensor.shape[1] <= 4:
            # [C, T, H, W] — channel-first video
            t = tensor.shape[1]
            frames = []
            for i in range(t):
                frame = tensor[:, i].permute(1, 2, 0)  # [H, W, C]
                frame = (frame.clamp(0, 1) * 255).byte()
                frames.append(Image.fromarray(frame.cpu().numpy().astype(np.uint8)))
            return frames
        else:
            # Ambiguous — assume [T, H, W, C] if last dim is 3
            frames = []
            for i in range(tensor.shape[0]):
                frame = tensor[i]
                if frame.dtype in (torch.float32, torch.float16, torch.bfloat16):
                    frame = (frame.clamp(0, 1) * 255).byte()
                frames.append(Image.fromarray(frame.cpu().numpy().astype(np.uint8)))
            return frames
    elif tensor.dim() == 5:
        # Still 5D after squeeze failed (batch>1): [B, C/T, T/H, H/W, W/C]
        if tensor.shape[-1] <= 4:
            # [B, T, H, W, C]
            frames = []
            for b in range(tensor.shape[0]):
                for t in range(tensor.shape[1]):
                    frame = tensor[b, t]
                    if frame.dtype in (torch.float32, torch.float16, torch.bfloat16):
                        frame = (frame.clamp(0, 1) * 255).byte()
                    frames.append(Image.fromarray(frame.cpu().numpy().astype(np.uint8)))
            return frames
        else:
            # [B, C, T, H, W]
            frames = []
            for b in range(tensor.shape[0]):
                for t in range(tensor.shape[2]):
                    frame = tensor[b, :, t].permute(1, 2, 0)
                    frame = (frame.clamp(0, 1) * 255).byte()
                    frames.append(Image.fromarray(frame.cpu().numpy().astype(np.uint8)))
            return frames
    elif tensor.dim() == 3:
        # Single frame [H, W, C]
        frame = tensor
        if frame.dtype in (torch.float32, torch.float16, torch.bfloat16):
            frame = (frame.clamp(0, 1) * 255).byte()
        return [Image.fromarray(frame.cpu().numpy().astype(np.uint8))]
    else:
        raise ValueError(f"Unexpected tensor shape for frame conversion: {tensor.shape}")

