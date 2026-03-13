"""AudioX integration for AI-powered audio/music synthesis in FFMPEGA.

Generates audio, music, and performs audio inpainting using the AudioX
model (ICLR 2026) — a unified anything-to-audio framework.

Supports:
- **Text-to-Music**: Generates music from a text description
- **Video-to-Music**: Generates a musical score synced to video
- **Text-to-Audio**: Alternative audio generation backend
- **Audio Inpainting**: Fills gaps or extends existing audio

Architecture:
- In-process inference with GPU↔CPU offloading
- Models cached globally and moved to GPU only during inference
- Uses ``model_manager`` for download guards and mirror support
- Models stored in ``ComfyUI/models/audiox/``
- FFmpeg-based video frame extraction (no decord dependency)
- Memory-efficient model init via ``accelerate``

License note:
    AudioX model weights are CC-BY-NC (non-commercial use only).
    Users download weights on first use and accept that license
    themselves.  See https://huggingface.co/HKUSTAudio/AudioX-MAF
"""

import gc
import logging
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Model directory & checkpoint discovery
# ---------------------------------------------------------------------------

_HF_REPO = "HKUSTAudio/AudioX-MAF"
_MIRROR_REPO = "AEmotionStudio/audiox-models"

# Files needed for AudioX-MAF
# Our mirror serves safetensors; upstream HF has .ckpt/.pth originals.
# _find_or_download_model() probes both formats.
# Note: AudioX-MAF bundles the VAE inside the main model checkpoint.
_MODEL_FILES = {
    "model": "model.safetensors",
    "config": "config.json",
    "synchformer": "synchformer_state_dict.safetensors",
}


def _get_model_dir() -> str:
    """Return the AudioX model directory, creating it if needed."""
    env_dir = os.environ.get("FFMPEGA_AUDIOX_MODEL_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir

    from .platform import get_models_dir
    return get_models_dir("audiox")


def _find_or_download_model(model_key: str) -> str:
    """Find or download an AudioX model file.

    Tries mirror first, then falls back to upstream HuggingFace.

    Args:
        model_key: One of "model", "config", "synchformer".

    Returns:
        Path to the model file.

    Raises:
        RuntimeError: If model downloads are disabled and file not found.
    """
    filename = _MODEL_FILES[model_key]
    model_dir = _get_model_dir()
    local_path = os.path.join(model_dir, filename)

    if os.path.isfile(local_path):
        return local_path

    # Check for alternative format on disk (.ckpt↔.safetensors, .pth↔.safetensors)
    if filename.endswith(".ckpt"):
        alt_name = filename.replace(".ckpt", ".safetensors")
    elif filename.endswith(".safetensors"):
        alt_name = filename.replace(".safetensors", ".ckpt")
        # Also try .pth for synchformer
        pth_name = filename.replace(".safetensors", ".pth")
        pth_path = os.path.join(model_dir, pth_name)
        if os.path.isfile(pth_path):
            return pth_path
    elif filename.endswith(".pth"):
        alt_name = filename.replace(".pth", ".safetensors")
    else:
        alt_name = None

    if alt_name:
        alt_path = os.path.join(model_dir, alt_name)
        if os.path.isfile(alt_path):
            return alt_path

    # Check if synchformer exists in mmaudio dir (shared on-disk file)
    if model_key == "synchformer":
        from .platform import get_models_dir
        mmaudio_synch = os.path.join(
            get_models_dir("mmaudio"), "synchformer_state_dict.safetensors"
        )
        if os.path.isfile(mmaudio_synch):
            log.info("AudioX: reusing Synchformer from mmaudio dir: %s", mmaudio_synch)
            return mmaudio_synch
        mmaudio_synch_pth = os.path.join(
            get_models_dir("mmaudio"), "synchformer_state_dict.pth"
        )
        if os.path.isfile(mmaudio_synch_pth):
            log.info("AudioX: reusing Synchformer from mmaudio dir: %s", mmaudio_synch_pth)
            return mmaudio_synch_pth

    # Guard: check if downloads are allowed
    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed  # type: ignore[no-redef]
    require_downloads_allowed("audiox")

    # Try mirror first
    try:
        from .model_manager import try_mirror_download, download_with_progress
    except ImportError:
        from core.model_manager import try_mirror_download, download_with_progress  # type: ignore[no-redef]

    mirror_path = try_mirror_download(
        model_key="audiox",
        filename=filename,
        local_dir=model_dir,
    )
    if mirror_path:
        _log_license_notice()
        return mirror_path

    # Download from upstream HuggingFace
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise RuntimeError(
            "huggingface_hub is required to download AudioX models. "
            "Install with: pip install huggingface_hub"
        )

    def _download():
        return hf_hub_download(
            repo_id=_HF_REPO,
            filename=filename,
            local_dir=model_dir,
            local_dir_use_symlinks=False,
        )

    downloaded = download_with_progress("audiox", _download, extra=filename)
    if isinstance(downloaded, str) and os.path.isfile(downloaded):
        _log_license_notice()
        return downloaded

    raise RuntimeError(f"Failed to download AudioX {model_key}: {filename}")


_license_logged = False


def _log_license_notice():
    """Log the CC-BY-NC license notice (once per session)."""
    global _license_logged
    if _license_logged:
        return
    _license_logged = True
    log.info(
        "⚠️  AudioX model weights are licensed CC-BY-NC (non-commercial). "
        "By using these models you agree to the license: "
        "https://huggingface.co/HKUSTAudio/AudioX-MAF"
    )


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram():
    """Free all GPU VRAM before loading AudioX."""
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="audiox_synthesizer")


