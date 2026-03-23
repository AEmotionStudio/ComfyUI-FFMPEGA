# coding: utf-8
"""SCAIL synthesizer — pose-driven character animation video generation.

**⚠️ WIP**: Memory optimization incomplete — OOMs on GPUs with <24 GiB VRAM.
See SCAIL_Memory_Report.md for details.

Follows the same integration pattern as ``dreamid_omni_synthesizer.py``:

- Module-level pipeline cache (``_pipeline``) to avoid repeated loading
- VRAM management via ``_vram_utils.free_for_module()``
- Model download via ``huggingface_hub`` with AEmotionStudio HF mirror
- ``generate_video()`` entry point for no-LLM mode callers
- ``cleanup()`` function for VRAM reclamation
"""

from __future__ import annotations

import gc
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch

log = logging.getLogger("ffmpega")

# ======================================================================
# Constants
# ======================================================================

# Primary mirror — our repo with clean filenames
HF_MIRROR = "AEmotionStudio/SCAIL-fp8"

# Fallback repos (Kijai's original uploads)
_HF_KIJAI = "Kijai/WanVideo_comfy"
_HF_KIJAI_FP8 = "Kijai/WanVideo_comfy_fp8_scaled"

# Kijai source filenames (only used for fallback)
_KIJAI_SCAIL_FP8 = "SCAIL/Wan21-14B-SCAIL-preview_fp8_e4m3fn_scaled_KJ.safetensors"
_KIJAI_SCAIL_BF16 = "SCAIL/Wan21-14B-SCAIL-preview_comfy_bf16.safetensors"
_KIJAI_VAE = "Wan2_1_VAE_bf16.safetensors"
_KIJAI_T5_BF16 = "umt5-xxl-enc-bf16.safetensors"
_KIJAI_T5_FP8 = "umt5-xxl-enc-fp8_e4m3fn.safetensors"
_KIJAI_CLIP = "open-clip-xlm-roberta-large-vit-huge-14_visual_fp16.safetensors"

# Local filenames (same as mirror filenames)
_SCAIL_FP8_LOCAL = "scail_fp8.safetensors"
_SCAIL_BF16_LOCAL = "scail_bf16.safetensors"
_VAE_LOCAL = "wan2_1_vae.safetensors"
_T5_LOCAL = "umt5-xxl-enc.safetensors"
_CLIP_LOCAL = "clip_visual.safetensors"

DEFAULT_STEPS = 40
DEFAULT_SOLVER = "unipc"
DEFAULT_SHIFT = 3.0
DEFAULT_GUIDANCE = 5.0
DEFAULT_SEED = 42

# ======================================================================
# Module-level pipeline cache
# ======================================================================

_pipeline = None
_pipeline_ckpt_dir: str | None = None
_pipeline_variant: str = ""


# ======================================================================
# Model directory helpers
# ======================================================================


def _get_model_dir() -> str:
    """Return the model checkpoint directory for SCAIL.

    Tries ComfyUI's ``folder_paths`` first, falls back to
    ``~/.cache/scail``.
    """
    try:
        import folder_paths  # type: ignore[import-not-found]
        base = folder_paths.models_dir
    except (ImportError, AttributeError):
        base = os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "scail")


def _resolve_checkpoint(ckpt_dir: str, precision: str = "auto") -> tuple[str, str]:
    """Resolve the SCAIL model checkpoint path.

    Returns:
        (checkpoint_path, variant_label)
    """
    fp8_path = os.path.join(ckpt_dir, _SCAIL_FP8_LOCAL)
    bf16_path = os.path.join(ckpt_dir, _SCAIL_BF16_LOCAL)

    if precision == "fp8":
        if os.path.isfile(fp8_path):
            return fp8_path, "fp8"
        raise RuntimeError(
            f"FP8 model requested but not found at {fp8_path}."
        )
    elif precision == "bf16":
        if os.path.isfile(bf16_path):
            return bf16_path, "bf16"
        raise RuntimeError(
            f"BF16 model not found at {bf16_path}."
        )
    else:  # "auto" — prefer fp8 > bf16
        if os.path.isfile(fp8_path):
            log.info("SCAIL auto: using FP8 checkpoint")
            return fp8_path, "fp8"
        if os.path.isfile(bf16_path):
            log.info("SCAIL auto: using BF16 checkpoint")
            return bf16_path, "bf16"
        # Nothing found — will need download → default to FP8
        return fp8_path, "fp8"


