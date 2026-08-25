"""Foundation-1 integration for AI-powered music sample generation.

Generates production-ready musical loops using the Foundation-1 model
(fine-tuned on stable-audio-open-1.0 by RoyalCities).

Supports:
- **Text-to-Sample**: Generates tempo-synced, key-aware musical loops
- **Structured prompts**: Instrument family, timbre tags, FX, notation
- **Built-in presets**: Quick-start prompts for common instrument types

Architecture:
- In-process inference with GPU↔CPU offloading
- Models cached globally and moved to GPU only during inference
- Uses ``model_manager`` for download guards and mirror support
- Models stored in ``ComfyUI/models/foundation1/``

License note:
    Foundation-1 model weights are under the Stability AI Community
    License (non-commercial or <$1M annual revenue).
    Users download weights on first use and accept that license
    themselves.  See https://huggingface.co/RoyalCities/Foundation-1
"""

import gc
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Model directory & checkpoint discovery
# ---------------------------------------------------------------------------

_HF_REPO = "RoyalCities/Foundation-1"
_MIRROR_REPO = "AEmotionStudio/foundation1-models"

_MODEL_FILES = {
    "model": "Foundation_1.safetensors",
    "config": "model_config.json",
}

# ---------------------------------------------------------------------------
#  Prompt presets
# ---------------------------------------------------------------------------

PRESETS = {
    "warm_pad": (
        "Synth, Pad, Warm, Wide, Lush, Soft Attack, Sustained, "
        "Reverb Hall, Stereo Spread, Legato, Slow Evolving"
    ),
    "synth_lead": (
        "Synth, Lead, Bright, Sharp, Saw, Detune, Portamento, "
        "Delay Ping Pong, Melodic Phrase, Ascending"
    ),
    "bass_loop": (
        "Bass, Synth Bass, Sub, Deep, Round, Mono, "
        "Rhythmic Pattern, Staccato, Eighth Notes, Dry"
    ),
    "string_ensemble": (
        "Strings, Ensemble, Bowed, Rich, Warm, Vibrato, "
        "Legato, Reverb Hall, Sustained, Harmonic Motion"
    ),
    "electric_piano": (
        "Keys, Electric Piano, Rhodes, Warm, Bell-like, "
        "Chorus, Tremolo, Chords, Rhythmic, Soft"
    ),
    "plucked_arp": (
        "Synth, Pluck, Bright, Short Decay, Arpeggio, "
        "Sixteenth Notes, Delay Sync, Stereo, Ascending Descending"
    ),
    "ambient_texture": (
        "Synth, Pad, Atmospheric, Ethereal, Granular, Evolving, "
        "Reverb Large, Delay Long, Slow, Stereo Spread"
    ),
    "brass_stab": (
        "Brass, Trumpet, Bright, Punchy, Staccato, "
        "Rhythmic, Syncopated, Dry, Tight, Accented"
    ),
    "guitar_clean": (
        "Guitar, Electric Guitar, Clean, Warm, Fingerpicked, "
        "Chorus, Reverb Room, Melodic, Arpeggiated, Legato"
    ),
    "mallet_vibes": (
        "Mallet, Vibraphone, Warm, Bell-like, Sustained, "
        "Tremolo, Reverb Plate, Melodic, Jazz, Legato"
    ),
}


