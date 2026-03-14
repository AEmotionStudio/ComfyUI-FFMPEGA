"""SAM-Audio integration for AI-powered audio separation in FFMPEGA.

Isolates specific sounds from audio mixtures using Meta's SAM-Audio
(Segment Anything Model for Audio) with text, visual, or span prompts.

Supports:
- **Text-prompted separation**: "drums", "vocals", "piano", etc.
- **Visual-prompted separation**: point at objects in video to isolate their sound
- **Span-prompted separation**: specify time ranges for target sounds

Architecture:
- In-process inference with GPU↔CPU offloading
- Models cached globally and moved to GPU only during inference
- Uses ``model_manager`` for download guards and mirror support
- Models stored in ``ComfyUI/models/sam_audio/``
- FFmpeg-based audio I/O (no torchcodec dependency)
- BF16 safetensors model format

License note:
    SAM-Audio model weights are subject to Meta's license terms.
    See https://huggingface.co/facebook/sam-audio-large-tv
"""

import gc
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Model directory & checkpoint discovery
# ---------------------------------------------------------------------------

_MIRROR_REPO = "AEmotionStudio/sam-audio-models"

# ---------------------------------------------------------------------------
#  Model variants — base-tv (3.6 GiB) vs large-tv (6.9 GiB)
# ---------------------------------------------------------------------------

_MODEL_VARIANTS = {
    "base": {
        "hf_repo": "facebook/sam-audio-base-tv",
        "weights": "sam-audio-base-tv-bf16.safetensors",
        "dim": 2048,
        "fp8_scaled": False,
    },
    "base-fp8": {
        "hf_repo": "facebook/sam-audio-base-tv",
        "weights": "sam-audio-base-tv-fp8-scaled.safetensors",
        "dim": 2048,
        "fp8_scaled": True,
    },
    "large": {
        "hf_repo": "facebook/sam-audio-large-tv",
        "weights": "sam-audio-large-tv-bf16.safetensors",
        "dim": 2816,
        "fp8_scaled": False,
    },
    "large-fp8": {
        "hf_repo": "facebook/sam-audio-large-tv",
        "weights": "sam-audio-large-tv-fp8-scaled.safetensors",
        "dim": 2816,
        "fp8_scaled": True,
    },
}

_DEFAULT_VARIANT = "base"

# Max duration the model processes at once (no hard limit, but practical)
_MAX_DURATION = 30.0

# Global model cache
_models: dict = {}
_active_variant: str = ""  # which variant is currently loaded


def _get_models_dir() -> str:
    """Return the sam_audio model directory under ComfyUI/models/."""
    try:
        import folder_paths  # type: ignore
        base = folder_paths.models_dir
    except Exception:
        base = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "..", "models",
        )
    d = os.path.join(base, "sam_audio")
    os.makedirs(d, exist_ok=True)
    return d


def _find_or_download_config(variant: str = _DEFAULT_VARIANT) -> str:
    """Get config.json from the original Facebook HF repo.

    Config must match the model variant exactly (base-tv dim=2048 vs
    large-tv dim=2816), so we always pull it from the upstream repo
    rather than our weights-only mirror.
    """
    vinfo = _MODEL_VARIANTS[variant]
    models_dir = _get_models_dir()
    local_path = os.path.join(models_dir, "config.json")

    if os.path.isfile(local_path):
        # Validate it matches the requested variant
        try:
            with open(local_path) as f:
                cfg = json.load(f)
            dim = cfg.get("transformer", {}).get("dim", 0)
            if dim == vinfo["dim"]:
                return local_path
            log.warning(
                "SAM-Audio: config.json dim=%d doesn't match %s variant "
                "(expected %d), re-downloading...", dim, variant, vinfo["dim"],
            )
        except Exception:
            pass

    # Download from original Facebook repo (tiny file, always accessible)
    hf_repo = vinfo["hf_repo"]
    log.info("SAM-Audio: downloading config.json from %s ...", hf_repo)
    try:
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(
            repo_id=hf_repo,
            filename="config.json",
            local_dir=models_dir,
            local_dir_use_symlinks=False,
        )
        return path
    except Exception as e:
        log.warning("SAM-Audio: HF download failed: %s", e)

    raise FileNotFoundError(
        f"SAM-Audio config.json not found.\n"
        f"  Expected at: {local_path}\n"
        f"  Download from: https://huggingface.co/{vinfo['hf_repo']}"
    )