def _ensure_weights_ready(ckpt_dir: str, precision: str = "auto") -> None:
    """Download model weights if they don't exist yet."""
    try:
        from .model_manager import (
            require_downloads_allowed,
            log_download_start,
            log_download_complete,
        )
    except ImportError:
        from core.model_manager import (  # type: ignore
            require_downloads_allowed,
            log_download_start,
            log_download_complete,
        )

    ckpt_path, variant = _resolve_checkpoint(ckpt_dir, precision)
    vae_path = os.path.join(ckpt_dir, _VAE_LOCAL)
    t5_path = os.path.join(ckpt_dir, _T5_LOCAL)
    clip_path = os.path.join(ckpt_dir, _CLIP_LOCAL)

    all_present = (
        os.path.isfile(ckpt_path)
        and os.path.isfile(vae_path)
        and os.path.isfile(t5_path)
        and os.path.isfile(clip_path)
    )

    if all_present:
        log.info("SCAIL: all model files present in %s", ckpt_dir)
        return

    require_downloads_allowed("scail")

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise RuntimeError(
            "huggingface_hub is required to download SCAIL models. "
            "Install with: pip install huggingface_hub"
        )

    os.makedirs(ckpt_dir, exist_ok=True)

    def _download_from_mirror(local_name: str, label: str):
        """Download from our mirror — filename matches local_name exactly."""
        dest = os.path.join(ckpt_dir, local_name)
        if os.path.isfile(dest):
            return True
        log_download_start("scail", f"{label} (from mirror)")
        try:
            hf_hub_download(
                repo_id=HF_MIRROR, filename=local_name, local_dir=ckpt_dir,
            )
            log_download_complete("scail", dest)
            return True
        except Exception as e:
            log.warning("SCAIL mirror download failed for %s: %s", local_name, e)
            return False

    def _download_from_kijai(repo: str, hf_file: str, local_name: str, label: str):
        """Fallback: download from Kijai's repo, rename to local_name."""
        dest = os.path.join(ckpt_dir, local_name)
        if os.path.isfile(dest):
            return
        log_download_start("scail", f"{label} (from Kijai fallback)")
        downloaded = hf_hub_download(
            repo_id=repo, filename=hf_file, local_dir=ckpt_dir,
        )
        # hf_hub_download places in subdirs for paths with /
        hf_local = os.path.join(ckpt_dir, hf_file)
        if os.path.isfile(hf_local) and hf_local != dest:
            os.rename(hf_local, dest)
            # Clean up empty SCAIL/ subdir if it was created
            subdir = os.path.dirname(hf_local)
            if subdir != ckpt_dir and os.path.isdir(subdir):
                try:
                    os.rmdir(subdir)
                except OSError:
                    pass
        elif os.path.isfile(downloaded) and downloaded != dest:
            os.rename(downloaded, dest)
        log_download_complete("scail", dest)

    # ── SCAIL DiT ──
    if not os.path.isfile(ckpt_path):
        if not _download_from_mirror(_SCAIL_FP8_LOCAL if variant == "fp8" else _SCAIL_BF16_LOCAL,
                                      f"SCAIL DiT ({'FP8 ~16 GB' if variant == 'fp8' else 'BF16 ~33 GB'})"):
            if variant == "fp8":
                _download_from_kijai(_HF_KIJAI_FP8, _KIJAI_SCAIL_FP8, _SCAIL_FP8_LOCAL, "SCAIL DiT FP8 ~16 GB")
            else:
                _download_from_kijai(_HF_KIJAI, _KIJAI_SCAIL_BF16, _SCAIL_BF16_LOCAL, "SCAIL DiT BF16 ~33 GB")

    # ── VAE ──
    if not os.path.isfile(vae_path):
        if not _download_from_mirror(_VAE_LOCAL, "Wan2.1 VAE ~254 MB"):
            _download_from_kijai(_HF_KIJAI, _KIJAI_VAE, _VAE_LOCAL, "Wan2.1 VAE ~254 MB")

    # ── T5 text encoder ──
    if not os.path.isfile(t5_path):
        if not _download_from_mirror(_T5_LOCAL, f"T5 encoder {'FP8 ~6.7 GB' if variant == 'fp8' else 'BF16 ~11.4 GB'}"):
            kijai_t5 = _KIJAI_T5_FP8 if variant == "fp8" else _KIJAI_T5_BF16
            _download_from_kijai(_HF_KIJAI, kijai_t5, _T5_LOCAL,
                                 f"T5 encoder {'FP8 ~6.7 GB' if variant == 'fp8' else 'BF16 ~11.4 GB'}")

    # ── CLIP vision encoder ──
    if not os.path.isfile(clip_path):
        if not _download_from_mirror(_CLIP_LOCAL, "CLIP vision ~1.3 GB"):
            _download_from_kijai(_HF_KIJAI, _KIJAI_CLIP, _CLIP_LOCAL, "CLIP vision ~1.3 GB")


