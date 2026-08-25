# coding: utf-8
"""DreamID-Omni synthesizer — identity-preserving talking-head video generation.

Wraps the vendored ``dreamid_omni`` engine and follows the same integration
pattern as ``kiwi_edit_synthesizer.py``:

- Module-level engine cache (``_engine``) to avoid repeated loading
- VRAM management via ``_vram_utils.free_for_module()``
- Model download via ``model_manager`` with mirror-first fallback
- ``generate_video()`` entry point for no-LLM and skill handler callers
- ``cleanup()`` function for VRAM reclamation
"""

from __future__ import annotations

import gc
import logging
import os
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

# HuggingFace repos (official + mirror)
HF_REPO_WAN = "Wan-AI/Wan2.2-TI2V-5B"
HF_REPO_DREAMID = "Guoxu1233/DreamID-Omni"
HF_MIRROR_DREAMID = "AEmotionStudio/dreamid-omni"
HF_MIRROR_WAN = "AEmotionStudio/dreamid-omni-wan"
HF_MIRROR_MMAUDIO = "AEmotionStudio/dreamid-omni-mmaudio"

# Default generation parameters (from inference_r2av.yaml)
DEFAULT_STEPS = 50
DEFAULT_SOLVER = "unipc"
DEFAULT_SHIFT = 5.0
DEFAULT_SEED = 100
DEFAULT_VIDEO_CFG = 3.0
DEFAULT_VIDEO_REF_CFG = 1.5
DEFAULT_AUDIO_CFG = 4.0
DEFAULT_AUDIO_REF_CFG = 2.0
DEFAULT_VIDEO_NEG = "jitter, bad hands, blur, distortion"
DEFAULT_AUDIO_NEG = "robotic, muffled, echo, distorted"

# Resolution presets: name → (H, W)
RESOLUTION_PRESETS: dict[str, tuple[int, int]] = {
    "992x512": (512, 992),
    "1280x704": (704, 1280),
}

# Auto-resolution VRAM thresholds (GiB free)
_VRAM_THRESHOLD_HIGH = 30  # 30 GiB → 1280x704
_VRAM_THRESHOLD_LOW = 20   # 20 GiB → 992x512

# ======================================================================
# Module-level engine cache
# ======================================================================

_engine = None
_engine_ckpt_dir: str | None = None
_engine_variant: str = ""  # tracks which precision variant is loaded


# ======================================================================
# Model directory helpers
# ======================================================================

def _get_model_dir() -> str:
    """Return the model checkpoint directory for DreamID-Omni.

    Tries ComfyUI's ``folder_paths`` first, falls back to
    ``~/.cache/dreamid_omni``.
    """
    try:
        import folder_paths  # type: ignore[import-not-found]
        base = folder_paths.models_dir  # e.g. ComfyUI/models
    except (ImportError, AttributeError):
        base = os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "dreamid_omni")