def _find_or_download_model(variant: str = _DEFAULT_VARIANT) -> str:
    """Find model weights locally or download from mirror.

    Weights come from our ungated mirror (AEmotionStudio), falling
    back to the original Facebook repo.
    """
    vinfo = _MODEL_VARIANTS[variant]
    filename = vinfo["weights"]
    models_dir = _get_models_dir()
    local_path = os.path.join(models_dir, filename)

    if os.path.isfile(local_path):
        return local_path

    # Try downloading
    log.info("SAM-Audio: downloading %s ...", filename)
    try:
        from ..core.model_manager import download_model  # type: ignore
        return download_model(
            filename=filename,
            hf_repo=_MIRROR_REPO,
            fallback_repo=vinfo["hf_repo"],
            target_dir=models_dir,
        )
    except Exception:
        pass

    # Fallback: huggingface_hub
    try:
        from huggingface_hub import hf_hub_download
        for repo in (_MIRROR_REPO, vinfo["hf_repo"]):
            try:
                path = hf_hub_download(
                    repo_id=repo,
                    filename=filename,
                    local_dir=models_dir,
                    local_dir_use_symlinks=False,
                )
                return path
            except Exception:
                continue
    except ImportError:
        pass

    raise FileNotFoundError(
        f"SAM-Audio model file '{filename}' not found.\n"
        f"  Expected at: {local_path}\n"
        f"  Run: python scripts/convert_sam_audio.py to create it, or\n"
        f"  Download from: https://huggingface.co/{_MIRROR_REPO} or {vinfo['hf_repo']}"
    )


# ---------------------------------------------------------------------------
#  Model loading & caching
# ---------------------------------------------------------------------------


def cleanup():
    """Free SAM-Audio model from memory.  Called by _vram_utils when
    other synthesizers need VRAM."""
    unload_models()


def load_models(model_variant: str = _DEFAULT_VARIANT) -> dict:
    """Load SAM-Audio model with GPU↔CPU offloading.

    Args:
        model_variant: "base" (3.6 GiB, default) or "large" (6.9 GiB).

    Returns a dict with keys: model, processor_config, device, offload_device.
    The model is kept on CPU when not actively separating.
    """
    global _models, _active_variant

    if model_variant not in _MODEL_VARIANTS:
        log.warning("SAM-Audio: unknown variant %r, falling back to %s",
                    model_variant, _DEFAULT_VARIANT)
        model_variant = _DEFAULT_VARIANT

    # If a different variant is cached, unload first
    if _models and _active_variant != model_variant:
        log.info("SAM-Audio: variant changed %s → %s, reloading...",
                 _active_variant, model_variant)
        unload_models()

    if _models:
        log.info("SAM-Audio: using cached model (%s)", _active_variant)
        return _models

    import torch
    try:
        from . import _vram_utils
    except ImportError:
        from core import _vram_utils  # type: ignore

    device = _vram_utils.get_device()
    offload_device = "cpu"

    # --- Budget-aware VRAM cleanup before loading ---
    _MODEL_VRAM_BUDGET = int(5.5 * 1024**3)
    try:
        _vram_utils.free_for_module("sam_audio_synthesizer", memory_needed=_MODEL_VRAM_BUDGET)
    except Exception:
        pass

    log.info("SAM-Audio: loading %s model (device=%s)", model_variant, device)

    # Find model files (weights from mirror, config from original FB repo)
    model_path = _find_or_download_model(model_variant)
    config_path = _find_or_download_config(model_variant)

    # Load config
    with open(config_path) as f:
        config_dict = json.load(f)

    # Load model architecture
    from sam_audio.model.config import SAMAudioConfig
    from sam_audio.model.model import SAMAudio

    config = SAMAudioConfig(**config_dict)

    # Disable rankers — they require ImageBind / CLAP / audiobox_aesthetics
    # which we skip.  We always use reranking_candidates=1 so rankers are
    # never called, but the constructor still tries to instantiate them.
    config.visual_ranker = None
    config.text_ranker = None
    # Also disable span_predictor if present (avoids PE-AV pretrained download)
    config.span_predictor = None

    model = SAMAudio(config)

    # Load weights from safetensors
    import torch
    from safetensors.torch import load_file

    state_dict = load_file(model_path)

    # Dequantize FP8 scaled weights if needed
    vinfo = _MODEL_VARIANTS[model_variant]
    if vinfo.get("fp8_scaled", False):
        log.info("SAM-Audio: dequantizing FP8 scaled weights → BF16")
        dequantized = {}
        scale_keys = {k for k in state_dict if k.endswith("._scale")}
        for key in list(state_dict.keys()):
            if key in scale_keys:
                continue  # skip scale tensors, handled with their weight
            scale_key = f"{key}._scale"
            if scale_key in state_dict:
                # FP8 weight: reconstruct as bf16 = fp8.to(bf16) * scale
                fp8_val = state_dict[key]
                scale_val = state_dict[scale_key]
                dequantized[key] = fp8_val.to(torch.bfloat16) * scale_val
            else:
                dequantized[key] = state_dict[key]
        state_dict = dequantized
        del dequantized
        gc.collect()

    model.load_state_dict(state_dict, strict=True)
    del state_dict
    gc.collect()

    model = model.eval().to(offload_device)
    log.info("SAM-Audio: model loaded and cached (offloaded to %s)",
             offload_device)

    # Get processor config (hop_length, sample_rate)
    processor_config = {
        "hop_length": config.audio_codec.hop_length,
        "sample_rate": config.audio_codec.sample_rate,
    }

    _models = {
        "model": model,
        "config": config,
        "processor_config": processor_config,
        "device": device,
        "offload_device": offload_device,
    }
    _active_variant = model_variant
    return _models