# ======================================================================
# Engine lifecycle
# ======================================================================


def _free_vram() -> None:
    """Free GPU VRAM and system RAM via the shared VRAM manager.

    Aggressive cleanup: evict other synthesizers, unload all ComfyUI
    models (frees system RAM too), empty CUDA cache, gc collect.
    """
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="scail_synthesizer", memory_needed=0)

    gc.collect()
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.unload_all_models()
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass

    gc.collect()
    try:
        torch.cuda.empty_cache()
        free_gb = torch.cuda.mem_get_info()[0] / (1024**3)
        log.info("[SCAIL] GPU free after cleanup: %.2f GiB", free_gb)
    except Exception:
        pass


def load_pipeline(
    ckpt_dir: str | None = None,
    precision: str = "auto",
):
    """Load or return the cached SCAIL pipeline.

    Args:
        ckpt_dir: Path to model checkpoints. ``None`` → auto-detect.
        precision: ``"auto"`` / ``"fp8"`` / ``"bf16"``.

    Returns:
        A ready-to-generate ``SCAILPipeline`` instance.
    """
    global _pipeline, _pipeline_ckpt_dir, _pipeline_variant

    if ckpt_dir is None:
        ckpt_dir = _get_model_dir()

    ckpt_path, variant = _resolve_checkpoint(ckpt_dir, precision)

    # Return cached if same
    if (
        _pipeline is not None
        and _pipeline_ckpt_dir == ckpt_dir
        and _pipeline_variant == variant
    ):
        log.info("SCAIL: using cached pipeline (variant=%s)", variant)
        return _pipeline

    # Variant changed — discard old
    if _pipeline is not None:
        log.info("SCAIL: variant changed (%s → %s), reloading", _pipeline_variant, variant)
        cleanup()

    # Free VRAM
    _free_vram()

    # Ensure weights downloaded
    _ensure_weights_ready(ckpt_dir, precision)

    # Resolve checkpoint again after potential download
    ckpt_path, variant = _resolve_checkpoint(ckpt_dir, precision)

    log.info("SCAIL: loading pipeline from %s (variant=%s)...", ckpt_dir, variant)
    t0 = time.time()

    from .scail import SCAILPipeline
    from .scail.configs import SCAIL_CONFIGS

    config = SCAIL_CONFIGS["SCAIL-14B"]

    # Config JSON path (if present)
    config_json = os.path.join(ckpt_dir, "config.json")

    try:
        from ._vram_utils import get_device
    except ImportError:
        from core._vram_utils import get_device  # type: ignore

    device = get_device()

    pipeline = SCAILPipeline(
        config=config,
        checkpoint_dir=ckpt_dir,
        scail_safetensors_path=ckpt_path,
        scail_config_path=config_json if os.path.exists(config_json) else None,
        device=device,
    )

    _pipeline = pipeline
    _pipeline_ckpt_dir = ckpt_dir
    _pipeline_variant = variant

    elapsed = time.time() - t0
    log.info("SCAIL: pipeline loaded in %.1fs (variant=%s)", elapsed, variant)
    return pipeline


def cleanup() -> None:
    """Release the cached pipeline and free GPU memory."""
    global _pipeline, _pipeline_ckpt_dir, _pipeline_variant

    if _pipeline is None:
        return

    log.info("SCAIL: cleaning up pipeline (variant=%s)...", _pipeline_variant)

    try:
        _pipeline.cleanup()
    except Exception as e:
        log.warning("SCAIL cleanup error (non-fatal): %s", e)

    _pipeline = None
    _pipeline_ckpt_dir = None
    _pipeline_variant = ""

    gc.collect()
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass

    log.info("SCAIL: cleanup complete")


# ======================================================================
# Main generation entry point
# ======================================================================