def _resolve_fusion_checkpoint(ckpt_dir: str, precision: str = "auto") -> tuple[str, str]:
    """Resolve the fusion checkpoint path based on precision preference.

    Returns:
        (checkpoint_path_or_pattern, variant_label)

    For sharded BF16, returns the first shard path and ``"bf16-sharded"`` variant.
    The loader will glob for all shards to merge.
    """
    import glob as _glob

    omni_dir = os.path.join(ckpt_dir, "DreamID_Omni")

    fp8_path = os.path.join(omni_dir, "dreamid_omni_fp8.safetensors")
    bf16_path = os.path.join(omni_dir, "dreamid_omni_bf16.safetensors")
    bf16_shard_pattern = os.path.join(omni_dir, "dreamid_omni_bf16-*-of-*.safetensors")
    fp32_path = os.path.join(omni_dir, "dreamid_omni.safetensors")

    bf16_shards = sorted(_glob.glob(bf16_shard_pattern))

    if precision == "fp8":
        if os.path.isfile(fp8_path):
            return fp8_path, "fp8"
        raise RuntimeError(
            f"FP8 model requested but not found at {fp8_path}. "
            "Run: python scripts/convert_dreamid_omni_precision.py --download --format fp8"
        )
    elif precision == "bf16":
        if os.path.isfile(bf16_path):
            return bf16_path, "bf16"
        if bf16_shards:
            log.info("Detected %d sharded BF16 files", len(bf16_shards))
            return bf16_shards[0], "bf16-sharded"
        if os.path.isfile(fp32_path):
            log.info("BF16 checkpoint not found, falling back to FP32 (will cast at load)")
            return fp32_path, "bf16-from-fp32"
        raise RuntimeError(
            f"BF16 model requested but no checkpoint found in {omni_dir}. "
            "Run: python scripts/convert_dreamid_omni_precision.py --download --format bf16"
        )
    else:  # "auto" — prefer fp8 > bf16 > bf16-sharded > fp32
        if os.path.isfile(fp8_path):
            log.info("Auto-detected FP8 fusion checkpoint at %s", fp8_path)
            return fp8_path, "fp8"
        if os.path.isfile(bf16_path):
            log.info("Auto-detected BF16 fusion checkpoint at %s", bf16_path)
            return bf16_path, "bf16"
        if bf16_shards:
            log.info("Auto-detected %d sharded BF16 files", len(bf16_shards))
            return bf16_shards[0], "bf16-sharded"
        if os.path.isfile(fp32_path):
            log.info("Using FP32 fusion checkpoint (consider converting to FP8/BF16)")
            return fp32_path, "fp32"
        # Nothing found — will need download
        return fp32_path, "fp32"


def _ensure_weights_ready(ckpt_dir: str, fusion_path: str | None = None, precision: str = "auto") -> None:
    """Download model weights if they don't exist yet.

    Precision-aware: skips fusion download if an FP8/BF16 variant already
    exists locally. When downloading, prefers the smallest variant (FP8).
    """
    import glob as _glob

    try:
        from .model_manager import require_downloads_allowed, log_download_start, log_download_complete
    except ImportError:
        from core.model_manager import require_downloads_allowed, log_download_start, log_download_complete  # type: ignore

    omni_dir = os.path.join(ckpt_dir, "DreamID_Omni")
    wan_vae = os.path.join(ckpt_dir, "Wan2.2-TI2V-5B", "Wan2.2_VAE.pth")
    t5_path = os.path.join(ckpt_dir, "Wan2.2-TI2V-5B", "models_t5_umt5-xxl-enc-bf16.pth")
    mmaudio_vae = os.path.join(ckpt_dir, "MMAudio", "ext_weights", "v1-16.pth")

    # Check if ANY fusion checkpoint variant exists locally
    fusion_exists = (
        (fusion_path and os.path.isfile(fusion_path))
        or os.path.isfile(os.path.join(omni_dir, "dreamid_omni_fp8.safetensors"))
        or os.path.isfile(os.path.join(omni_dir, "dreamid_omni_bf16.safetensors"))
        or bool(_glob.glob(os.path.join(omni_dir, "dreamid_omni_bf16-*-of-*.safetensors")))
        or os.path.isfile(os.path.join(omni_dir, "dreamid_omni.safetensors"))
    )

    all_exist = fusion_exists and all(os.path.isfile(p) for p in [wan_vae, t5_path, mmaudio_vae])
    if all_exist:
        log.info("DreamID-Omni: all model files present in %s", ckpt_dir)
        return

    # Need to download — check permission
    require_downloads_allowed("dreamid_omni")

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise RuntimeError(
            "huggingface_hub is required to download DreamID-Omni models. "
            "Install with: pip install huggingface_hub"
        )

    # Download fusion model (prefer FP8 from our mirror — smallest at ~12 GB)
    if not fusion_exists:
        log_download_start("dreamid_omni", "fusion model")
        os.makedirs(omni_dir, exist_ok=True)
        try:
            from huggingface_hub import hf_hub_download
            # Download FP8 from our mirror (12 GB instead of 47 GB FP32)
            target_file = "dreamid_omni_fp8.safetensors"
            hf_hub_download(
                repo_id=HF_MIRROR_DREAMID,
                filename=target_file,
                local_dir=omni_dir,
            )
            log_download_complete("dreamid_omni", os.path.join(omni_dir, target_file))
        except Exception as e:
            log.error("Failed to download DreamID-Omni fusion model: %s", e)
            raise

    # Download Wan2.2 components
    if not os.path.isfile(wan_vae) or not os.path.isfile(t5_path):
        log_download_start("dreamid_omni_wan", "Wan2.2 T5 + VAE")
        wan_dir = os.path.join(ckpt_dir, "Wan2.2-TI2V-5B")
        os.makedirs(wan_dir, exist_ok=True)
        try:
            snapshot_download(
                repo_id=HF_REPO_WAN,
                local_dir=wan_dir,
                allow_patterns=[
                    "Wan2.2_VAE.pth",
                    "models_t5_umt5-xxl-enc-bf16.pth",
                    "google/umt5-xxl/*",
                ],
            )
            log_download_complete("dreamid_omni_wan", wan_dir)
        except Exception as e:
            log.error("Failed to download Wan2.2 components: %s", e)
            raise

    # Download MMAudio VAE weights
    if not os.path.isfile(mmaudio_vae):
        log_download_start("dreamid_omni_mmaudio", "MMAudio VAE")
        mma_dir = os.path.join(ckpt_dir, "MMAudio", "ext_weights")
        os.makedirs(mma_dir, exist_ok=True)
        try:
            from huggingface_hub import hf_hub_download
            for fname in ["ext_weights/v1-16.pth", "ext_weights/best_netG.pt"]:
                try:
                    hf_hub_download(
                        repo_id=HF_MIRROR_MMAUDIO,
                        filename=fname,
                        local_dir=os.path.join(ckpt_dir, "MMAudio"),
                    )
                except Exception:
                    hf_hub_download(
                        repo_id="hkchengrex/MMAudio",
                        filename=fname,
                        local_dir=os.path.join(ckpt_dir, "MMAudio"),
                    )
            log_download_complete("dreamid_omni_mmaudio", mma_dir)
        except Exception as e:
            log.error("Failed to download MMAudio weights: %s", e)
            raise