def unload_models():
    """Free SAM-Audio model from memory."""
    global _models, _active_variant
    if _models:
        if "model" in _models:
            _models["model"].to("cpu")
            del _models["model"]
        _models.clear()
        _active_variant = ""
        gc.collect()
        try:
            from . import _vram_utils
            _vram_utils.soft_empty_cache()
        except Exception:
            pass
        log.info("SAM-Audio: models unloaded")


# ---------------------------------------------------------------------------
#  FFmpeg-based audio I/O
# ---------------------------------------------------------------------------


def _get_ffmpeg_bin() -> str:
    """Get the FFmpeg binary path."""
    try:
        from .bin_paths import get_ffmpeg_bin
        return get_ffmpeg_bin()
    except ImportError:
        return "ffmpeg"


def _get_ffprobe_bin() -> str:
    """Get the FFprobe binary path."""
    try:
        from .bin_paths import get_ffprobe_bin
        return get_ffprobe_bin()
    except ImportError:
        return "ffprobe"


def _load_audio_ffmpeg(
    audio_path: str, sample_rate: int = 48000
) -> "torch.Tensor":
    """Load audio file via FFmpeg and return as mono tensor.

    Returns tensor of shape (1, N) at the target sample rate.
    """
    import torch
    import numpy as np

    ffmpeg_bin = _get_ffmpeg_bin()

    cmd = [
        ffmpeg_bin, "-y",
        "-i", audio_path,
        "-f", "f32le",
        "-acodec", "pcm_f32le",
        "-ar", str(sample_rate),
        "-ac", "1",  # mono for SAM-Audio
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg audio load failed: {proc.stderr[-500:]}"
        )

    raw = proc.stdout
    audio_np = np.frombuffer(raw, dtype=np.float32)
    audio_tensor = torch.from_numpy(audio_np.copy()).unsqueeze(0)  # (1, N)
    return audio_tensor


def _save_audio_ffmpeg(
    tensor: "torch.Tensor",
    output_path: str,
    sample_rate: int = 48000,
):
    """Save a 1D or 2D tensor as a WAV file via FFmpeg.

    Args:
        tensor: Audio tensor, shape (N,) or (C, N).
        output_path: Where to save the WAV.
        sample_rate: Sample rate.
    """
    import numpy as np

    if tensor.dim() == 2:
        channels = tensor.shape[0]
        audio_np = tensor.cpu().float().numpy()
        # Interleave channels: (C, N) -> (N, C) -> flat
        audio_np = audio_np.T.flatten()
    else:
        channels = 1
        audio_np = tensor.cpu().float().numpy()

    ffmpeg_bin = _get_ffmpeg_bin()
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "f32le",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-i", "pipe:0",
        "-c:a", "pcm_s16le",
        output_path,
    ]
    proc = subprocess.run(
        cmd,
        input=audio_np.tobytes(),
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg audio save failed: {proc.stderr[-500:]}"
        )