def generate_video(
    prompt: str,
    reference_image_path: str,
    driving_video_path: str | None = None,
    pose_video_path: str | None = None,
    output_path: str | None = None,
    *,
    steps: int = DEFAULT_STEPS,
    solver: str = DEFAULT_SOLVER,
    guidance: float = DEFAULT_GUIDANCE,
    shift: float = DEFAULT_SHIFT,
    seed: int = DEFAULT_SEED,
    precision: str = "auto",
    ckpt_dir: str | None = None,
) -> tuple[str, str | None]:
    """Generate character animation from reference image + driving video.

    Args:
        prompt: Text describing the character/scene.
        reference_image_path: Path to reference character image.
        driving_video_path: Path to driving video (motion source).
            If provided and no ``pose_video_path``, the driving video
            is used directly as pose input (pre-rendered skeleton expected).
        pose_video_path: Path to pre-rendered skeleton video. If not
            provided, ``driving_video_path`` is used as pose input.
        output_path: Where to save the output. Auto-generated if None.
        steps: Diffusion sampling steps.
        solver: ``"unipc"`` or ``"dpm++"``.
        guidance: CFG scale.
        shift: Flow matching shift (3.0 for 480p, 5.0 for HD).
        seed: Random seed (-1 for random).
        precision: ``"auto"`` / ``"fp8"`` / ``"bf16"``.
        ckpt_dir: Override checkpoint directory.

    Returns:
        (output_video_path, skeleton_video_path_or_None)
    """
    from PIL import Image

    if not os.path.isfile(reference_image_path):
        raise FileNotFoundError(
            f"Reference image not found: {reference_image_path}"
        )

    pose_input = pose_video_path or driving_video_path
    if not pose_input or not os.path.isfile(pose_input):
        raise FileNotFoundError(
            f"Pose/driving video not found: {pose_input}"
        )

    log.info(
        "SCAIL generate: ref=%s, pose=%s, steps=%d, seed=%d",
        reference_image_path, pose_input, steps, seed,
    )

    # Load pipeline
    pipeline = load_pipeline(ckpt_dir=ckpt_dir, precision=precision)

    # Load reference image
    ref_img = Image.open(reference_image_path).convert("RGB")
    from .scail.scail_utils import (
        load_image_to_tensor_chw_normalized,
        load_video_for_pose_sample,
    )
    img_tensor = load_image_to_tensor_chw_normalized(ref_img).squeeze(0)  # [3, H, W]

    # Load pose video
    pose_frames = load_video_for_pose_sample(pose_input)  # [T, H, W, C] uint8
    # Convert to [T, C, H, W] float [0, 1]
    pose_video = pose_frames.permute(0, 3, 1, 2).float() / 255.0

    # Generate
    t0 = time.time()
    video_tensor = pipeline.generate(
        input_prompt=prompt,
        img=img_tensor,
        pose_video=pose_video,
        shift=shift,
        sample_solver=solver,
        sampling_steps=steps,
        guide_scale=guidance,
        seed=seed,
        offload_model=True,
    )
    elapsed = time.time() - t0
    log.info("SCAIL: generation completed in %.1fs", elapsed)

    if video_tensor is None:
        raise RuntimeError("SCAIL generation failed (pipeline returned None)")

    # Build output path
    if output_path is None:
        try:
            import folder_paths  # type: ignore[import-not-found]
            out_dir = folder_paths.get_output_directory()
        except (ImportError, AttributeError):
            out_dir = tempfile.gettempdir()
        output_path = os.path.join(out_dir, f"scail_{seed}.mp4")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Save video
    _save_video_tensor(video_tensor, output_path)
    log.info("SCAIL: saved output to %s", output_path)

    return output_path, None  # No skeleton output yet


def _save_video_tensor(
    video: torch.Tensor,
    output_path: str,
    fps: float = 16.0,
) -> None:
    """Save video tensor [C, T, H, W] in [0, 1] to MP4 via FFmpeg."""
    try:
        from .bin_paths import get_ffmpeg_bin
    except ImportError:
        try:
            from core.bin_paths import get_ffmpeg_bin  # type: ignore
        except ImportError:
            get_ffmpeg_bin = lambda: "ffmpeg"
    ffmpeg = get_ffmpeg_bin()

    # [C, T, H, W] → [T, H, W, C]
    if video.ndim == 4 and video.shape[0] in (3, 4):
        video_np = video[:3].permute(1, 2, 3, 0).cpu().numpy()
    else:
        video_np = video.cpu().numpy()

    video_np = np.clip(video_np * 255, 0, 255).astype(np.uint8)
    n_frames, h, w, c = video_np.shape

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = os.path.join(tmpdir, "video.raw")
        video_np.tofile(raw_path)

        cmd = [
            ffmpeg, "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{w}x{h}",
            "-r", str(fps),
            "-i", raw_path,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "medium",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg encoding failed: {proc.stderr[-500:]}"
            )

    log.info("SCAIL: wrote %d frames to %s", n_frames, output_path)