# ======================================================================
# Resolution helpers
# ======================================================================

def auto_select_resolution() -> tuple[int, int]:
    """Pick resolution preset based on available VRAM."""
    try:
        from ._vram_utils import get_free_memory, get_device
    except ImportError:
        from core._vram_utils import get_free_memory, get_device  # type: ignore

    free_gib = get_free_memory(get_device()) / (1024 ** 3)
    if free_gib >= _VRAM_THRESHOLD_HIGH:
        log.info("DreamID-Omni auto resolution: 1280x704 (%.1f GiB free)", free_gib)
        return RESOLUTION_PRESETS["1280x704"]
    else:
        log.info("DreamID-Omni auto resolution: 992x512 (%.1f GiB free)", free_gib)
        return RESOLUTION_PRESETS["992x512"]


def resolve_resolution(preset: str) -> tuple[int, int]:
    """Resolve a resolution preset name to (H, W)."""
    if preset == "auto":
        return auto_select_resolution()
    if preset in RESOLUTION_PRESETS:
        return RESOLUTION_PRESETS[preset]
    # Fallback
    log.warning("Unknown DreamID-Omni resolution '%s', using 992x512", preset)
    return RESOLUTION_PRESETS["992x512"]


# ======================================================================
# Engine lifecycle
# ======================================================================

def _free_vram() -> None:
    """Free GPU VRAM via the shared VRAM manager.

    Aggressive cleanup matching Flux Klein pattern: cross-synthesizer
    eviction + ComfyUI soft cache + CUDA cache + garbage collection.
    """
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="dreamid_omni_synthesizer", memory_needed=0)

    # Extra aggressive cleanup for low-VRAM systems
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