def _get_model_dir() -> str:
    """Return the Foundation-1 model directory, creating it if needed."""
    env_dir = os.environ.get("FFMPEGA_FOUNDATION1_MODEL_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir

    from .platform import get_models_dir
    return get_models_dir("foundation1")


def _find_or_download_model(model_key: str) -> str:
    """Find or download a Foundation-1 model file.

    Tries mirror first, then falls back to upstream HuggingFace.

    Args:
        model_key: One of "model", "config".

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

    # Check for alternative format on disk (.ckpt↔.safetensors)
    if filename.endswith(".safetensors"):
        alt_name = filename.replace(".safetensors", ".ckpt")
    elif filename.endswith(".ckpt"):
        alt_name = filename.replace(".ckpt", ".safetensors")
    else:
        alt_name = None

    if alt_name:
        alt_path = os.path.join(model_dir, alt_name)
        if os.path.isfile(alt_path):
            return alt_path

    # Guard: check if downloads are allowed
    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed  # type: ignore[no-redef]
    require_downloads_allowed("foundation1")

    # Try mirror first
    try:
        from .model_manager import try_mirror_download, download_with_progress
    except ImportError:
        from core.model_manager import try_mirror_download, download_with_progress  # type: ignore[no-redef]

    mirror_path = try_mirror_download(
        model_key="foundation1",
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
            "huggingface_hub is required to download Foundation-1 models. "
            "Install with: pip install huggingface_hub"
        )

    def _download():
        return hf_hub_download(
            repo_id=_HF_REPO,
            filename=filename,
            local_dir=model_dir,
            local_dir_use_symlinks=False,
        )

    downloaded = download_with_progress("foundation1", _download, extra=filename)
    if isinstance(downloaded, str) and os.path.isfile(downloaded):
        _log_license_notice()
        return downloaded

    raise RuntimeError(f"Failed to download Foundation-1 {model_key}: {filename}")


_license_logged = False


def _log_license_notice():
    """Log the Stability AI Community License notice (once per session)."""
    global _license_logged
    if _license_logged:
        return
    _license_logged = True
    log.info(
        "⚠️  Foundation-1 model weights are licensed under the "
        "Stability AI Community License (non-commercial or <$1M revenue). "
        "By using these models you agree to the license: "
        "https://huggingface.co/RoyalCities/Foundation-1"
    )


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram():
    """Free all GPU VRAM before loading Foundation-1."""
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="foundation1_synthesizer")


def _get_offload_device():
    """Get the ComfyUI offload device (CPU), or fallback to 'cpu'."""
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        return mm.unet_offload_device()
    except ImportError:
        import torch
        return torch.device("cpu")


# ---------------------------------------------------------------------------
#  Cached model state (in-process offloading)
# ---------------------------------------------------------------------------

_models: Optional[dict] = None


def load_models() -> dict:
    """Load and cache all Foundation-1 models.

    On first call, downloads models if needed, frees VRAM from other
    AI models, and loads the Foundation-1 model from config + checkpoint.

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
    dtype = torch.float16  # Foundation-1 ships as FP16
    offload_device = _get_offload_device()

    # Resolve model paths (downloads if needed)
    model_path = _find_or_download_model("model")
    config_path = _find_or_download_model("config")

    # Free VRAM from other models
    _free_vram()

    log.info("Foundation-1: loading model (device=%s)", device)

    # Load config
    with open(config_path, "r") as f:
        model_config = json.load(f)

    # ── Create model from config ──────────────────────────────────
    # Foundation-1 is built on stable-audio-tools (vanilla, not AudioX)
    try:
        from stable_audio_tools.models.factory import create_model_from_config
        from stable_audio_tools.models.utils import load_ckpt_state_dict
    except ImportError:
        raise ImportError(
            "stable-audio-tools is required for Foundation-1. "
            "Install with: pip install --no-deps stable-audio-tools"
        )

    model = create_model_from_config(model_config)

    # Load state dict
    state_dict = load_ckpt_state_dict(model_path)
    model.load_state_dict(state_dict, strict=False)
    del state_dict
    log.info("Foundation-1: model loaded from %s", os.path.basename(model_path))

    model = model.eval().to(str(offload_device))

    log.info("Foundation-1: model loaded and cached (offloaded to %s)", offload_device)

    _models = {
        "model": model,
        "model_config": model_config,
        "device": device,
        "dtype": dtype,
        "offload_device": offload_device,
    }
    return _models


def cleanup() -> None:
    """Free GPU memory and clear cached Foundation-1 models."""
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
    log.info("Foundation-1: models unloaded")


# ---------------------------------------------------------------------------
#  Core inference
# ---------------------------------------------------------------------------

def _resolve_prompt(
    prompt: str,
    preset: str = "",
    bpm: int = 0,
    bars: int = 0,
    key: str = "",
) -> str:
    """Build the final prompt from user text, preset, and music params.

    If a preset is provided and prompt is empty, the preset tags are used.
    If both are provided, they are combined (user prompt takes precedence).
    BPM, bars, and key are appended when provided.

    Args:
        prompt: Free-text user prompt.
        preset: Preset name from PRESETS dict.
        bpm: Beats per minute (0 = not specified).
        bars: Number of bars (0 = not specified).
        key: Musical key (e.g. "C major", "A minor").

    Returns:
        The resolved prompt string.
    """
    parts = []

    # Preset tags
    if preset and preset in PRESETS:
        parts.append(PRESETS[preset])

    # User prompt
    if prompt.strip():
        parts.append(prompt.strip())

    # Music structure params
    if bpm > 0:
        parts.append(f"{bpm} BPM")
    if bars > 0:
        parts.append(f"{bars} Bars")
    if key.strip():
        parts.append(key.strip())

    return ", ".join(parts) if parts else "Synth, Pad, Warm, Sustained"


def generate_sample(
    prompt: str = "",
    negative_prompt: str = "",
    preset: str = "",
    bpm: int = 0,
    bars: int = 0,
    key: str = "",
    duration: Optional[float] = None,
    seed: int = -1,
    cfg_scale: float = 7.0,
    steps: int = 100,
    output_dir: Optional[str] = None,
) -> str:
    """Generate a music sample/loop using Foundation-1.

    Args:
        prompt: Text description to guide generation.
        negative_prompt: What to avoid in generated audio.
        preset: Preset name from PRESETS dict (combined with prompt).
        bpm: Beats per minute (0 = model default).
        bars: Number of bars (0 = model default).
        key: Musical key/scale (e.g. "C major").
        duration: Duration in seconds (None = auto from BPM/bars or default).
        seed: Random seed (-1 for random).
        cfg_scale: Classifier-free guidance scale.
        steps: Number of diffusion steps.
        output_dir: Where to save output.

    Returns:
        Path to generated audio file (.wav).
    """
    import torch
    import numpy as np

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_foundation1_")

    # Build final prompt
    text_prompt = _resolve_prompt(prompt, preset, bpm, bars, key)

    # Load or reuse cached models
    models = load_models()
    model = models["model"]
    model_config = models["model_config"]
    device = models["device"]
    offload_device = models["offload_device"]

    sample_rate = model_config.get("sample_rate", 44100)
    sample_size = model_config.get("sample_size", 2646000)  # ~60s at 44100

    # ── Determine duration ────────────────────────────────────────
    if duration is None:
        # Auto-calculate from BPM/bars if provided
        if bpm > 0 and bars > 0:
            # 4/4 time: bars * 4 beats / bpm * 60 seconds
            duration = (bars * 4 / bpm) * 60.0
        elif bpm > 0:
            # BPM set but no bars → default 8 bars
            duration = (8 * 4 / bpm) * 60.0
        elif bars > 0:
            # Bars set but no BPM → default 120 BPM
            duration = (bars * 4 / 120) * 60.0
        else:
            # No constraints → default 8 bars at 120 BPM = 16s
            # This matches Foundation-1's training distribution
            duration = 16.0

    # Compute sample count for the requested duration
    requested_samples = int(duration * sample_rate)
    # Clamp to model's max sample_size
    effective_samples = min(requested_samples, sample_size)

    log.info(
        "Foundation-1: generating %.1fs sample (prompt=%r, bpm=%s, bars=%s, key=%r, "
        "requested_samples=%d, effective_samples=%d, model_max=%d)",
        effective_samples / sample_rate, text_prompt, bpm or "auto", bars or "auto", key,
        requested_samples, effective_samples, sample_size,
    )

    # Move model to GPU for inference
    log.info("Foundation-1: moving model to %s for generation", device)
    model.to(device)

    try:
        # Seed
        seed_val = seed if seed != -1 else np.random.randint(0, 2**32 - 1)
        torch.manual_seed(seed_val)

        # ── Build conditioning ────────────────────────────────────
        conditioning = [{
            "prompt": text_prompt,
            "seconds_start": 0,
            "seconds_total": effective_samples / sample_rate,
        }]

        negative_conditioning = None
        if negative_prompt:
            negative_conditioning = [{
                "prompt": negative_prompt,
                "seconds_start": 0,
                "seconds_total": effective_samples / sample_rate,
            }]

        # Import generation function
        from stable_audio_tools.inference.generation import generate_diffusion_cond

        # Generate
        output = generate_diffusion_cond(
            model,
            steps=steps,
            cfg_scale=cfg_scale,
            conditioning=conditioning,
            negative_conditioning=negative_conditioning,
            sample_size=effective_samples,
            seed=seed_val,
            device=device,
        )

        # Post-process and save
        output = output.squeeze(0)  # Remove batch dim
        output = output.to(torch.float32)
        max_val = torch.max(torch.abs(output))
        if max_val > 0:
            output = output / max_val
        output = output.clamp(-1.0, 1.0)

        output_path = os.path.join(output_dir, "foundation1_sample.wav")
        from scipy.io import wavfile
        audio_np = output.cpu().numpy()
        if audio_np.ndim == 2:
            audio_np = audio_np.T  # (channels, samples) → (samples, channels)
        audio_np = np.clip(audio_np, -1.0, 1.0).astype(np.float32)
        wavfile.write(output_path, sample_rate, audio_np)

        log.info("Foundation-1: sample saved to %s (seed=%d)", output_path, seed_val)
        return output_path

    finally:
        _offload_models(models)


def _offload_models(models: dict) -> None:
    """Move models back to CPU to free VRAM."""
    try:
        offload_device = models["offload_device"]
        models["model"].to(offload_device)
    except Exception:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    gc.collect()


def style_transfer_audio(
    input_audio_path: str,
    prompt: str = "",
    negative_prompt: str = "",
    preset: str = "",
    bpm: int = 0,
    bars: int = 0,
    key: str = "",
    init_noise_level: float = 0.7,
    seed: int = -1,
    cfg_scale: float = 7.0,
    steps: int = 100,
    output_dir: Optional[str] = None,
) -> str:
    """Style-transfer an existing audio file using Foundation-1.

    Loads the input audio, encodes it into the model's latent space,
    adds noise at ``init_noise_level``, then denoises conditioned on
    the text prompt.  Lower noise levels preserve more of the original;
    higher levels allow more creative reinterpretation.

    Args:
        input_audio_path: Path to the source audio file (.wav, .mp3, .flac, etc.).
        prompt: Text description to guide the style transfer.
        negative_prompt: What to avoid.
        preset: Optional PRESETS name to combine with prompt.
        bpm: BPM tag appended to prompt (0 = skip).
        bars: Bars tag appended to prompt (0 = skip).
        key: Musical key tag (e.g. "C major").
        init_noise_level: How much noise to add to the source audio.
            0.0 = keep original (no change),
            0.3 = subtle variation,
            0.7 = strong restyling (default),
            1.0 = fully regenerate (ignore source).
        seed: Random seed (-1 for random).
        cfg_scale: Classifier-free guidance scale.
        steps: Number of diffusion steps.
        output_dir: Where to save result.

    Returns:
        Path to the style-transferred audio file (.wav).
    """
    import torch
    import numpy as np

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_f1_transfer_")

    # Build prompt
    text_prompt = _resolve_prompt(prompt, preset, bpm, bars, key)

    # Load input audio
    try:
        import torchaudio
    except ImportError:
        raise ImportError("torchaudio is required for style transfer")

    waveform, sr = torchaudio.load(input_audio_path)
    # Ensure float32
    waveform = waveform.to(torch.float32)

    # Load models
    models = load_models()
    model = models["model"]
    model_config = models["model_config"]
    device = models["device"]
    offload_device = models["offload_device"]

    sample_rate = model_config.get("sample_rate", 44100)

    log.info(
        "Foundation-1: style transfer (prompt=%r, noise_level=%.2f, source=%s)",
        text_prompt, init_noise_level, os.path.basename(input_audio_path),
    )

    # Move model to GPU
    log.info("Foundation-1: moving model to %s for style transfer", device)
    model.to(device)

    try:
        seed_val = seed if seed != -1 else np.random.randint(0, 2**32 - 1)
        torch.manual_seed(seed_val)

        # Determine output length from source audio
        source_duration = waveform.shape[-1] / sr
        sample_size = model_config.get("sample_size", 2646000)
        requested_samples = int(source_duration * sample_rate)
        effective_samples = min(requested_samples, sample_size)

        # Build conditioning
        conditioning = [{
            "prompt": text_prompt,
            "seconds_start": 0,
            "seconds_total": effective_samples / sample_rate,
        }]

        negative_conditioning = None
        if negative_prompt:
            negative_conditioning = [{
                "prompt": negative_prompt,
                "seconds_start": 0,
                "seconds_total": effective_samples / sample_rate,
            }]

        from stable_audio_tools.inference.generation import generate_diffusion_cond

        # Pass source audio as init_audio tuple (sample_rate, tensor)
        init_audio = (int(sr), waveform)

        output = generate_diffusion_cond(
            model,
            steps=steps,
            cfg_scale=cfg_scale,
            conditioning=conditioning,
            negative_conditioning=negative_conditioning,
            sample_size=effective_samples,
            seed=seed_val,
            device=device,
            init_audio=init_audio,
            init_noise_level=init_noise_level,
        )

        # Post-process
        output = output.squeeze(0).to(torch.float32)
        max_val = torch.max(torch.abs(output))
        if max_val > 0:
            output = output / max_val
        output = output.clamp(-1.0, 1.0)

        output_path = os.path.join(output_dir, "foundation1_transfer.wav")
        from scipy.io import wavfile
        audio_np = output.cpu().numpy()
        if audio_np.ndim == 2:
            audio_np = audio_np.T
        audio_np = np.clip(audio_np, -1.0, 1.0).astype(np.float32)
        wavfile.write(output_path, sample_rate, audio_np)

        log.info("Foundation-1: style transfer saved to %s (seed=%d)", output_path, seed_val)
        return output_path

    finally:
        _offload_models(models)

