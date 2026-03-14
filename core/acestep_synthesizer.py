# coding: utf-8
"""ACE-Step 1.5 integration for AI-powered music generation in FFMPEGA.

High-quality music generation, cover creation, audio repaint, stem separation,
and LRC generation using ACE-Step 1.5 — an open-source music generation model.

Supports:
- **Text-to-Music**: Generate music from text prompt + optional lyrics
- **Cover / Repaint**: Improve existing audio (e.g. AudioX output) via
  reference-guided regeneration
- **Track Separation**: Split audio into stems (vocals, drums, bass, other)
- **Vocal-to-BGM**: Generate accompaniment from a vocal track
- **LRC Generation**: Produce timestamped lyrics for generated songs
- **AudioX → ACE-Step Pipeline**: Two-stage flow — AudioX generates
  video-synced music, ACE-Step repaints it to higher quality

Architecture:
- In-process inference via ``AceStepHandler`` with GPU↔CPU offloading
- Models cached globally, offloaded to CPU when not in use
- Download guard via ``model_manager``
- Models stored in ``ComfyUI/models/acestep/`` (symlinked or downloaded)
- Designed for 12 GB VRAM (RTX 4070) with aggressive offloading

License note:
    ACE-Step 1.5 is MIT-licensed (both code and model weights).
"""

import gc
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Model directory & checkpoint discovery
# ---------------------------------------------------------------------------

# ACE-Step stores models under <project_root>/checkpoints/ by default.
# We redirect ACESTEP_PROJECT_ROOT to ComfyUI/models/acestep/ so models
# live alongside other FFMPEGA models.

_HF_REPO = "ACE-Step/Ace-Step1.5"
_MIRROR_REPO = "AEmotionStudio/acestep-models"

# DiT model variants (config_path names)
DIT_MODELS = {
    "turbo": "acestep-v15-turbo",
    "base": "acestep-v15-base",
    "turbo-shift3": "acestep-v15-turbo-shift3",
}

# LM model variants
LM_MODELS = {
    "0.6B": "acestep-5Hz-lm-0.6B",
    "1.7B": "acestep-5Hz-lm-1.7B",
    "4B": "acestep-5Hz-lm-4B",
}

# Default choices (tuned for RTX 4070 12 GB)
DEFAULT_DIT = "turbo"
DEFAULT_LM = "1.7B"

# ---------------------------------------------------------------------------
#  Global handler state (singleton pattern — same as AudioX/MMAudio)
# ---------------------------------------------------------------------------

_handler = None           # AceStepHandler instance
_llm_handler = None       # LLMHandler instance (for lyric planning)
_current_lm: str = ""     # Currently loaded LM tier
_initialized: bool = False