def load_engine(
    ckpt_dir: str | None = None,
    cpu_offload: bool = True,
    precision: str = "auto",
) -> "DreamIDOmniEngine":
    """Load or return the cached DreamID-Omni engine.

    Args:
        ckpt_dir: Path to model checkpoints. ``None`` → auto-detect.
        cpu_offload: Enable CPU offloading (mandatory for <40 GB VRAM).
        precision: Model precision variant: ``"auto"`` / ``"fp8"`` / ``"bf16"``.
            ``"auto"`` prefers FP8 if available, else BF16, else FP32.

    Returns:
        A ready-to-generate ``DreamIDOmniEngine`` instance.
    """
    global _engine, _engine_ckpt_dir, _engine_variant

    if ckpt_dir is None:
        ckpt_dir = _get_model_dir()

    # Resolve which checkpoint file to use
    fusion_path, variant = _resolve_fusion_checkpoint(ckpt_dir, precision)

    # Return cached engine if same checkpoint dir AND same variant
    if _engine is not None and _engine_ckpt_dir == ckpt_dir and _engine_variant == variant:
        log.info("DreamID-Omni: using cached engine (variant=%s)", variant)
        return _engine

    # Variant changed — discard old engine first
    if _engine is not None:
        log.info("DreamID-Omni: variant changed (%s → %s), reloading", _engine_variant, variant)
        cleanup()

    # Free VRAM for loading
    _free_vram()

    # Ensure weights are downloaded
    _ensure_weights_ready(ckpt_dir, fusion_path=fusion_path, precision=precision)

    log.info("DreamID-Omni: loading engine from %s (variant=%s, cpu_offload=%s)...",
             ckpt_dir, variant, cpu_offload)
    t0 = time.time()

    from omegaconf import OmegaConf
    from .dreamid_omni.dreamid_omni_engine import DreamIDOmniEngine, _PACKAGE_DIR

    # Build config from defaults + overrides
    default_cfg = OmegaConf.load(str(_PACKAGE_DIR / "configs" / "inference" / "inference_r2av.yaml"))

    # target_dtype is for latents/noise/embeddings — always BF16.
    # FP8 only applies to model weights (handled by autocast during forward pass).
    target_dtype = torch.bfloat16

    overrides = OmegaConf.create({
        "ckpt_dir": ckpt_dir,
        "cpu_offload": cpu_offload,
        "fusion_checkpoint_path": fusion_path,
    })
    config = OmegaConf.merge(default_cfg, overrides)

    # Detect GPU device
    try:
        from ._vram_utils import get_device
    except ImportError:
        from core._vram_utils import get_device  # type: ignore

    device = get_device()
    device_idx = device.index if device.index is not None else 0

    engine = DreamIDOmniEngine(config=config, device=device_idx, target_dtype=target_dtype)

    _engine = engine
    _engine_ckpt_dir = ckpt_dir
    _engine_variant = variant

    elapsed = time.time() - t0
    log.info("DreamID-Omni: engine loaded in %.1fs (variant=%s)", elapsed, variant)
    return engine


def cleanup() -> None:
    """Release the cached engine and free GPU memory.

    Follows Flux Klein's aggressive cleanup pattern: release all references,
    empty CUDA cache, run gc, and tell ComfyUI to reclaim memory.
    """
    global _engine, _engine_ckpt_dir, _engine_variant

    if _engine is None:
        return

    log.info("DreamID-Omni: cleaning up engine (variant=%s)...", _engine_variant)

    # Move all components to CPU to free VRAM immediately
    try:
        if hasattr(_engine, "model") and _engine.model is not None:
            _engine.model.cpu()
            del _engine.model
        if hasattr(_engine, "text_model") and _engine.text_model is not None:
            if hasattr(_engine.text_model, "model"):
                _engine.text_model.model.cpu()
            del _engine.text_model
        if hasattr(_engine, "vae_model_video") and _engine.vae_model_video is not None:
            if hasattr(_engine.vae_model_video, "model"):
                _engine.vae_model_video.model.cpu()
            del _engine.vae_model_video
        if hasattr(_engine, "vae_model_audio") and _engine.vae_model_audio is not None:
            _engine.vae_model_audio.cpu()
            del _engine.vae_model_audio
    except Exception as e:
        log.warning("DreamID-Omni cleanup offload error (non-fatal): %s", e)

    _engine = None
    _engine_ckpt_dir = None
    _engine_variant = ""

    gc.collect()
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass
    # ComfyUI soft cache eviction (matches Flux Klein)
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass

    log.info("DreamID-Omni: cleanup complete")


# ======================================================================
# Audio helpers
# ======================================================================