def _get_offload_device():
    """Get the ComfyUI offload device (CPU), or fallback to 'cpu'."""
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        return mm.unet_offload_device()
    except ImportError:
        import torch
        return torch.device("cpu")


# ---------------------------------------------------------------------------
#  Video frame extraction (FFmpeg-based, no decord)
# ---------------------------------------------------------------------------

def _extract_video_frames(
    video_path: str,
    duration: float,
    target_fps: int = 5,
    frame_size: int = 224,
) -> "torch.Tensor":
    """Extract video frames using FFmpeg and return as a tensor.

    Args:
        video_path: Path to the video file.
        duration: Duration in seconds to extract.
        target_fps: Target frames per second.
        frame_size: Width and height to resize frames to.

    Returns:
        Tensor of shape [F, C, H, W] (float32, 0-1 range).
    """
    import torch
    import numpy as np
    from PIL import Image
    import io

    try:
        from .bin_paths import get_ffmpeg_bin
        ffmpeg_bin = get_ffmpeg_bin()
    except ImportError:
        ffmpeg_bin = "ffmpeg"

    target_frames = int(duration * target_fps)

    # Extract frames as raw RGB bytes using FFmpeg
    cmd = [
        ffmpeg_bin, "-y",
        "-i", video_path,
        "-t", str(duration),
        "-vf", f"fps={target_fps},scale={frame_size}:{frame_size}",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo",
        "pipe:1",
    ]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg frame extraction failed: {proc.stderr[-500:]}"
            )

        raw = proc.stdout
        total_bytes = len(raw)
        frame_bytes = frame_size * frame_size * 3  # RGB
        actual_frames = total_bytes // frame_bytes

        if actual_frames == 0:
            raise RuntimeError("FFmpeg produced no frames")

        # Parse raw bytes into numpy array
        frames_np = np.frombuffer(
            raw[:actual_frames * frame_bytes], dtype=np.uint8
        ).reshape(actual_frames, frame_size, frame_size, 3)

        # Convert to tensor [F, C, H, W]
        # Return as uint8 0-255 — AudioX's CLIP conditioner does /255.0 internally
        frames = torch.from_numpy(frames_np).permute(0, 3, 1, 2)

    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg frame extraction timed out")

    # Pad or crop to target frame count (repeat last frame, matching AudioX's adjust_video_duration)
    if frames.shape[0] < target_frames:
        last = frames[-1:].repeat(target_frames - frames.shape[0], 1, 1, 1)
        frames = torch.cat([frames, last], dim=0)
    elif frames.shape[0] > target_frames:
        frames = frames[:target_frames]

    return frames