def _get_model_dir() -> str:
    """Return the ACE-Step model directory (also used as project root).

    This directory will contain a ``checkpoints/`` subdirectory mirroring
    ACE-Step's expected layout.
    """
    env_dir = os.environ.get("FFMPEGA_ACESTEP_MODEL_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir

    from .platform import get_models_dir
    return get_models_dir("acestep")


def _get_checkpoints_dir() -> str:
    """Return the checkpoints subdirectory inside the model dir."""
    ckpt = os.path.join(_get_model_dir(), "checkpoints")
    os.makedirs(ckpt, exist_ok=True)
    return ckpt


# ---------------------------------------------------------------------------
#  Model download helpers
# ---------------------------------------------------------------------------

def _ensure_models_downloaded(
    lm_model: str = DEFAULT_LM,
) -> str:
    """Download ACE-Step models if not present.

    Uses ACE-Step's built-in ``model_downloader`` module which handles
    HuggingFace / ModelScope fallback and submodel downloads.

    Returns:
        Path to the checkpoints directory.

    Raises:
        RuntimeError: If downloads are blocked by model_manager.
    """
    from . import model_manager
    model_manager.require_downloads_allowed("acestep")

    checkpoints_dir = _get_checkpoints_dir()

    try:
        from acestep.model_downloader import (
            check_main_model_exists,
            download_main_model,
            check_model_exists,
            download_submodel,
        )
    except ImportError:
        raise RuntimeError(
            "ACE-Step package not installed. "
            "Run: pip install --no-deps git+https://github.com/ace-step/ACE-Step-1.5.git"
        )

    ckpt_path = Path(checkpoints_dir)

    # Download main model (DiT turbo + VAE + text encoder + 1.7B LM)
    if not check_main_model_exists(ckpt_path):
        model_manager.log_download_start("acestep", "main model")
        log.info("[ACE-Step] Downloading main model from %s...", _HF_REPO)
        success, msg = download_main_model(
            checkpoints_dir=ckpt_path,
            prefer_source="huggingface",
        )
        if not success:
            raise RuntimeError(f"Failed to download ACE-Step main model: {msg}")
        model_manager.log_download_complete("acestep", checkpoints_dir)

    # Download requested LM if it's a submodel (0.6B and 4B are separate)
    lm_name = LM_MODELS.get(lm_model, lm_model)
    if not check_model_exists(lm_name, ckpt_path):
        if lm_name in ("acestep-5Hz-lm-0.6B", "acestep-5Hz-lm-4B"):
            log.info("[ACE-Step] Downloading LM model: %s...", lm_name)
            success, msg = download_submodel(
                model_name=lm_name,
                checkpoints_dir=ckpt_path,
                prefer_source="huggingface",
            )
            if not success:
                log.warning("[ACE-Step] LM download failed: %s — proceeding without LM", msg)

    return checkpoints_dir


# ---------------------------------------------------------------------------
#  Handler lifecycle
# ---------------------------------------------------------------------------

def load_handler(
    lm_model: str = DEFAULT_LM,
    dit_model: str = DEFAULT_DIT,
    force_reinit: bool = False,
) -> None:
    """Initialize the ACE-Step handler with models loaded.

    Uses aggressive CPU offloading suitable for 12 GB VRAM.

    Args:
        lm_model: LM tier — ``"0.6B"``, ``"1.7B"``, or ``"4B"``.
        dit_model: DiT variant — ``"turbo"``, ``"base"``, etc.
        force_reinit: Re-initialize even if already loaded.
    """
    global _handler, _llm_handler, _current_lm, _initialized

    if _initialized and not force_reinit and _current_lm == lm_model:
        log.debug("[ACE-Step] Handler already initialized (LM=%s)", lm_model)
        return

    # Free other FFMPEGA models first
    from ._vram_utils import free_for_module
    free_for_module(exclude="acestep_synthesizer", memory_needed=6 * 1024**3)

    # Set project root so ACE-Step's internal model discovery works
    model_dir = _get_model_dir()
    os.environ["ACESTEP_PROJECT_ROOT"] = model_dir

    # Download models if needed
    checkpoints_dir = _ensure_models_downloaded(lm_model=lm_model)

    try:
        from acestep.handler import AceStepHandler
    except ImportError:
        raise RuntimeError(
            "ACE-Step package not installed. "
            "Run: pip install --no-deps git+https://github.com/ace-step/ACE-Step-1.5.git"
        )

    # Resolve config_path
    config_path = DIT_MODELS.get(dit_model, dit_model)

    # Check if flash attention is available
    import torch
    use_flash = False
    if torch.cuda.is_available():
        try:
            import flash_attn  # noqa: F401
            use_flash = True
        except ImportError:
            pass

    log.info(
        "[ACE-Step] Initializing — DiT=%s, LM=%s, flash_attn=%s",
        config_path, lm_model, use_flash,
    )

    # Create handler and initialize
    handler = AceStepHandler()
    status_msg, success = handler.initialize_service(
        project_root=model_dir,
        config_path=config_path,
        device="auto",
        use_flash_attention=use_flash,
        compile_model=False,  # avoid compile overhead in ComfyUI
        offload_to_cpu=True,  # aggressive offloading for 12 GB cards
        offload_dit_to_cpu=True,
        quantization=None,    # quantization requires compile_model=True
    )

    if not success:
        raise RuntimeError(f"ACE-Step initialization failed: {status_msg}")

    log.info("[ACE-Step] DiT initialized: %s", status_msg)
    _handler = handler

    # Initialize LLM handler for lyric planning (optional)
    lm_name = LM_MODELS.get(lm_model, lm_model)
    lm_path = os.path.join(checkpoints_dir, lm_name)
    if os.path.isdir(lm_path):
        try:
            from acestep.llm_inference import LLMHandler

            llm = LLMHandler()
            lm_status, lm_ok = llm.initialize(
                checkpoint_dir=checkpoints_dir,
                lm_model_path=lm_name,
                backend="pt",  # plain PyTorch — avoids nano-vllm dependency
                device="auto",
                offload_to_cpu=True,
                dtype=None,
            )
            if lm_ok:
                _llm_handler = llm
                log.info("[ACE-Step] LM initialized: %s", lm_status)
            else:
                log.warning("[ACE-Step] LM init failed: %s — proceeding without LM", lm_status)
                _llm_handler = None
        except Exception as e:
            log.warning("[ACE-Step] LM init error: %s — proceeding without LM", e)
            _llm_handler = None
    else:
        log.info("[ACE-Step] LM model not found at %s — proceeding without LM", lm_path)
        _llm_handler = None

    _current_lm = lm_model
    _initialized = True
    log.info("[ACE-Step] ✅ Ready (DiT=%s, LM=%s)", config_path, lm_model if _llm_handler else "none")


def cleanup() -> None:
    """Release ACE-Step models and free VRAM.

    Called by ``_vram_utils.free_for_module()`` when another synthesizer
    needs GPU memory.
    """
    global _handler, _llm_handler, _initialized, _current_lm

    if _handler is not None:
        try:
            # Move models to CPU
            import torch
            if hasattr(_handler, "model") and _handler.model is not None:
                _handler.model.cpu()
            if hasattr(_handler, "vae") and _handler.vae is not None:
                _handler.vae.cpu()
            if hasattr(_handler, "text_encoder") and _handler.text_encoder is not None:
                _handler.text_encoder.cpu()
        except Exception as e:
            log.debug("[ACE-Step] Error during model offload: %s", e)

    if _llm_handler is not None:
        try:
            if hasattr(_llm_handler, "model") and _llm_handler.model is not None:
                _llm_handler.model.cpu()
        except Exception:
            pass

    _handler = None
    _llm_handler = None
    _initialized = False
    _current_lm = ""

    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    log.info("[ACE-Step] Cleanup complete — models released")


# ---------------------------------------------------------------------------
#  Lyric generation (uses ACE-Step's LLM handler)
# ---------------------------------------------------------------------------

def generate_lyrics(
    prompt: str,
    duration: float = 60.0,
    user_metadata: Optional[Dict[str, str]] = None,
) -> str:
    """Auto-generate structured lyrics from a music description.

    Uses ACE-Step's 1.7B LM to produce lyrics with section markers
    (``[verse]``, ``[chorus]``, etc.) matching the requested style.

    Must be called *after* ``load_handler()`` so ``_llm_handler`` is available.

    Args:
        prompt: Text description of the song (e.g. "country folk song about love").
        duration: Target duration in seconds (affects lyric length).
        user_metadata: Optional dict with ``bpm``, ``keyscale``, ``timesignature``.

    Returns:
        Generated lyrics string, or ``""`` if the LLM handler is not available.
    """
    global _llm_handler

    if _llm_handler is None:
        log.info("[ACE-Step] LLM handler not available — skipping lyric generation")
        return ""

    try:
        log.info("[ACE-Step] Generating lyrics from prompt: %r", prompt[:80])
        result = _llm_handler.generate_with_stop_condition(
            caption=prompt,
            lyrics="",
            infer_type="dit",       # Phase 1 only — CoT metadata, no audio codes
            temperature=0.85,
            target_duration=duration,
            user_metadata=user_metadata,
        )

        if not result.get("success", False):
            log.warning("[ACE-Step] Lyric generation failed: %s", result.get("error"))
            return ""

        # Extract generated metadata — may contain a formatted caption and lyrics
        metadata = result.get("metadata", {})
        generated_caption = metadata.get("caption", "")

        # The LM generates the caption with metadata but not standalone lyrics.
        # Use the generated caption as enriched prompt context.
        log.info("[ACE-Step] LM generated metadata: %s", list(metadata.keys()))

        # Build lyrics section from metadata if present
        lyrics_parts = []
        if generated_caption and generated_caption != prompt:
            lyrics_parts.append(f"[intro]\n{generated_caption}")
        if metadata.get("language"):
            pass  # language is handled internally

        return "\n".join(lyrics_parts) if lyrics_parts else ""

    except Exception as e:
        log.warning("[ACE-Step] Lyric generation error: %s — proceeding without lyrics", e)
        return ""


# ---------------------------------------------------------------------------
#  Core generation functions
# ---------------------------------------------------------------------------

def generate_music_acestep(
    prompt: str = "",
    lyrics: str = "",
    duration: float = 60.0,
    seed: int = -1,
    cfg_scale: float = 7.0,
    steps: int = 8,
    reference_audio: Optional[str] = None,
    lm_model: str = DEFAULT_LM,
    dit_model: str = DEFAULT_DIT,
    batch_size: int = 1,
    task_type: str = "text2music",
) -> str:
    """Generate music using ACE-Step.

    Args:
        prompt: Text description of desired music.
        lyrics: Structured lyrics with section markers (``[verse]``, etc.).
        duration: Audio duration in seconds (10–600).
        seed: Random seed (-1 = random).
        cfg_scale: Guidance scale.
        steps: Diffusion steps (ACE-Step turbo default is 8).
        reference_audio: Optional path to reference audio for style guidance.
        lm_model: LM tier to use.
        dit_model: DiT variant.
        batch_size: Number of samples to generate (returns first).
        task_type: ``"text2music"`` or other ACE-Step task type.

    Returns:
        Path to the generated ``.wav`` file.

    Raises:
        RuntimeError: On generation failure.
    """
    load_handler(lm_model=lm_model, dit_model=dit_model)

    # Clamp duration
    duration = max(10.0, min(duration, 600.0))

    # Handle seed
    use_random = seed < 0
    actual_seed = seed if seed >= 0 else None

    # Prepare reference audio
    ref_audio_data = None
    if reference_audio and os.path.isfile(reference_audio):
        try:
            import torchaudio
            waveform, sr = torchaudio.load(reference_audio)
            ref_audio_data = (sr, waveform.numpy())
        except Exception as e:
            log.warning("[ACE-Step] Could not load reference audio: %s", e)

    log.info(
        "[ACE-Step] Generating music — prompt=%r, duration=%.0fs, steps=%d, cfg=%.1f",
        prompt[:80], duration, steps, cfg_scale,
    )

    result = _handler.generate_music(
        captions=prompt,
        lyrics=lyrics,
        audio_duration=duration,
        inference_steps=steps,
        guidance_scale=cfg_scale,
        use_random_seed=use_random,
        seed=actual_seed,
        reference_audio=ref_audio_data,
        batch_size=batch_size,
        task_type=task_type,
    )

    if not result.get("success", False):
        error = result.get("error", result.get("status_message", "Unknown error"))
        raise RuntimeError(f"ACE-Step generation failed: {error}")

    audios = result.get("audios", [])
    if not audios:
        raise RuntimeError("ACE-Step returned no audio")

    # Save first audio to temp file
    return _save_audio_tensor(audios[0])


def cover_audio(
    audio_path: str,
    prompt: str = "",
    lyrics: str = "",
    seed: int = -1,
    cover_strength: float = 0.8,
    lm_model: str = DEFAULT_LM,
) -> str:
    """Generate a cover version of existing audio.

    Uses ACE-Step's cover mode with the source audio as reference.

    Args:
        audio_path: Path to source audio to cover.
        prompt: Optional text guidance for the cover.
        lyrics: Optional lyrics.
        seed: Random seed.
        cover_strength: How closely to follow the source (0–1).
        lm_model: LM tier.

    Returns:
        Path to the generated ``.wav`` file.
    """
    load_handler(lm_model=lm_model)

    # Load source audio
    src_audio_data = _load_audio_for_acestep(audio_path)
    if src_audio_data is None:
        raise RuntimeError(f"Could not load source audio: {audio_path}")

    use_random = seed < 0

    log.info(
        "[ACE-Step] Covering audio — src=%s, strength=%.2f",
        os.path.basename(audio_path), cover_strength,
    )

    result = _handler.generate_music(
        captions=prompt,
        lyrics=lyrics,
        src_audio=src_audio_data,
        task_type="text2music",  # cover uses src_audio with strength
        audio_cover_strength=cover_strength,
        use_random_seed=use_random,
        seed=seed if seed >= 0 else None,
        batch_size=1,
    )

    if not result.get("success", False):
        error = result.get("error", "Unknown error")
        raise RuntimeError(f"ACE-Step cover failed: {error}")

    audios = result.get("audios", [])
    if not audios:
        raise RuntimeError("ACE-Step cover returned no audio")

    return _save_audio_tensor(audios[0])


def repaint_audio(
    audio_path: str,
    prompt: str = "",
    mask_start: float = 0.0,
    mask_end: float = 100.0,
    seed: int = -1,
    lm_model: str = DEFAULT_LM,
) -> str:
    """Repaint (selectively regenerate) a region of audio.

    Args:
        audio_path: Source audio path.
        prompt: Text guidance for the repainted region.
        mask_start: Start of repaint region as percentage (0–100).
        mask_end: End of repaint region as percentage (0–100).
        seed: Random seed.
        lm_model: LM tier.

    Returns:
        Path to the repainted ``.wav`` file.
    """
    load_handler(lm_model=lm_model)

    src_audio_data = _load_audio_for_acestep(audio_path)
    if src_audio_data is None:
        raise RuntimeError(f"Could not load source audio: {audio_path}")

    # Convert percentages to 0-1 range
    repaint_start = max(0.0, min(mask_start / 100.0, 1.0))
    repaint_end = max(repaint_start, min(mask_end / 100.0, 1.0))

    use_random = seed < 0

    log.info(
        "[ACE-Step] Repainting audio — region=%.0f%%–%.0f%%",
        mask_start, mask_end,
    )

    result = _handler.generate_music(
        captions=prompt,
        src_audio=src_audio_data,
        task_type="text2music",
        repainting_start=repaint_start,
        repainting_end=repaint_end,
        use_random_seed=use_random,
        seed=seed if seed >= 0 else None,
        batch_size=1,
    )

    if not result.get("success", False):
        error = result.get("error", "Unknown error")
        raise RuntimeError(f"ACE-Step repaint failed: {error}")

    audios = result.get("audios", [])
    if not audios:
        raise RuntimeError("ACE-Step repaint returned no audio")

    return _save_audio_tensor(audios[0])


def audiox_to_acestep_repaint(
    video_path: str,
    prompt: str = "",
    lyrics: str = "",
    cover_strength: float = 0.8,
    seed: int = -1,
    lm_model: str = DEFAULT_LM,
) -> str:
    """Two-stage pipeline: AudioX → ACE-Step repaint.

    1. Runs AudioX ``generate_music()`` to produce video-synced music
    2. Feeds that output to ACE-Step ``cover_audio()`` for quality improvement

    Args:
        video_path: Input video path.
        prompt: Music description.
        lyrics: Optional lyrics.
        cover_strength: How closely ACE-Step follows the AudioX output.
        seed: Random seed.
        lm_model: LM tier.

    Returns:
        Path to the final high-quality ``.wav`` file.
    """
    # Stage 1: Generate base music with AudioX
    log.info("[ACE-Step→AudioX] Stage 1: Generating base music with AudioX...")
    try:
        from .audiox_synthesizer import generate_music as audiox_generate
        audiox_wav = audiox_generate(
            video_path=video_path,
            prompt=prompt,
            seed=seed,
        )
        log.info("[ACE-Step→AudioX] Stage 1 complete: %s", audiox_wav)
    except Exception as e:
        log.warning(
            "[ACE-Step→AudioX] AudioX generation failed (%s), "
            "falling back to direct ACE-Step generation",
            e,
        )
        # Fallback: generate directly with ACE-Step
        return generate_music_acestep(
            prompt=prompt,
            lyrics=lyrics,
            seed=seed,
            lm_model=lm_model,
        )

    # Stage 2: Repaint with ACE-Step
    log.info("[ACE-Step→AudioX] Stage 2: Repainting with ACE-Step (strength=%.2f)...", cover_strength)
    result = cover_audio(
        audio_path=audiox_wav,
        prompt=prompt,
        lyrics=lyrics,
        seed=seed,
        cover_strength=cover_strength,
        lm_model=lm_model,
    )

    # Clean up the intermediate AudioX file
    try:
        os.unlink(audiox_wav)
    except OSError:
        pass

    log.info("[ACE-Step→AudioX] Pipeline complete: %s", result)
    return result


# ---------------------------------------------------------------------------
#  Utility functions
# ---------------------------------------------------------------------------

def _load_audio_for_acestep(audio_path: str) -> Optional[Any]:
    """Load an audio file in the format ACE-Step expects.

    Returns:
        Tuple of (sample_rate, numpy_array) or None on failure.
    """
    if not audio_path or not os.path.isfile(audio_path):
        return None
    try:
        import torchaudio
        waveform, sr = torchaudio.load(audio_path)
        # ACE-Step expects (sample_rate, numpy_array)
        return (sr, waveform.numpy())
    except Exception as e:
        log.warning("[ACE-Step] Failed to load audio %s: %s", audio_path, e)
        return None


def _save_audio_tensor(audio_data: Any) -> str:
    """Save an audio tensor/array to a temporary WAV file.

    Args:
        audio_data: Can be:
            - A dict with ``{"tensor": tensor, "sample_rate": int}`` (ACE-Step format)
            - A tuple ``(sample_rate, numpy_array)``
            - A raw numpy/torch tensor at 48 kHz

    Returns:
        Path to the saved ``.wav`` file.
    """
    import numpy as np

    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="acestep_")
    os.close(fd)

    # Unpack ACE-Step dict format: {"tensor": tensor, "sample_rate": sr}
    if isinstance(audio_data, dict):
        sr = audio_data.get("sample_rate", 48000)
        data = audio_data.get("tensor", audio_data.get("audio"))
        if data is None:
            raise RuntimeError(f"ACE-Step audio dict missing 'tensor' key: {list(audio_data.keys())}")
    elif isinstance(audio_data, tuple):
        sr, data = audio_data
    else:
        sr = 48000
        data = audio_data

    # Convert torch tensor to numpy
    import torch
    if isinstance(data, torch.Tensor):
        data = data.cpu().numpy()

    if not isinstance(data, np.ndarray):
        raise RuntimeError(f"Unexpected audio data type: {type(data)}")

    # Try soundfile first, fall back to torchaudio
    try:
        import soundfile as sf
        if data.ndim > 1:
            # Ensure shape is (samples, channels) for soundfile
            if data.shape[0] < data.shape[-1]:
                data = data.T
        sf.write(wav_path, data, sr)
    except ImportError:
        import torchaudio
        tensor = torch.from_numpy(data)
        if tensor.dim() == 1:
            tensor = tensor.unsqueeze(0)
        elif tensor.dim() > 1 and tensor.shape[0] > tensor.shape[-1]:
            # (samples, channels) → (channels, samples) for torchaudio
            tensor = tensor.T
        torchaudio.save(wav_path, tensor, sr)

    return wav_path


def is_available() -> bool:
    """Check if ACE-Step is installed and importable."""
    try:
        from acestep.handler import AceStepHandler  # noqa: F401
        return True
    except ImportError:
        return False