def _audio_dict_to_wav(audio_dict: dict, output_path: str) -> str:
    """Convert a ComfyUI AUDIO dict to a WAV file.

    ComfyUI AUDIO format: ``{"waveform": Tensor[B, C, S], "sample_rate": int}``
    """
    import scipy.io.wavfile as wavfile

    waveform = audio_dict["waveform"]
    sample_rate = audio_dict["sample_rate"]

    # Squeeze to mono if needed
    if waveform.dim() == 3:
        waveform = waveform[0]  # Remove batch
    if waveform.dim() == 2 and waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)  # Mix to mono
    audio_np = waveform.squeeze().cpu().numpy()

    # Normalize to int16
    if audio_np.dtype in (np.float32, np.float64):
        audio_np = np.clip(audio_np, -1.0, 1.0)
        audio_np = (audio_np * 32767).astype(np.int16)

    wavfile.write(output_path, sample_rate, audio_np)
    return output_path


def _tensor_to_image(tensor: torch.Tensor, output_path: str) -> str:
    """Convert a ComfyUI IMAGE tensor [H,W,C] to a PNG file."""
    from PIL import Image

    arr = (tensor.cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
    Image.fromarray(arr).save(output_path)
    return output_path


# ======================================================================
# Main generation entry point
# ======================================================================

def generate_video(
    prompt: str,
    face_image_paths: list[str] | None = None,
    audio_paths: list[str] | None = None,
    output_path: str | None = None,
    *,
    # Generation parameters
    resolution_preset: str = "auto",
    seed: int = DEFAULT_SEED,
    steps: int = DEFAULT_STEPS,
    solver_name: str = DEFAULT_SOLVER,
    shift: float = DEFAULT_SHIFT,
    video_cfg_scale: float = DEFAULT_VIDEO_CFG,
    video_ref_cfg_scale: float = DEFAULT_VIDEO_REF_CFG,
    audio_cfg_scale: float = DEFAULT_AUDIO_CFG,
    audio_ref_cfg_scale: float = DEFAULT_AUDIO_REF_CFG,
    video_negative_prompt: str = DEFAULT_VIDEO_NEG,
    audio_negative_prompt: str = DEFAULT_AUDIO_NEG,
    # Engine options
    ckpt_dir: str | None = None,
    cpu_offload: bool = True,
    precision: str = "auto",
) -> str:
    """Generate a video with identity-preserving speech from face images and audio.

    Args:
        prompt: Text prompt describing the scene/action.
        face_image_paths: Paths to 1-2 reference face images.
        audio_paths: Paths to 1-2 reference audio clips (WAV/MP3/FLAC).
        output_path: Where to save the output video. Auto-generated if None.
        resolution_preset: ``"auto"``, ``"992x512"``, or ``"1280x704"``.
        seed: RNG seed for reproducibility.
        steps: Number of diffusion sampling steps.
        solver_name: Solver algorithm (``"unipc"``, ``"euler"``, ``"dpm++"``)
        shift: Flow matching shift parameter.
        video_cfg_scale: Video classifier-free guidance scale.
        video_ref_cfg_scale: Video reference guidance scale.
        audio_cfg_scale: Audio classifier-free guidance scale.
        audio_ref_cfg_scale: Audio reference guidance scale.
        video_negative_prompt: Negative prompt for video.
        audio_negative_prompt: Negative prompt for audio.
        ckpt_dir: Override checkpoint directory.
        cpu_offload: Enable CPU offloading.

    Returns:
        Path to the generated output video (MP4 with audio).
    """
    if not face_image_paths:
        raise ValueError("DreamID-Omni requires at least one face reference image")
    if not audio_paths:
        raise ValueError("DreamID-Omni requires at least one audio reference clip")

    # Resolve resolution
    video_h, video_w = resolve_resolution(resolution_preset)
    log.info(
        "DreamID-Omni generate: %dx%d, %d steps, seed=%d, solver=%s",
        video_w, video_h, steps, seed, solver_name,
    )

    # Load engine
    engine = load_engine(ckpt_dir=ckpt_dir, cpu_offload=cpu_offload, precision=precision)

    # Prepare image/audio paths (max 2 each for the engine API)
    image0 = face_image_paths[0] if len(face_image_paths) >= 1 else None
    image1 = face_image_paths[1] if len(face_image_paths) >= 2 else None
    audio0 = audio_paths[0] if len(audio_paths) >= 1 else None
    audio1 = audio_paths[1] if len(audio_paths) >= 2 else None

    # Generate
    t0 = time.time()
    result = engine.generate(
        text_prompt=prompt,
        image0_path=image0,
        image1_path=image1,
        audio0_path=audio0,
        audio1_path=audio1,
        video_frame_height_width=(video_h, video_w),
        seed=seed,
        solver_name=solver_name,
        sample_steps=steps,
        shift=shift,
        video_cfg_scale=video_cfg_scale,
        video_ref_cfg_scale=video_ref_cfg_scale,
        audio_cfg_scale=audio_cfg_scale,
        audio_ref_cfg_scale=audio_ref_cfg_scale,
        video_negative_prompt=video_negative_prompt,
        audio_negative_prompt=audio_negative_prompt,
    )
    elapsed = time.time() - t0

    if result is None:
        raise RuntimeError("DreamID-Omni generation failed (engine returned None)")

    generated_video, generated_audio, _ = result
    log.info("DreamID-Omni: generation completed in %.1fs", elapsed)

    # Build output path
    if output_path is None:
        try:
            import folder_paths  # type: ignore[import-not-found]
            out_dir = folder_paths.get_output_directory()
        except (ImportError, AttributeError):
            out_dir = tempfile.gettempdir()
        output_path = os.path.join(out_dir, f"dreamid_omni_{seed}.mp4")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Save video + audio to MP4
    _save_output(generated_video, generated_audio, output_path, video_h, video_w)
    log.info("DreamID-Omni: saved output to %s", output_path)

    return output_path


def _save_output(
    video_array: np.ndarray,
    audio_array: np.ndarray,
    output_path: str,
    height: int,
    width: int,
    fps: float = 16.0,
    sr: int = 16000,
) -> None:
    """Save generated video+audio arrays to an MP4 file.

    Uses FFmpeg for proper MP4 muxing with H.264 video and AAC audio.
    """
    import subprocess

    # Get FFmpeg binary
    try:
        from .bin_paths import get_ffmpeg_bin
    except ImportError:
        try:
            from core.bin_paths import get_ffmpeg_bin  # type: ignore
        except ImportError:
            get_ffmpeg_bin = lambda: "ffmpeg"
    ffmpeg = get_ffmpeg_bin()

    # video_array shape: [C, T, H, W] in [0, 1] float
    # Convert to [T, H, W, C] uint8
    if video_array.ndim == 4 and video_array.shape[0] in (3, 4):
        # C, T, H, W → T, H, W, C
        video_frames = np.transpose(video_array, (1, 2, 3, 0))
    elif video_array.ndim == 4:
        video_frames = video_array
    else:
        raise ValueError(f"Unexpected video array shape: {video_array.shape}")

    video_frames = np.clip(video_frames * 255, 0, 255).astype(np.uint8)
    n_frames = video_frames.shape[0]

    # Write to temp raw files
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write raw video frames as pipe
        raw_video = os.path.join(tmpdir, "video.raw")
        video_frames.tofile(raw_video)

        # Write audio as WAV
        audio_wav = os.path.join(tmpdir, "audio.wav")
        import scipy.io.wavfile as wavfile
        audio_int16 = np.clip(audio_array, -1.0, 1.0)
        audio_int16 = (audio_int16 * 32767).astype(np.int16)
        wavfile.write(audio_wav, sr, audio_int16)

        # FFmpeg: raw video + WAV audio → MP4
        frame_h, frame_w = video_frames.shape[1], video_frames.shape[2]
        cmd = [
            ffmpeg, "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{frame_w}x{frame_h}",
            "-r", str(fps),
            "-i", raw_video,
            "-i", audio_wav,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            log.error("FFmpeg muxing failed: %s", proc.stderr[-500:] if proc.stderr else "")
            raise RuntimeError(f"FFmpeg failed to create output: {proc.stderr[-200:]}")

    log.info("DreamID-Omni: wrote %d frames + audio to %s", n_frames, output_path)