# ---------------------------------------------------------------------------
#  Cached model state (in-process offloading)
# ---------------------------------------------------------------------------

_models: Optional[dict] = None


def load_models() -> dict:
    """Load and cache all AudioX models.

    On first call, downloads models if needed, frees VRAM from other
    AI models, and loads the AudioX model from config + checkpoint.

    Subsequent calls return the cached models immediately.

    Returns:
        Dict with keys: model, model_config, device, dtype, offload_device.
    """
    global _models
    if _models is not None:
        return _models

    import json
    import torch

    # Device / dtype setup
    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    dtype = torch.float32  # AudioX uses fp32 for precision
    offload_device = _get_offload_device()

    # Resolve model paths (downloads if needed)
    model_path = _find_or_download_model("model")
    config_path = _find_or_download_model("config")
    # Synchformer is needed for video conditioning (loaded lazily)
    _find_or_download_model("synchformer")

    # Free VRAM from other models
    _free_vram()

    log.info("AudioX: loading model (device=%s)", device)

    # Load config
    with open(config_path, "r") as f:
        model_config = json.load(f)

    # ── Create model from config ──────────────────────────────────
    # AudioX is built on stable-audio-tools; the model factory creates
    # the full architecture from the config JSON.
    #
    # AudioX's import chain pulls in `decord` at module level
    # (conditioners → inference/utils → data/utils → decord).
    # We never use decord (our _extract_video_frames uses FFmpeg),
    # so we inject a stub to satisfy the import.
    import sys
    import types
    if "decord" not in sys.modules:
        _decord_stub = types.ModuleType("decord")
        _decord_stub.VideoReader = None
        _decord_stub.cpu = lambda *a, **kw: None
        sys.modules["decord"] = _decord_stub

    try:
        from audiox.models.factory import create_model_from_config
        from audiox.models.utils import load_ckpt_state_dict
    except ImportError:
        try:
            from stable_audio_tools.models.factory import create_model_from_config
            from stable_audio_tools.models.utils import load_ckpt_state_dict
        except ImportError:
            raise ImportError(
                "AudioX is required. Install with: "
                "pip install --no-deps git+https://github.com/ZeyueT/AudioX.git"
            )

    model = create_model_from_config(model_config)

    # Load state dict
    state_dict = load_ckpt_state_dict(model_path)
    model.load_state_dict(state_dict, strict=False)
    del state_dict
    log.info("AudioX: model loaded from %s", os.path.basename(model_path))

    model = model.eval().to(str(offload_device))

    log.info("AudioX: model loaded and cached (offloaded to %s)", offload_device)

    _models = {
        "model": model,
        "model_config": model_config,
        "device": device,
        "dtype": dtype,
        "offload_device": offload_device,
    }
    return _models


def cleanup() -> None:
    """Free GPU memory and clear cached AudioX models."""
    global _models
    if _models is None:
        return

    models = _models
    _models = None

    try:
        offload = models["offload_device"]
        models["model"].to(offload)
    except Exception:
        pass
    del models

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
    log.info("AudioX: models unloaded")


# ---------------------------------------------------------------------------
#  Core inference
# ---------------------------------------------------------------------------

_MAX_DURATION = 10.0  # AudioX max generation duration (seconds)


def generate_music(
    video_path: Optional[str] = None,
    prompt: str = "",
    negative_prompt: str = "",
    duration: Optional[float] = None,
    seed: int = -1,
    cfg_scale: float = 7.0,
    steps: int = 250,
    output_dir: Optional[str] = None,
) -> str:
    """Generate music from video and/or text using AudioX.

    Args:
        video_path: Path to input video (None for text-to-music mode).
        prompt: Text description to guide music generation.
        negative_prompt: What to avoid in generated music.
        duration: Override duration in seconds (max 10s per chunk).
        seed: Random seed (-1 for random).
        cfg_scale: Classifier-free guidance scale.
        steps: Number of diffusion steps.
        output_dir: Where to save output.

    Returns:
        Path to generated audio file (.wav).
    """
    return _generate(
        video_path=video_path,
        prompt=prompt,
        negative_prompt=negative_prompt,
        duration=duration,
        seed=seed,
        cfg_scale=cfg_scale,
        steps=steps,
        output_dir=output_dir,
        task="music",
    )