def _get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    ffprobe_bin = _get_ffprobe_bin()
    cmd = [
        ffprobe_bin,
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        audio_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
        return float(proc.stdout.strip())
    except Exception:
        return 10.0  # fallback


# ---------------------------------------------------------------------------
#  Core separation API
# ---------------------------------------------------------------------------


def _move_submodule(module, device):
    """Move a submodule to a device, no-op if already there."""
    import itertools
    try:
        first_tensor = next(
            itertools.chain(module.parameters(), module.buffers()), None
        )
        if first_tensor is not None and first_tensor.device != device:
            module.to(device)
    except StopIteration:
        pass


def separate_audio(
    audio_path: str,
    description: str = "",
    video_path: Optional[str] = None,
    predict_spans: bool = False,
    output_dir: Optional[str] = None,
    model_variant: str = _DEFAULT_VARIANT,
) -> dict:
    """Separate audio using SAM-Audio with per-component GPU↔CPU offloading.

    Unlike calling ``model.separate()`` directly (which puts the entire
    ~9.5 GiB model + activations on GPU at once), this reimplements the
    separation pipeline with SAM3-style component offloading:

      1. Text encoder → GPU, encode text, → CPU  (~0.9 GiB freed)
      2. Codec encoder → GPU, encode audio, → CPU  (~0.4 GiB freed)
      3. Transformer stays on GPU for 16 ODE steps  (peak ~5 GiB)
      4. Codec decoder → GPU, decode waveforms, → CPU

    This reduces peak VRAM from ~9.5 GiB to ~5-6 GiB, fitting on 12 GB GPUs.

    Args:
        audio_path: Path to input audio/video file.
        description: Text prompt describing the sound to isolate.
        video_path: Optional video path for visual prompting.
        predict_spans: Whether to auto-detect time ranges for the target.
        output_dir: Where to save output files.

    Returns:
        dict with keys:
            - "target": path to isolated sound WAV
            - "residual": path to everything-else WAV
            - "sample_rate": output sample rate
    """
    import math

    import torch
    from sam_audio.model.model import DFLT_ODE_OPT
    from sam_audio.processor import Batch
    from torchdiffeq import odeint

    if not audio_path or not os.path.isfile(audio_path):
        raise ValueError(f"Audio file not found: {audio_path}")

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_samaudio_")
    os.makedirs(output_dir, exist_ok=True)

    # Load models
    models = load_models(model_variant=model_variant)
    model = models["model"]
    proc_config = models["processor_config"]
    device = models["device"]
    offload_device = models["offload_device"]

    sample_rate = proc_config["sample_rate"]
    hop_length = proc_config["hop_length"]

    try:
        from . import _vram_utils
    except ImportError:
        from core import _vram_utils  # type: ignore

    # Budget-aware VRAM cleanup — we only need ~4 GiB peak now with offloading
    _INFERENCE_BUDGET = int(4.5 * 1024**3)
    _vram_utils.free_for_module("sam_audio_synthesizer", memory_needed=_INFERENCE_BUDGET)

    autocast_device = device.type if hasattr(device, "type") else str(device).split(":")[0]

    try:
        with torch.inference_mode(), torch.amp.autocast(autocast_device, dtype=torch.bfloat16):
            # ---- Load audio via FFmpeg ----
            audio_tensor = _load_audio_ffmpeg(audio_path, sample_rate)
            wav_sizes = torch.tensor([audio_tensor.shape[-1]])
            audios = audio_tensor.unsqueeze(0).to(device)  # (1, 1, N)

            feature_size = math.ceil(audio_tensor.shape[-1] / hop_length)
            sizes = torch.tensor([feature_size])

            audio_pad_mask = (
                torch.arange(feature_size).unsqueeze(0) < sizes.unsqueeze(1)
            ).to(device)

            # ==============================================================
            #  Phase 1: Encode text  (text_encoder on GPU, then offload)
            # ==============================================================
            log.info("SAM-Audio: [phase 1/4] encoding text on %s", device)
            _move_submodule(model.text_encoder, device)
            text_features, text_mask = model.text_encoder(
                [description if description else ""]
            )
            # Keep results on GPU, offload text encoder to free ~0.9 GiB
            text_features = text_features.to(device)
            text_mask = text_mask.to(device) if text_mask is not None else None
            _move_submodule(model.text_encoder, torch.device("cpu"))
            gc.collect()
            _vram_utils.soft_empty_cache()
            log.info("SAM-Audio: text_encoder offloaded, free=%.2f GiB",
                     _vram_utils.get_free_memory(device) / (1024**3))

            # ==============================================================
            #  Phase 2: Encode audio  (codec encoder on GPU, then offload)
            # ==============================================================
            log.info("SAM-Audio: [phase 2/4] encoding audio on %s", device)
            _move_submodule(model.audio_codec.encoder, device)
            _move_submodule(model.audio_codec.quantizer, device)
            audio_features = model.audio_codec(audios).transpose(1, 2)
            audio_features = torch.cat(
                [audio_features, audio_features], dim=2
            )
            # Video features (zeros for text-only mode)
            B, T, _ = audio_features.shape
            masked_video_features = audio_features.new_zeros(
                B, model.vision_encoder.dim, T
            )
            # Offload codec encoder + quantizer.in_proj to CPU (~0.4 GiB)
            _move_submodule(model.audio_codec.encoder, torch.device("cpu"))
            # Keep quantizer on GPU (out_proj needed for decode)
            del audios, audio_tensor
            gc.collect()
            _vram_utils.soft_empty_cache()
            log.info("SAM-Audio: codec encoder offloaded, free=%.2f GiB",
                     _vram_utils.get_free_memory(device) / (1024**3))

            # ==============================================================
            #  Phase 3: ODE separation  (transformer on GPU — main compute)
            # ==============================================================
            log.info("SAM-Audio: [phase 3/4] running ODE separation (%d steps)",
                     int(1.0 / DFLT_ODE_OPT["options"]["step_size"]))
            _move_submodule(model.transformer, device)
            _move_submodule(model.proj, device)
            _move_submodule(model.align_masked_video, device)
            _move_submodule(model.embed_anchors, device)
            _move_submodule(model.memory_proj, device)
            _move_submodule(model.timestep_emb, device)

            C = audio_features.shape[2] // 2
            noise = torch.randn_like(audio_features)

            # Build forward_args (same as model._get_forward_args but inline)
            forward_args = {
                "audio_features": audio_features,
                "text_features": text_features,
                "text_mask": text_mask,
                "masked_video_features": masked_video_features,
                "anchor_ids": None,
                "anchor_alignment": None,
                "audio_pad_mask": audio_pad_mask,
            }

            def vector_field(t, noisy_audio):
                return model.forward(
                    noisy_audio=noisy_audio,
                    time=t.expand(noisy_audio.size(0)),
                    **forward_args,
                )

            states = odeint(
                vector_field,
                noise,
                torch.tensor([0.0, 1.0], device=device),
                **DFLT_ODE_OPT,
            )
            generated_features = states[-1].transpose(1, 2)

            # Free ODE intermediates and forward_args
            del states, noise, forward_args, text_features, text_mask
            del audio_features, masked_video_features, audio_pad_mask
            gc.collect()
            _vram_utils.soft_empty_cache()

            # Offload transformer components to CPU (~3 GiB freed)
            _move_submodule(model.transformer, torch.device("cpu"))
            _move_submodule(model.proj, torch.device("cpu"))
            _move_submodule(model.align_masked_video, torch.device("cpu"))
            _move_submodule(model.embed_anchors, torch.device("cpu"))
            _move_submodule(model.memory_proj, torch.device("cpu"))
            _move_submodule(model.timestep_emb, torch.device("cpu"))
            gc.collect()
            _vram_utils.soft_empty_cache()
            log.info("SAM-Audio: transformer offloaded, free=%.2f GiB",
                     _vram_utils.get_free_memory(device) / (1024**3))

            # ==============================================================
            #  Phase 4: Decode waveforms  (codec decoder on GPU, then offload)
            # ==============================================================
            log.info("SAM-Audio: [phase 4/4] decoding audio on %s", device)
            _move_submodule(model.audio_codec.decoder, device)
            # quantizer.out_proj should still be on GPU (or move it)
            _move_submodule(model.audio_codec.quantizer, device)

            wavs = model.audio_codec.decode(
                generated_features.reshape(2 * B, C, T)
            ).view(B, 2, -1)

            del generated_features
            gc.collect()

            # Compute output sizes and unbatch
            out_sizes = model.audio_codec.feature_idx_to_wav_idx(sizes)
            idxs = torch.zeros(B, dtype=torch.long, device=device)
            target_wavs = model.unbatch(
                wavs[:, 0].view(B, 1, -1), out_sizes
            )
            residual_wavs = model.unbatch(
                wavs[:, 1].view(B, 1, -1), out_sizes
            )
            del wavs

        # ---- Save outputs ----
        from sam_audio.model.model import SeparationResult
        result = SeparationResult(
            target=[wav[idx] for wav, idx in zip(target_wavs, idxs)],
            residual=[wav[idx] for wav, idx in zip(residual_wavs, idxs)],
            noise=torch.empty(0),
        )

        target_path = os.path.join(output_dir, "target.wav")
        residual_path = os.path.join(output_dir, "residual.wav")

        target_wav = result.target[0].cpu()
        residual_wav = result.residual[0].cpu()

        _save_audio_ffmpeg(target_wav, target_path, sample_rate)
        _save_audio_ffmpeg(residual_wav, residual_path, sample_rate)

        log.info("SAM-Audio: separation complete — target=%s, residual=%s",
                 target_path, residual_path)

        return {
            "target": target_path,
            "residual": residual_path,
            "sample_rate": sample_rate,
        }

    finally:
        # Offload entire model back to CPU
        log.info("SAM-Audio: offloading model to %s", offload_device)
        model.to(offload_device)
        gc.collect()
        _vram_utils.soft_empty_cache()