def generate_audio_audiox(
    video_path: Optional[str] = None,
    prompt: str = "",
    negative_prompt: str = "",
    duration: Optional[float] = None,
    seed: int = -1,
    cfg_scale: float = 7.0,
    steps: int = 250,
    output_dir: Optional[str] = None,
) -> str:
    """Generate audio from video and/or text using AudioX.

    Alternative to MMAudio — slower but different quality character.

    Returns:
        Path to generated audio file (.wav).
    """
    return _generate(
        video_path=video_path,
        prompt=prompt,
        negative_prompt=negative_prompt,
        duration=duration,
        seed=seed,
        cfg_scale=cfg_scale,
        steps=steps,
        output_dir=output_dir,
        task="audio",
    )


def inpaint_audio(
    audio_path: str,
    prompt: str = "",
    negative_prompt: str = "",
    mask_start: float = 0.0,
    mask_end: float = 100.0,
    seed: int = -1,
    cfg_scale: float = 7.0,
    steps: int = 250,
    output_dir: Optional[str] = None,
) -> str:
    """Inpaint or complete audio using AudioX.

    Args:
        audio_path: Path to input audio file.
        prompt: Text description to guide the inpainted audio.
        negative_prompt: What to avoid.
        mask_start: Start of the mask region as percentage (0-100).
        mask_end: End of the mask region as percentage (0-100).
        seed: Random seed (-1 for random).
        cfg_scale: Classifier-free guidance scale.
        steps: Number of diffusion steps.
        output_dir: Where to save output.

    Returns:
        Path to inpainted audio file (.wav).
    """
    # Validate audio path
    if not audio_path or not os.path.isfile(audio_path):
        raise ValueError(f"Audio file not found: {audio_path}")

    import torch
    import numpy as np

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_audiox_")

    # Load models
    models = load_models()
    model = models["model"]
    model_config = models["model_config"]
    device = models["device"]
    offload_device = models["offload_device"]

    sample_rate = model_config.get("sample_rate", 44100)
    sample_size = model_config.get("sample_size", 485100)

    # Move model to GPU
    log.info("AudioX: moving model to %s for inpainting", device)
    model.to(device)

    try:
        # Load the input audio using FFmpeg (avoids torchcodec dependency)
        try:
            from .bin_paths import get_ffmpeg_bin
            ffmpeg_bin = get_ffmpeg_bin()
        except ImportError:
            ffmpeg_bin = "ffmpeg"

        load_cmd = [
            ffmpeg_bin, "-y",
            "-i", audio_path,
            "-f", "f32le",          # 32-bit float PCM
            "-acodec", "pcm_f32le",
            "-ar", str(sample_rate),
            "-ac", "2",             # force stereo
            "pipe:1",
        ]
        proc = subprocess.run(load_cmd, capture_output=True, timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(
                f"FFmpeg audio load failed: {proc.stderr[-300:]}"
            )
        raw = proc.stdout
        import numpy as np
        audio_np = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T  # (2, N)
        audio_tensor = torch.from_numpy(audio_np.copy())
        sr = sample_rate  # already resampled by FFmpeg

        # Ensure stereo
        if audio_tensor.shape[0] == 1:
            audio_tensor = audio_tensor.repeat(2, 1)
        elif audio_tensor.shape[0] > 2:
            audio_tensor = audio_tensor[:2, :]

        # Pad or trim to sample_size
        if audio_tensor.shape[1] < sample_size:
            pad = torch.zeros(2, sample_size - audio_tensor.shape[1])
            audio_tensor = torch.cat([audio_tensor, pad], dim=1)
        else:
            audio_tensor = audio_tensor[:, :sample_size]

        init_audio = (sample_rate, audio_tensor)

        # Build mask args
        mask_args = {
            # Cut-and-paste: which part of init_audio to keep
            "cropfrom": 0.0,          # crop from start of original audio
            "pastefrom": 0.0,         # paste at the start of the output
            "pasteto": mask_start,    # paste up to the mask start (preserved region)
            # Soft mask: where to regenerate
            "maskstart": mask_start,
            "maskend": mask_end,
            "softnessL": 5.0,  # 5% soft edge
            "softnessR": 5.0,
            "marination": 0.0,
        }

        # Prepare conditioning
        # Video prompt: zero tensor signals 'no video' — the CLIP conditioner
        # checks for all-zeros and uses empty_visual_feat instead.
        empty_video = torch.zeros(1, 50, 3, 224, 224)  # 10s × 5fps
        empty_sync = torch.zeros(1, 240, 768)  # Synchformer features

        conditioning = [{
            "text_prompt": prompt,
            "video_prompt": {
                "video_tensors": empty_video,
                "video_sync_frames": empty_sync,
            },
            "audio_prompt": torch.zeros((1, 2, int(sample_rate * _MAX_DURATION))),
            "seconds_start": 0,
            "seconds_total": sample_size / sample_rate,
        }]

        negative_conditioning = None
        if negative_prompt:
            negative_conditioning = [{
                "text_prompt": negative_prompt,
                "video_prompt": {
                    "video_tensors": empty_video,
                    "video_sync_frames": empty_sync,
                },
                "audio_prompt": torch.zeros((1, 2, int(sample_rate * _MAX_DURATION))),
                "seconds_start": 0,
                "seconds_total": sample_size / sample_rate,
            }]

        # Seed
        seed_val = seed if seed != -1 else np.random.randint(0, 2**32 - 1)
        torch.manual_seed(seed_val)

        # Import generation function
        try:
            from audiox.inference.generation import generate_diffusion_cond
        except ImportError:
            from stable_audio_tools.inference.generation import generate_diffusion_cond

        # Generate
        output = generate_diffusion_cond(
            model,
            steps=steps,
            cfg_scale=cfg_scale,
            conditioning=conditioning,
            negative_conditioning=negative_conditioning,
            sample_size=sample_size,
            seed=seed_val,
            device=device,
            init_audio=init_audio,
            mask_args=mask_args,
        )

        # Post-process and save
        output = output.squeeze(0)  # Remove batch dim
        output = output.to(torch.float32)
        max_val = torch.max(torch.abs(output))
        if max_val > 0:
            output = output / max_val
        output = output.clamp(-1.0, 1.0)

        output_path = os.path.join(output_dir, "audiox_inpaint.wav")
        from scipy.io import wavfile
        audio_np = output.cpu().numpy()
        if audio_np.ndim == 2:
            audio_np = audio_np.T
        audio_np = np.clip(audio_np, -1.0, 1.0).astype(np.float32)
        wavfile.write(output_path, sample_rate, audio_np)

        log.info("AudioX: inpainted audio saved to %s", output_path)
        return output_path

    finally:
        _offload_models(models)


def _generate(
    video_path: Optional[str] = None,
    prompt: str = "",
    negative_prompt: str = "",
    duration: Optional[float] = None,
    seed: int = -1,
    cfg_scale: float = 7.0,
    steps: int = 250,
    output_dir: Optional[str] = None,
    task: str = "music",
) -> str:
    """Internal generation function shared by generate_music and generate_audio_audiox."""
    # Validate video path
    if video_path is not None:
        try:
            from .sanitize import validate_video_path
        except ImportError:
            from core.sanitize import validate_video_path  # type: ignore
        video_path = validate_video_path(video_path)

    import torch
    import numpy as np
    from einops import rearrange

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_audiox_")

    # Load or reuse cached models
    models = load_models()
    model = models["model"]
    model_config = models["model_config"]
    device = models["device"]
    offload_device = models["offload_device"]

    sample_rate = model_config.get("sample_rate", 44100)
    sample_size = model_config.get("sample_size", 485100)
    target_fps = model_config.get("video_fps", 5)

    # Move model to GPU for inference
    log.info("AudioX: moving model to %s for %s generation", device, task)
    model.to(device)

    try:
        # ── Determine total duration ──────────────────────────────
        if video_path and os.path.isfile(video_path):
            total_duration = _get_video_duration(video_path) or _MAX_DURATION
            if duration is not None:
                total_duration = min(total_duration, duration)
        else:
            total_duration = duration or _MAX_DURATION
            video_path = None

        # Clamp to max
        total_duration = min(total_duration, _MAX_DURATION)

        log.info(
            "AudioX: generating %.1fs %s (video=%s, prompt=%r)",
            total_duration, task, video_path or "none", prompt,
        )

        # Seed
        seed_val = seed if seed != -1 else np.random.randint(0, 2**32 - 1)
        torch.manual_seed(seed_val)

        # ── Prepare video conditioning ────────────────────────────
        video_tensor = None
        video_sync_frames = None
        if video_path:
            # The CLIP conditioner's Temp_pos_embedding is fixed at (1, 50, 768)
            # = 10s * 5fps. AudioX always uses MODEL_SECONDS=10.0 for conditioning.
            # _extract_video_frames returns uint8 0-255 (CLIP normalizes internally).
            MODEL_SECONDS = 10.0
            video_tensor = _extract_video_frames(
                video_path, MODEL_SECONDS, target_fps=target_fps
            )

            # Encode with Synchformer for MAF models
            synchformer_path = _find_or_download_model("synchformer")
            video_sync_frames = _encode_video_with_synchformer(
                video_path, synchformer_path,
                seconds_start=0, seconds_total=total_duration,
                device=device,
            )

        # ── Build conditioning ────────────────────────────────────
        # Adjust prompt based on task
        if task == "music" and "music" not in prompt.lower():
            text_prompt = f"Generate music for the video. {prompt}" if video_path else prompt
        else:
            text_prompt = prompt

        audio_tensor = torch.zeros((2, int(sample_rate * total_duration)))

        conditioning = [{
            "text_prompt": text_prompt,
            "seconds_start": 0,
            "seconds_total": total_duration,
        }]

        # Add video conditioning if available
        if video_tensor is not None:
            conditioning[0]["video_prompt"] = {
                "video_tensors": video_tensor.unsqueeze(0),
                "video_sync_frames": video_sync_frames,
            }
        else:
            conditioning[0]["video_prompt"] = None

        # Audio prompt (zero tensor when no reference audio)
        conditioning[0]["audio_prompt"] = audio_tensor.unsqueeze(0)

        negative_conditioning = None
        if negative_prompt:
            neg_cond = {
                "text_prompt": negative_prompt,
                "video_prompt": None,
                "audio_prompt": torch.zeros((1, 2, int(sample_rate * total_duration))),
                "seconds_start": 0,
                "seconds_total": total_duration,
            }
            negative_conditioning = [neg_cond]

        # ── Generate ──────────────────────────────────────────────
        try:
            from audiox.inference.generation import generate_diffusion_cond
        except ImportError:
            from stable_audio_tools.inference.generation import generate_diffusion_cond

        output = generate_diffusion_cond(
            model,
            steps=steps,
            cfg_scale=cfg_scale,
            conditioning=conditioning,
            negative_conditioning=negative_conditioning,
            sample_size=sample_size,
            seed=seed_val,
            device=device,
            sampler_type="dpmpp-3m-sde",
            sigma_min=0.3,
            sigma_max=500.0,
        )

        # ── Post-process ──────────────────────────────────────────
        output = rearrange(output, "b d n -> d (b n)")
        output = output.to(torch.float32)
        max_val = torch.max(torch.abs(output))
        if max_val > 0:
            output = output / max_val
        output = output.clamp(-1.0, 1.0)

        # Trim to target duration
        target_samples = int(total_duration * sample_rate)
        if output.shape[1] > target_samples:
            output = output[:, :target_samples]

        # Save as WAV
        output_path = os.path.join(output_dir, f"audiox_{task}.wav")
        from scipy.io import wavfile
        audio_np = output.cpu().numpy()
        if audio_np.ndim == 2:
            audio_np = audio_np.T
        audio_np = np.clip(audio_np, -1.0, 1.0).astype(np.float32)
        wavfile.write(output_path, sample_rate, audio_np)

        log.info("AudioX: %s saved to %s", task, output_path)
        return output_path

    finally:
        _offload_models(models)


def _offload_models(models: dict):
    """Offload models back to CPU after inference."""
    import torch
    offload_device = models["offload_device"]
    log.info("AudioX: offloading model to %s", offload_device)
    try:
        models["model"].to(offload_device)
    except Exception:
        pass
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass


def _get_video_duration(video_path: str) -> Optional[float]:
    """Get video duration using FFmpeg."""
    try:
        from .bin_paths import get_ffmpeg_bin
        ffprobe = get_ffmpeg_bin().replace("ffmpeg", "ffprobe")
    except ImportError:
        ffprobe = "ffprobe"

    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def _encode_video_with_synchformer(
    video_path: str,
    synchformer_path: str,
    seconds_start: float = 0,
    seconds_total: float = 10,
    device: str = "cuda",
) -> "torch.Tensor":
    """Encode video frames with Synchformer for AudioX-MAF conditioning.

    Returns:
        Encoded video sync features tensor.
    """
    import torch
    from torchvision.transforms import v2

    # Load Synchformer directly (bypassing FeaturesUtils which uses
    # torch.load(weights_only=True) and can't handle .safetensors).
    # FeaturesUtils only uses the Synchformer component anyway — VAE/CLIP
    # portions are commented out in AudioX-MAF.
    try:
        from audiox.models.synchformer.synchformer import Synchformer
    except ImportError:
        try:
            from stable_audio_tools.models.synchformer.synchformer import Synchformer
        except ImportError:
            log.warning(
                "AudioX: Synchformer not available — video sync disabled. "
                "Install: pip install --no-deps git+https://github.com/ZeyueT/AudioX.git"
            )
            return None

    synchformer_model = Synchformer()

    # Load weights — handle both .safetensors and .pth/.ckpt formats
    if synchformer_path.endswith(".safetensors"):
        from safetensors.torch import load_file
        state_dict = load_file(synchformer_path)
    else:
        state_dict = torch.load(synchformer_path, map_location="cpu", weights_only=False)

    synchformer_model.load_state_dict(state_dict)
    del state_dict
    synchformer_model = synchformer_model.eval().to(device)

    # Extract frames at 25fps for Synchformer.
    # The conditioner expects exactly 240 sync features = 30 segments × 8.
    # With segment_size=16  and step_size=8: need (30-1)*8+16 = 248 frames min.
    # Use exactly 250 frames (10s × 25fps) to match the model's expectations.
    sync_target_frames = 250  # 10s × 25fps
    sync_video_tensor = _extract_video_frames(
        video_path, _MAX_DURATION, target_fps=25, frame_size=224
    )
    # _extract_video_frames already pads to exactly 250 frames (10s × 25fps)

    # Apply Synchformer preprocessing (matching reference implementations)
    sync_transform = v2.Compose([
        v2.Resize(224, interpolation=v2.InterpolationMode.BICUBIC),
        v2.CenterCrop(224),
        v2.ToDtype(torch.float32, scale=True),   # uint8 0-255 → float32 0-1
        v2.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
    ])
    sync_video = sync_transform(sync_video_tensor).unsqueeze(0).to(device)

    # Encode using Synchformer (replicating FeaturesUtils.encode_video_with_sync)
    from einops import rearrange
    with torch.no_grad():
        b, t, c, h, w = sync_video.shape
        # Partition video into overlapping segments of 16 frames with step 8
        segment_size = 16
        step_size = 8
        num_segments = (t - segment_size) // step_size + 1
        segments = []
        for i in range(num_segments):
            segments.append(sync_video[:, i * step_size:i * step_size + segment_size])
        x = torch.stack(segments, dim=1)  # (B, S, T, C, H, W)
        x = rearrange(x, 'b s t c h w -> (b s) 1 t c h w')
        outputs = []
        for i in range(0, b * num_segments, b):
            outputs.append(synchformer_model(x[i:i + b]))
        x = torch.cat(outputs, dim=0)
        video_sync_frames = rearrange(x, '(b s) 1 t d -> b (s t) d', b=b)

    # Clean up
    del synchformer_model
    import gc as _gc
    _gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return video_sync_frames
