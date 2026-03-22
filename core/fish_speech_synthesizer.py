"""Fish Speech S2 Pro integration for AI-powered TTS in FFMPEGA.

Generates speech audio from text with fine-grained prosody and emotion
control using Fish Audio's S2 Pro model (Dual-AR architecture).

Supports:
- **Text-to-Speech**: Natural speech from text with 80+ languages
- **Long-form TTS**: Sentence-aware chunking for documents up to 5000+ words
- **Voice cloning**: Clone any voice from 10-30s reference audio
- **Emotion/prosody tags**: Inline control via ``[whisper]``, ``[excited]``, etc.
  Also supports free-form tags like ``[whisper in small voice]``
- **Multi-speaker**: ``<|speaker:0|>``, ``<|speaker:1|>`` for multi-voice output
- **FP8 inference**: Per-row symmetric FP8 for ~12GB VRAM on RTX 4070+

Architecture:
- In-process inference with GPU↔CPU offloading
- Models cached globally and moved to GPU only during inference
- FP8 weights dequantized to BF16 at load time (pure PyTorch, no external libs)
- Voice reference library in ``ComfyUI/models/fish_speech/voices/``
- Models stored in ``ComfyUI/models/fish_speech/``

License note:
    Fish Speech S2 Pro model weights are under the Fish Audio Research
    License.  Research and non-commercial use is free.  Commercial use
    requires a separate license from Fish Audio (business@fish.audio).
    See https://huggingface.co/fishaudio/s2-pro/blob/main/LICENSE.md

    Built with Fish Audio.
"""

import gc
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Constants & curated emotion tags
# ---------------------------------------------------------------------------

# Curated emotion/prosody tags for the UI dropdown.
# Fish Speech supports 15K+ tags inline — including free-form text descriptions
# like [whisper in small voice] or [professional broadcast tone].
# These are the most useful curated tags from the upstream README.
EMOTION_TAGS = [
    "",  # none / no tag
    "[happy]",
    "[sad]",
    "[angry]",
    "[excited]",
    "[whisper]",
    "[shouting]",
    "[laughing]",
    "[laughing tone]",
    "[chuckling]",
    "[chuckle]",
    "[crying]",
    "[singing]",
    "[pause]",
    "[short pause]",
    "[breath]",
    "[inhale]",
    "[exhale]",
    "[emphasis]",
    "[sigh]",
    "[tsk]",
    "[nervous]",
    "[calm]",
    "[serious]",
    "[cheerful]",
    "[sarcastic]",
    "[surprised]",
    "[shocked]",
    "[disgusted]",
    "[fearful]",
    "[tender]",
    "[delight]",
    "[monotone]",
    "[interrupting]",
    "[fast]",
    "[slow]",
    "[loud]",
    "[soft]",
    "[low voice]",
    "[volume up]",
    "[volume down]",
    "[echo]",
    "[panting]",
    "[clearing throat]",
    "[audience laughter]",
    "[with strong accent]",
]

# ---------------------------------------------------------------------------
#  Model repos & file layout
# ---------------------------------------------------------------------------

_HF_REPO_FP8 = "AEmotionStudio/fish-speech-s2-pro-fp8"
_HF_REPO_BF16 = "AEmotionStudio/fish-speech-s2-pro"
_HF_UPSTREAM = "fishaudio/s2-pro"

_MODEL_FILES = {
    "model": "model.safetensors",
    "codec": "codec.pth",
    "config": "config.json",
    "tokenizer": "tokenizer.json",
    "tokenizer_config": "tokenizer_config.json",
}

_MODEL_VARIANTS = {
    "fp8": {
        "hf_repo": _HF_REPO_FP8,
        "fallback_repo": _HF_UPSTREAM,
        "vram_budget": int(12 * 1024**3),
    },
    "bf16": {
        "hf_repo": _HF_REPO_BF16,
        "fallback_repo": _HF_UPSTREAM,
        "vram_budget": int(22 * 1024**3),
    },
}

_DEFAULT_VARIANT = "bf16"

# ---------------------------------------------------------------------------
#  Global cache
# ---------------------------------------------------------------------------

_models: dict = {}
_active_variant: str = ""
_license_logged = False


# ---------------------------------------------------------------------------
#  License notice
# ---------------------------------------------------------------------------


def _log_license_notice():
    """Log the Fish Audio license notice once per session."""
    global _license_logged
    if _license_logged:
        return
    log.info(
        "🐟 Fish Speech S2 Pro — Built with Fish Audio.\n"
        "   Model weights are under the Fish Audio Research License.\n"
        "   Research and non-commercial use is free.\n"
        "   Commercial use requires a license from Fish Audio.\n"
        "   See: https://huggingface.co/fishaudio/s2-pro/blob/main/LICENSE.md"
    )
    _license_logged = True


# ---------------------------------------------------------------------------
#  Model directory & voice library
# ---------------------------------------------------------------------------


def _get_model_dir(variant: str = _DEFAULT_VARIANT) -> str:
    """Return the fish_speech model directory for the given variant."""
    from .platform import get_models_dir
    subdir = f"fish_speech/s2-pro-{variant}"
    d = get_models_dir(subdir)
    os.makedirs(d, exist_ok=True)
    return d


def _get_voices_dir() -> str:
    """Return the voice reference library directory."""
    from .platform import get_models_dir
    d = get_models_dir("fish_speech/voices")
    os.makedirs(d, exist_ok=True)
    return d


def list_voices() -> list[str]:
    """Scan the voices directory and return available voice names.

    Supports:
    - ``voices/name.wav`` → voice name is "name"
    - ``voices/name/reference.wav`` → voice name is "name"

    Returns:
        Sorted list of voice names (without extensions).
    """
    voices_dir = _get_voices_dir()
    names = set()

    for entry in os.scandir(voices_dir):
        if entry.is_file() and entry.name.lower().endswith(
            (".wav", ".mp3", ".flac", ".ogg")
        ):
            names.add(Path(entry.name).stem)
        elif entry.is_dir():
            # Check if directory contains any audio files
            for sub in os.scandir(entry.path):
                if sub.is_file() and sub.name.lower().endswith(
                    (".wav", ".mp3", ".flac", ".ogg")
                ):
                    names.add(entry.name)
                    break

    return sorted(names)


def _get_voice_audio_path(voice_name: str) -> Optional[str]:
    """Resolve a voice name to its reference audio file path."""
    voices_dir = _get_voices_dir()

    # Check direct file: voices/name.wav
    for ext in (".wav", ".mp3", ".flac", ".ogg"):
        path = os.path.join(voices_dir, f"{voice_name}{ext}")
        if os.path.isfile(path):
            return path

    # Check directory: voices/name/reference.wav
    voice_dir = os.path.join(voices_dir, voice_name)
    if os.path.isdir(voice_dir):
        for entry in os.scandir(voice_dir):
            if entry.is_file() and entry.name.lower().endswith(
                (".wav", ".mp3", ".flac", ".ogg")
            ):
                return entry.path

    return None


def _get_voice_transcript(voice_name: str) -> Optional[str]:
    """Get the optional transcript for a voice reference.

    Looks for transcript.txt in the voice directory.
    """
    voices_dir = _get_voices_dir()
    voice_dir = os.path.join(voices_dir, voice_name)
    if os.path.isdir(voice_dir):
        txt_path = os.path.join(voice_dir, "transcript.txt")
        if os.path.isfile(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                return f.read().strip()
    return None


# ---------------------------------------------------------------------------
#  Model download
# ---------------------------------------------------------------------------


def _find_or_download_file(
    filename: str, variant: str = _DEFAULT_VARIANT
) -> str:
    """Find a model file locally or download it."""
    vinfo = _MODEL_VARIANTS[variant]
    model_dir = _get_model_dir(variant)
    local_path = os.path.join(model_dir, filename)

    if os.path.isfile(local_path):
        return local_path

    # Guard: check if downloads are allowed
    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed  # type: ignore

    require_downloads_allowed("fish_speech")

    # Try mirror download first
    try:
        from .model_manager import try_mirror_download
    except ImportError:
        from core.model_manager import try_mirror_download  # type: ignore

    mirror_path = try_mirror_download(
        model_key="fish_speech",
        filename=filename,
        local_dir=model_dir,
    )
    if mirror_path:
        return mirror_path

    # Fallback: huggingface_hub
    log.info("Fish Speech: downloading %s from %s ...", filename, vinfo["hf_repo"])
    try:
        from huggingface_hub import hf_hub_download

        for repo in (vinfo["hf_repo"], vinfo.get("fallback_repo", "")):
            if not repo:
                continue
            try:
                path = hf_hub_download(
                    repo_id=repo,
                    filename=filename,
                    local_dir=model_dir,
                    local_dir_use_symlinks=False,
                )
                return path
            except Exception:
                continue
    except ImportError:
        pass

    raise FileNotFoundError(
        f"Fish Speech model file '{filename}' not found.\n"
        f"  Expected at: {local_path}\n"
        f"  Download from: https://huggingface.co/{vinfo['hf_repo']}"
    )


# ---------------------------------------------------------------------------
#  FP8 native inference (stays in FP8 — half the VRAM)
# ---------------------------------------------------------------------------
# Based on ComfyUI-WanVideoWrapper's fp8_optimization.py
# (ComfyUI's and MinusZoneAI's fp8_linear optimization)
#
# Instead of dequantizing FP8 → BF16 (doubling model size), we keep
# weights in FP8 and use torch._scaled_mm for native FP8 matmul.
# Requires CUDA compute capability >= 8.9 (RTX 4000 series and up).


def _fp8_linear_forward(cls, base_dtype, input):
    """FP8 linear forward using torch._scaled_mm.

    Keeps weights in FP8, casts input to FP8, and uses hardware-
    accelerated scaled matmul.  Output is in *base_dtype* (BF16).
    """
    import torch

    weight_dtype = cls.weight.dtype
    if weight_dtype in [torch.float8_e4m3fn, torch.float8_e5m2]:
        if len(input.shape) == 3:
            input_shape = input.shape

            scale_weight = getattr(cls, "scale_weight", None)
            if scale_weight is None:
                scale_weight = torch.ones(
                    (), device=input.device, dtype=torch.float32
                )
            else:
                scale_weight = scale_weight.to(input.device)

            # Clamp + cast input to FP8 (e4m3fn — required for matmul)
            input = torch.clamp(input, min=-448, max=448, out=input)
            inn = (
                input.reshape(-1, input_shape[2])
                .to(torch.float8_e4m3fn)
                .contiguous()
            )

            bias = cls.bias.to(base_dtype) if cls.bias is not None else None

            # Determine scale mode: TensorWise (scalar) vs RowWise (per-channel)
            if scale_weight.dim() == 0 or scale_weight.numel() == 1:
                # TensorWise: both scales are singletons
                scale_input = torch.ones(
                    (), device=input.device, dtype=torch.float32
                )
                scale_b = scale_weight.reshape(())
            else:
                # RowWise: scale_a=(M,1), scale_b=(1,N)
                scale_input = torch.ones(
                    (inn.shape[0], 1), device=input.device, dtype=torch.float32
                )
                scale_b = scale_weight.reshape(1, -1).contiguous()

            o = torch._scaled_mm(
                inn,
                cls.weight.t(),
                out_dtype=base_dtype,
                bias=bias,
                scale_a=scale_input,
                scale_b=scale_b,
            )
            return o.reshape((-1, input_shape[1], cls.weight.shape[0]))
        else:
            return cls.original_forward(input.to(base_dtype))
    else:
        return cls.original_forward(input)


def _convert_fp8_linear(module, base_dtype, scale_weight_keys=None):
    """Patch all nn.Linear in *module* to use native FP8 matmul.

    Stores per-layer scale_weight attributes and monkey-patches forward()
    to use ``_fp8_linear_forward``.

    Args:
        module: The nn.Module whose Linear layers to patch.
        base_dtype: Output dtype for matmul (e.g. torch.bfloat16).
        scale_weight_keys: Dict mapping ``"layer.name.scale_weight"``
            to scale tensors.  Extracted from the state dict's
            ``"layer.name.weight.scale"`` keys.
    """
    import torch.nn as nn

    patched = 0
    for name, submodule in module.named_modules():
        if isinstance(submodule, nn.Linear):
            if scale_weight_keys is not None:
                scale_key = f"{name}.scale_weight"
                if scale_key in scale_weight_keys:
                    setattr(
                        submodule,
                        "scale_weight",
                        scale_weight_keys[scale_key].float(),
                    )
            original_forward = submodule.forward
            setattr(submodule, "original_forward", original_forward)
            setattr(
                submodule,
                "forward",
                lambda input, m=submodule: _fp8_linear_forward(
                    m, base_dtype, input
                ),
            )
            patched += 1

    log.info("Fish Speech: patched %d Linear layers for native FP8 matmul", patched)


def _extract_scale_weights(state_dict: dict) -> dict:
    """Extract scale keys from state dict and reformat for convert_fp8_linear.

    Fish Speech FP8 models use ``layer.weight.scale`` keys.
    convert_fp8_linear expects ``layer.scale_weight`` keys.

    Returns:
        Dict mapping ``"layer.scale_weight"`` → scale tensor.
        Scale keys are removed from state_dict in-place.
    """
    scale_weights = {}
    scale_keys = [k for k in state_dict if k.endswith(".weight.scale")]
    for sk in scale_keys:
        # "layers.0.attention.wq.weight.scale" → "layers.0.attention.wq.scale_weight"
        layer_name = sk.removesuffix(".weight.scale")
        scale_weights[f"{layer_name}.scale_weight"] = state_dict.pop(sk)
    # Also handle bare ".scale" keys (some FP8 formats)
    bare_scales = [k for k in state_dict if k.endswith(".scale") and k not in scale_weights]
    for sk in bare_scales:
        weight_key = sk.removesuffix(".scale")
        layer_name = weight_key.removesuffix(".weight")
        scale_weights[f"{layer_name}.scale_weight"] = state_dict.pop(sk)
    return scale_weights


def _supports_fp8_matmul() -> bool:
    """Check if the GPU supports native FP8 matmul (compute capability >= 8.9)."""
    import torch
    if not torch.cuda.is_available():
        return False
    cap = torch.cuda.get_device_capability()
    return cap[0] > 8 or (cap[0] == 8 and cap[1] >= 9)


def _remap_state_dict_keys(state_dict: dict) -> dict:
    """Remap FP8 state dict keys to match DualARTransformer parameter names.

    The drbaph/s2-pro-fp8 checkpoint uses a different key naming convention:
      - ``text_model.model.X`` → ``X``  (main LLM: layers, embeddings, norm)
      - ``audio_decoder.layers.X`` → ``fast_layers.X``
      - ``audio_decoder.embeddings`` → ``fast_embeddings``
      - ``audio_decoder.codebook_embeddings`` → ``codebook_embeddings`` (same)
      - ``audio_decoder.norm`` → ``fast_norm``
      - ``audio_decoder.output`` → ``fast_output``

    Operates in-place on the dict to avoid allocating a copy.
    Returns the same dict with remapped keys.
    """
    # Check if remapping is needed (if keys already match, skip)
    if any(k.startswith("layers.") for k in state_dict):
        return state_dict  # Already in model format

    if not any(k.startswith("text_model.") or k.startswith("audio_decoder.") for k in state_dict):
        return state_dict  # Unknown format, skip

    remapped = {}
    for key in list(state_dict.keys()):
        new_key = key
        # Main LLM: text_model.model.X → X
        if key.startswith("text_model.model."):
            new_key = key.removeprefix("text_model.model.")
        # Audio decoder: audio_decoder.X → fast_X (with exceptions)
        elif key.startswith("audio_decoder."):
            suffix = key.removeprefix("audio_decoder.")
            if suffix.startswith("layers."):
                new_key = "fast_" + suffix
            elif suffix.startswith("embeddings."):
                new_key = "fast_" + suffix
            elif suffix.startswith("norm."):
                new_key = "fast_" + suffix
            elif suffix.startswith("output."):
                new_key = "fast_" + suffix
            elif suffix.startswith("codebook_embeddings."):
                new_key = suffix  # stays as codebook_embeddings
            else:
                new_key = suffix  # unknown sub-key, keep as-is

        remapped[new_key] = state_dict[key]

    log.info(
        "Fish Speech: remapped %d state dict keys (text_model.model.* → *, "
        "audio_decoder.* → fast_*)",
        len(remapped),
    )
    return remapped


def _dequantize_fp8_state_dict(state_dict: dict) -> dict:
    """Fallback: dequantize FP8 → BF16 in-place (for GPUs without FP8 matmul).

    Only used when ``_supports_fp8_matmul()`` returns False.
    """
    import torch

    scale_keys = {k for k in state_dict if k.endswith(".scale")}
    if not scale_keys:
        return state_dict

    log.info(
        "Fish Speech: dequantizing %d FP8 weights → BF16 (no FP8 matmul support)",
        len(scale_keys),
    )

    for scale_key in list(scale_keys):
        weight_key = scale_key.removesuffix(".scale")
        if weight_key in state_dict:
            fp8_val = state_dict[weight_key]
            scale_val = state_dict[scale_key]
            state_dict[weight_key] = fp8_val.to(torch.bfloat16) * scale_val
            del fp8_val
        del state_dict[scale_key]

    gc.collect()
    return state_dict


# ---------------------------------------------------------------------------
#  Codec loading (hydra-free)
# ---------------------------------------------------------------------------


def _load_codec_direct(codec_path: str, device, precision=None):
    """Load the DAC codec model without hydra/omegaconf dependencies.

    Directly instantiates the model classes with config values from
    modded_dac_vq.yaml to avoid pulling in heavy hydra dependency.
    """
    import torch

    if precision is None:
        precision = torch.bfloat16
    from fish_speech.models.dac.modded_dac import DAC, ModelArgs, WindowLimitedTransformer
    from fish_speech.models.dac.rvq import DownsampleResidualVectorQuantize

    # Transformer config (shared between pre_module and post_module)
    transformer_config = ModelArgs(
        block_size=2048,
        n_layer=8,
        n_head=16,
        dim=1024,
        intermediate_size=3072,
        n_local_heads=-1,
        head_dim=64,
        rope_base=10000,
        norm_eps=1e-5,
        dropout_rate=0.1,
        attn_dropout_rate=0.1,
        channels_first=True,
    )

    post_module = WindowLimitedTransformer(
        causal=True,
        window_size=128,
        input_dim=1024,
        config=transformer_config,
    )
    pre_module = WindowLimitedTransformer(
        causal=True,
        window_size=128,
        input_dim=1024,
        config=transformer_config,
    )

    quantizer = DownsampleResidualVectorQuantize(
        input_dim=1024,
        n_codebooks=9,
        codebook_size=1024,
        codebook_dim=8,
        quantizer_dropout=0.5,
        downsample_factor=(2, 2),
        post_module=post_module,
        pre_module=pre_module,
        semantic_codebook_size=4096,
    )

    # The YAML uses _partial_: true, meaning DAC expects a callable factory
    # that it calls with (n_layer=..., dim=..., intermediate_size=...) to
    # produce per-block ModelArgs.  functools.partial matches hydra's behavior.
    from functools import partial

    general_config = partial(
        ModelArgs,
        block_size=8192,
        n_local_heads=-1,
        head_dim=64,
        rope_base=10000,
        norm_eps=1e-5,
        dropout_rate=0.1,
        attn_dropout_rate=0.1,
        channels_first=True,
    )

    codec = DAC(
        sample_rate=44100,
        encoder_dim=64,
        encoder_rates=[2, 4, 8, 8],
        decoder_dim=1536,
        decoder_rates=[8, 8, 4, 2],
        encoder_transformer_layers=[0, 0, 0, 4],
        decoder_transformer_layers=[4, 0, 0, 0],
        quantizer=quantizer,
        transformer_general_config=general_config,
    )

    # Load weights
    state_dict = torch.load(codec_path, map_location="cpu", weights_only=True)
    if "state_dict" in state_dict:
        state_dict = state_dict["state_dict"]
    if any("generator" in k for k in state_dict):
        state_dict = {
            k.replace("generator.", ""): v
            for k, v in state_dict.items()
            if "generator." in k
        }
    codec.load_state_dict(state_dict, strict=False)
    codec.eval()
    codec.to(device=device, dtype=precision)
    del state_dict
    gc.collect()
    return codec


# ---------------------------------------------------------------------------
#  Model loading & caching
# ---------------------------------------------------------------------------


def cleanup():
    """Free Fish Speech models from memory.

    Called by _vram_utils when other synthesizers need VRAM.
    """
    unload_models()


def load_models(variant: str = _DEFAULT_VARIANT) -> dict:
    """Load Fish Speech S2 Pro model with GPU↔CPU offloading.

    Args:
        variant: "fp8" (default, ~12GB VRAM) or "bf16" (~24GB VRAM).

    Returns:
        Dict with keys: llama_model, decode_one_token, codec, device,
        offload_device.
    """
    global _models, _active_variant

    if variant not in _MODEL_VARIANTS:
        log.warning(
            "Fish Speech: unknown variant %r, falling back to %s",
            variant, _DEFAULT_VARIANT,
        )
        variant = _DEFAULT_VARIANT

    # If a different variant is cached, unload first
    if _models and _active_variant != variant:
        log.info(
            "Fish Speech: variant changed %s → %s, reloading...",
            _active_variant, variant,
        )
        unload_models()

    if _models:
        log.info("Fish Speech: using cached model (%s)", _active_variant)
        return _models

    import torch

    try:
        from . import _vram_utils
    except ImportError:
        from core import _vram_utils  # type: ignore

    device = _vram_utils.get_device()
    offload_device = "cpu"

    # Aggressive VRAM cleanup before loading — evict all other models
    try:
        _vram_utils.free_for_module(exclude="fish_speech_synthesizer")
    except Exception:
        pass

    _log_license_notice()
    log.info("Fish Speech: loading %s model (device=%s)", variant, device)

    # --- Download model files ---
    model_path = _find_or_download_file("model.safetensors", variant)
    codec_path = _find_or_download_file("codec.pth", variant)

    # Ensure config and tokenizer are available
    model_dir = _get_model_dir(variant)
    for f in ("config.json", "tokenizer.json", "tokenizer_config.json"):
        _find_or_download_file(f, variant)

    # --- Load LLaMA (DualARTransformer) ---
    log.info("Fish Speech: loading DualARTransformer from %s ...", model_dir)

    from fish_speech.models.text2semantic.llama import DualARTransformer
    from fish_speech.models.text2semantic.inference import (
        decode_one_token_ar,
    )

    # Load model structure on meta device (zero RAM — no random weights)
    log.info("Fish Speech: creating model skeleton on meta device ...")
    with torch.device("meta"):
        llama_model = DualARTransformer.from_pretrained(
            model_dir, load_weights=False
        )

    # Materialize meta skeleton → CPU (creates real empty tensors for
    # buffers like freqs_cis, causal_mask that load_state_dict won't fill)
    llama_model = llama_model.to_empty(device=offload_device)

    # Load and handle FP8 weights
    from safetensors.torch import load_file

    log.info("Fish Speech: loading state dict from %s ...", model_path)
    state_dict = load_file(model_path)

    # Remap keys from FP8 checkpoint format → DualARTransformer format
    state_dict = _remap_state_dict_keys(state_dict)

    # Detect FP8 model
    is_fp8 = variant == "fp8" or any(k.endswith(".scale") for k in state_dict)
    use_native_fp8 = is_fp8 and _supports_fp8_matmul()

    if is_fp8 and use_native_fp8:
        # Native FP8 path: keep weights in FP8, extract scales for patching
        log.info(
            "Fish Speech: native FP8 mode — keeping weights in FP8 "
            "(half VRAM, hardware-accelerated matmul)"
        )
        scale_weights = _extract_scale_weights(state_dict)
    elif is_fp8:
        # Fallback: dequantize to BF16 (older GPUs without FP8 matmul)
        log.info("Fish Speech: GPU does not support FP8 matmul, dequantizing to BF16")
        state_dict = _dequantize_fp8_state_dict(state_dict)
        scale_weights = None
    else:
        scale_weights = None

    # assign=True replaces parameter tensors with loaded data (no copy)
    result = llama_model.load_state_dict(state_dict, strict=False, assign=True)
    if result.missing_keys:
        log.warning(
            "Fish Speech: %d missing keys after load (first 5: %s)",
            len(result.missing_keys), result.missing_keys[:5],
        )
    del state_dict
    gc.collect()

    # CRITICAL: to_empty() materialized non-persistent buffers as
    # uninitialized garbage.  freqs_cis (rotary embeddings) and
    # causal_mask are NOT in the state dict (persistent=False), so
    # load_state_dict does NOT fill them.  We MUST recompute them.
    from fish_speech.models.text2semantic.llama import precompute_freqs_cis
    cfg = llama_model.config
    llama_model.freqs_cis = precompute_freqs_cis(
        cfg.max_seq_len, cfg.head_dim, cfg.rope_base,
    )
    llama_model.causal_mask = torch.tril(
        torch.ones(cfg.max_seq_len, cfg.max_seq_len, dtype=torch.bool)
    )
    # DualARTransformer also has fast_freqs_cis for the fast codebook layers
    if hasattr(llama_model, "fast_freqs_cis"):
        llama_model.fast_freqs_cis = precompute_freqs_cis(
            cfg.num_codebooks, cfg.fast_head_dim, cfg.rope_base,
        )
    log.info("Fish Speech: recomputed freqs_cis, causal_mask, fast_freqs_cis")

    precision = torch.bfloat16

    if use_native_fp8:
        # Patch Linear layers for native FP8 matmul (weights stay FP8)
        llama_model.eval()
        _convert_fp8_linear(llama_model, precision, scale_weights)
        del scale_weights
    else:
        # BF16 path — cast parameters to bfloat16
        llama_model = llama_model.to(dtype=precision)
        llama_model.eval()

    # Mark cache as not set up yet (done on first inference)
    llama_model._cache_setup_done = False

    # --- Shrink oversized buffers to save VRAM ---
    # The model's causal_mask is 32768×32768 (bool) = ~1 GiB!
    # freqs_cis is 32768×64 (complex64) = ~16 MiB
    # For TTS we only need 4096 tokens max. Trim these BEFORE .to(device)
    # to avoid copying the full 1 GiB mask to GPU.
    _tts_max_seq = 4096
    if hasattr(llama_model, "causal_mask") and llama_model.causal_mask is not None:
        if llama_model.causal_mask.shape[-1] > _tts_max_seq:
            llama_model.causal_mask = llama_model.causal_mask[
                ..., :_tts_max_seq, :_tts_max_seq
            ].contiguous()
    if hasattr(llama_model, "freqs_cis") and llama_model.freqs_cis is not None:
        if llama_model.freqs_cis.shape[0] > _tts_max_seq:
            llama_model.freqs_cis = llama_model.freqs_cis[
                :_tts_max_seq
            ].contiguous()
    llama_model.config.max_seq_len = _tts_max_seq
    gc.collect()

    log.info("Fish Speech: LLaMA model loaded and offloaded to %s", offload_device)

    # --- Load DAC codec ---
    log.info("Fish Speech: loading DAC codec from %s ...", codec_path)

    codec = _load_codec_direct(codec_path, offload_device, precision)
    log.info("Fish Speech: DAC codec loaded and offloaded to %s", offload_device)

    _models = {
        "llama_model": llama_model,
        "decode_one_token": decode_one_token_ar,
        "codec": codec,
        "device": device,
        "offload_device": offload_device,
        "precision": precision,
        "variant": variant,
    }
    _active_variant = variant
    return _models


def unload_models():
    """Free Fish Speech models from GPU and system memory.

    Follows the Flux Klein cleanup pattern: explicit del, CUDA cache flush,
    ComfyUI soft_empty_cache, and gc.collect().  This is called automatically
    by ``_vram_utils.free_for_module()`` when other synthesizers need VRAM.
    """
    global _models, _active_variant

    if _models:
        for key in ("llama_model", "codec"):
            if key in _models:
                try:
                    _models[key].to("cpu")
                except Exception:
                    pass
                try:
                    del _models[key]
                except Exception:
                    pass
        _models.clear()
        _active_variant = ""

    # Aggressive cleanup matching Flux Klein pattern
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
    log.info("Fish Speech: models unloaded")


# ---------------------------------------------------------------------------
#  Audio I/O helpers (FFmpeg-based, no torchaudio/soundfile dependency)
# ---------------------------------------------------------------------------


def _get_ffmpeg_bin() -> str:
    """Get the FFmpeg binary path."""
    try:
        from .bin_paths import get_ffmpeg_bin
        return get_ffmpeg_bin()
    except ImportError:
        return "ffmpeg"


def _load_audio_for_codec(audio_path: str, sample_rate: int = 44100):
    """Load audio via FFmpeg and return as tensor for DAC codec.

    Returns:
        torch.Tensor of shape (1, 1, N) at the target sample rate.
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
        "-ac", "1",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg audio load failed: {proc.stderr[-500:]}")

    raw = proc.stdout
    audio_np = np.frombuffer(raw, dtype=np.float32)
    return torch.from_numpy(audio_np.copy())


def _save_audio_wav(tensor, output_path: str, sample_rate: int):
    """Save a 1D tensor as a WAV file via FFmpeg."""
    import numpy as np

    audio_np = tensor.cpu().float().numpy()
    ffmpeg_bin = _get_ffmpeg_bin()
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "f32le",
        "-ar", str(sample_rate),
        "-ac", "1",
        "-i", "pipe:0",
        "-c:a", "pcm_s16le",
        output_path,
    ]
    proc = subprocess.run(
        cmd, input=audio_np.tobytes(),
        capture_output=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg audio save failed: {proc.stderr[-500:]}")


# ---------------------------------------------------------------------------
#  Reference audio encoding
# ---------------------------------------------------------------------------


def _encode_reference_audio(
    audio_path: str, codec, device, precision
):
    """Encode reference audio to VQ codes for voice cloning.

    Args:
        audio_path: Path to the reference audio file (10-30s recommended).
        codec: The DAC codec model.
        device: CUDA device.
        precision: Model dtype (bfloat16).

    Returns:
        torch.Tensor of shape (num_codebooks, T) — the VQ codes.
    """
    import torch

    sample_rate = codec.sample_rate
    wav = _load_audio_for_codec(audio_path, sample_rate)

    # Match codec dtype
    audios = wav[None, None].to(device=device, dtype=precision)  # (1, 1, N)
    audio_lengths = torch.tensor(
        [audios.shape[2]], device=device, dtype=torch.long
    )

    log.info(
        "Fish Speech: encoding reference audio (%.1fs) ...",
        audios.shape[2] / sample_rate,
    )

    indices, feature_lengths = codec.encode(audios, audio_lengths)
    codes = indices[0, :, :feature_lengths[0]]  # (num_codebooks, T)
    log.info("Fish Speech: encoded reference → %s", list(codes.shape))
    return codes


# ---------------------------------------------------------------------------
#  Long-form text splitting & audio stitching
# ---------------------------------------------------------------------------


def _count_words(text: str) -> int:
    """Approximate word count (CJK characters each count as one word)."""
    if not text or not text.strip():
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", text))
    non_cjk = re.sub(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", " ", text)
    western = len(non_cjk.split())
    return cjk + western


def _split_text_into_chunks(
    text: str, max_words_per_chunk: int = 200
) -> List[str]:
    """Split text into chunks at sentence boundaries.

    Sentences are split on ``.``, ``!``, ``?``, CJK sentence-enders
    (``。``, ``！``, ``？``), and newlines.  Each chunk stays under
    *max_words_per_chunk* words unless a single sentence exceeds the limit.

    Args:
        text: Full input text.
        max_words_per_chunk: Maximum words per chunk (default 200).

    Returns:
        List of text chunks, each at or below the word limit.
    """
    text = text.strip()
    if not text:
        return []

    # Split into sentences on punctuation or newlines
    sentence_end = r"[.!?。！？]\s*|\n+"
    raw_parts = re.split(f"({sentence_end})", text)
    sentences: list[str] = []
    buf = ""
    for part in raw_parts:
        if re.match(sentence_end, part):
            buf += part
            if buf.strip():
                sentences.append(buf.strip())
            buf = ""
        else:
            buf = part
    if buf.strip():
        sentences.append(buf.strip())

    if not sentences:
        return [text] if text else []

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for sent in sentences:
        sent_words = _count_words(sent)
        # Single sentence exceeds limit — add as its own chunk
        if sent_words > max_words_per_chunk:
            if current:
                chunks.append(" ".join(current))
                current = []
                current_words = 0
            chunks.append(sent)
            continue

        if current_words + sent_words > max_words_per_chunk and current:
            chunks.append(" ".join(current))
            current = []
            current_words = 0

        current.append(sent)
        current_words += sent_words

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if c]


def _crossfade_concat(
    segments: list, sample_rate: int, crossfade_ms: int = 100
):
    """Concatenate audio segments with a short crossfade to avoid clicks.

    Args:
        segments: List of 1D numpy arrays (audio samples).
        sample_rate: Audio sample rate.
        crossfade_ms: Crossfade duration in milliseconds (0 = no crossfade).

    Returns:
        Concatenated numpy array.
    """
    import numpy as np

    if not segments:
        return np.array([], dtype=np.float32)
    if len(segments) == 1:
        return segments[0]

    xfade_samples = int(sample_rate * crossfade_ms / 1000)

    result = segments[0]
    for seg in segments[1:]:
        overlap = min(xfade_samples, len(result), len(seg))
        if overlap > 0:
            fade_out = np.linspace(1.0, 0.0, overlap, dtype=np.float32)
            fade_in = np.linspace(0.0, 1.0, overlap, dtype=np.float32)
            # Blend the overlapping region
            blended = result[-overlap:] * fade_out + seg[:overlap] * fade_in
            result = np.concatenate([result[:-overlap], blended, seg[overlap:]])
        else:
            result = np.concatenate([result, seg])

    return result


# ---------------------------------------------------------------------------
#  Core TTS generation
# ---------------------------------------------------------------------------


def generate_speech(
    text: str,
    reference_audio: Optional[str] = None,
    reference_text: Optional[str] = None,
    reference_audios: Optional[list] = None,
    voice_name: Optional[str] = None,
    emotion_tag: str = "",
    variant: str = _DEFAULT_VARIANT,
    temperature: float = 0.8,
    top_p: float = 0.8,
    repetition_penalty: float = 1.1,
    max_new_tokens: int = 0,
    chunk_length: int = 200,
    max_words_per_chunk: int = 200,
    seed: int = -1,
    output_dir: Optional[str] = None,
) -> str:
    """Generate speech audio from text using Fish Speech S2 Pro.

    Args:
        text: Input text to synthesize. Supports inline tags like
            ``[whisper]``, ``[excited]``, ``<|speaker:0|>``, etc.
        reference_audio: Path to a single reference audio file for voice cloning.
        reference_text: Transcript of the reference audio (improves quality).
        reference_audios: List of (audio_path, text_label) tuples for multi-speaker.
            Each entry maps to <|speaker:N|> in order. Overrides reference_audio.
        voice_name: Name from the voice library (alternative to reference_audio).
        emotion_tag: Emotion tag to prepend, e.g. "[excited]".
        variant: Model variant, "fp8" (default) or "bf16".
        temperature: Sampling temperature (0.1-1.0).
        top_p: Top-p sampling (0.1-1.0).
        repetition_penalty: Repetition penalty (1.0-2.0).
        max_new_tokens: Maximum tokens to generate (0 = unlimited).
        chunk_length: Text chunk size for iterative prompting.
        max_words_per_chunk: For long-form text, split into chunks of
            this many words at sentence boundaries (0 = no splitting).
        seed: Random seed (-1 for random).
        output_dir: Directory for output file (auto-created if needed).

    Returns:
        Path to the generated WAV file.
    """
    import torch

    if not text or not text.strip():
        raise ValueError("Fish Speech: text cannot be empty")

    # Resolve voice name to audio path
    if voice_name and not reference_audio:
        resolved = _get_voice_audio_path(voice_name)
        if resolved:
            reference_audio = resolved
            # Also check for transcript
            if not reference_text:
                reference_text = _get_voice_transcript(voice_name)
            log.info("Fish Speech: using voice '%s' → %s", voice_name, resolved)
        else:
            log.warning(
                "Fish Speech: voice '%s' not found in library, "
                "using default voice", voice_name
            )

    # Prepend emotion tag if provided
    if emotion_tag and emotion_tag.strip():
        tag = emotion_tag.strip()
        if not tag.startswith("["):
            tag = f"[{tag}]"
        text = f"{tag}{text}"

    # Load models
    models = load_models(variant=variant)
    llama_model = models["llama_model"]
    decode_one_token = models["decode_one_token"]
    codec = models["codec"]
    device = models["device"]
    offload_device = models["offload_device"]
    precision = models["precision"]

    try:
        from . import _vram_utils
    except ImportError:
        from core import _vram_utils  # type: ignore

    # --- Aggressive VRAM cleanup ---
    # 1. Free our own synthesizer modules (except ourselves)
    _vram_utils.free_for_module(exclude="fish_speech_synthesizer")

    # 2. Hard-flush ALL ComfyUI models from GPU (SD checkpoints, LoRAs,
    #    VAEs, etc.)  These typically hold ~6-8 GiB and aren't needed
    #    during TTS inference.
    try:
        import comfy.model_management
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()
    except Exception:
        pass  # Non-critical if ComfyUI API changed
    torch.cuda.empty_cache()
    gc.collect()

    if torch.cuda.is_available():
        free_gb = torch.cuda.mem_get_info(device)[0] / (1024**3)
        log.info("Fish Speech: GPU free after cleanup: %.2f GiB", free_gb)

    # --- Auto-estimate max_new_tokens from text length ---
    # Fish Speech generates ~86 tokens per second of speech.
    # English speech averages ~2.5 words/sec (~150 wpm).
    # So: tokens ≈ words × (86 / 2.5) ≈ words × 35
    # With a 1.5× safety margin: words × 50
    # The model will still stop early via <|im_end|> when it's done.
    if max_new_tokens <= 0:
        word_count = _count_words(text)
        # ~50 tokens per word (1.5× safety margin), minimum 256
        estimated = max(256, int(word_count * 50))
        # Cap at 2048 to keep VRAM and time reasonable
        max_new_tokens = min(estimated, 2048)
        log.info(
            "Fish Speech: auto max_new_tokens=%d for %d words "
            "(model stops early via <|im_end|>)",
            max_new_tokens, word_count,
        )

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_fishspeech_")
    os.makedirs(output_dir, exist_ok=True)

    try:
        # === PHASE 0: Encode reference audio(s) (codec alone on GPU) ===
        # Must happen BEFORE the LLM moves to GPU — both can't
        # fit simultaneously (9.2 GiB LLM + 1 GiB codec > VRAM).
        prompt_tokens_list = None
        prompt_text_list = None

        # Build list of references: multi-speaker list takes priority
        _refs: list[tuple[str, str]] = []  # (audio_path, text_label)
        if reference_audios:
            for entry in reference_audios:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    path, label = entry[0], entry[1]
                else:
                    path, label = str(entry), "reference audio"
                if path and os.path.isfile(path):
                    _refs.append((path, label))
        elif reference_audio and os.path.isfile(reference_audio):
            _refs.append((
                reference_audio,
                reference_text if reference_text else "reference audio",
            ))

        if _refs:
            codec.to(device)
            prompt_tokens_list = []
            prompt_text_list = []
            for idx, (ref_path, ref_label) in enumerate(_refs):
                codes = _encode_reference_audio(
                    ref_path, codec, device, precision
                )
                prompt_tokens_list.append(codes.cpu())
                # Tag each reference with speaker ID for multi-speaker
                speaker_tag = f"<|speaker:{idx}|>"
                prompt_text_list.append(f"{speaker_tag}{ref_label}")
                log.info(
                    "Fish Speech: encoded reference %d → %s (%d tokens)",
                    idx, ref_label[:40], codes.shape[1],
                )
            codec.to(offload_device)
            torch.cuda.empty_cache()

        # === PHASE 1: LLM semantic token generation (LLM on GPU, codec stays CPU) ===
        log.info("Fish Speech: moving LLM to %s for inference", device)
        llama_model.to(device)

        # Set seed
        if seed >= 0:
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed(seed)

        # Setup KV caches
        if not getattr(llama_model, "_cache_setup_done", False):
            cache_seq_len = min(4096, llama_model.config.max_seq_len)
            torch.cuda.empty_cache()
            with torch.device(device):
                llama_model.setup_caches(
                    max_batch_size=1,
                    max_seq_len=cache_seq_len,
                    dtype=precision,
                )
            llama_model._cache_setup_done = True
            log.info(
                "Fish Speech: KV caches set up (seq_len=%d)", cache_seq_len
            )

        # Import generation functions
        from fish_speech.models.text2semantic.inference import (
            generate_long,
            decode_to_audio,
        )

        # Split long text into sentence-bounded chunks
        word_count = _count_words(text)
        if max_words_per_chunk > 0 and word_count > max_words_per_chunk:
            text_chunks = _split_text_into_chunks(text, max_words_per_chunk)
            log.info(
                "Fish Speech: long-form mode — %d words split into %d chunks",
                word_count, len(text_chunks),
            )
        else:
            text_chunks = [text]

        # Generate semantic codes for ALL chunks (LLM on GPU)
        import numpy as np

        all_chunk_codes: list = []

        for chunk_idx, chunk_text in enumerate(text_chunks):
            log.info(
                "Fish Speech: generating chunk %d/%d (%d words, %d chars)",
                chunk_idx + 1, len(text_chunks),
                _count_words(chunk_text), len(chunk_text),
            )

            chunk_codes = []
            generator = generate_long(
                model=llama_model,
                device=device,
                decode_one_token=decode_one_token,
                text=chunk_text,
                num_samples=1,
                max_new_tokens=max_new_tokens,
                top_p=top_p,
                top_k=30,
                repetition_penalty=repetition_penalty,
                temperature=temperature,
                compile=False,
                iterative_prompt=chunk_length > 0,
                chunk_length=chunk_length,
                prompt_text=prompt_text_list,
                prompt_tokens=prompt_tokens_list,
            )

            for response in generator:
                if response.action == "sample":
                    chunk_codes.append(response.codes.cpu())
                    log.info("Fish Speech: generated segment for: %s",
                             response.text[:80] if response.text else "?")
                elif response.action == "next":
                    break

            if chunk_codes:
                all_chunk_codes.append(torch.cat(chunk_codes, dim=1))
            else:
                log.warning(
                    "Fish Speech: no audio for chunk %d, skipping",
                    chunk_idx + 1,
                )

        if not all_chunk_codes:
            raise RuntimeError("Fish Speech: no audio generated — check input text")

        # === PHASE 2: Offload LLM, load codec for audio decoding ===
        log.info("Fish Speech: offloading LLM, loading codec for decode")

        # Reset KV caches to release GPU memory — setup_caches() registered
        # large buffer tensors (4096 × layers × heads × head_dim × bf16)
        # that .to(cpu) copies but doesn't immediately free from GPU.
        llama_model._cache_setup_done = False
        # Reset max_seq_len so setup_caches() fully re-initializes next run
        llama_model.max_seq_len = -1
        llama_model.max_batch_size = -1
        for layer in llama_model.layers:
            if hasattr(layer, "attention") and hasattr(layer.attention, "kv_cache"):
                layer.attention.kv_cache = None
        if hasattr(llama_model, "fast_layers"):
            for layer in llama_model.fast_layers:
                if hasattr(layer, "attention") and hasattr(layer.attention, "kv_cache"):
                    layer.attention.kv_cache = None

        llama_model.to(offload_device)
        del llama_model  # Drop local reference
        gc.collect()
        torch.cuda.empty_cache()

        if torch.cuda.is_available():
            free_gb = torch.cuda.mem_get_info(device)[0] / (1024**3)
            log.info("Fish Speech: GPU free after LLM offload: %.2f GiB", free_gb)

        codec.to(device)
        sample_rate = codec.sample_rate

        # Chunked codec decoding: full token sequences produce enormous
        # intermediate activations in the DAC upsampler (512× upsample,
        # 1536 channels → ~7 GiB for 4048 tokens).  Decode in smaller
        # chunks to cap peak VRAM at ~2 GiB per chunk.
        _CODEC_CHUNK_TOKENS = 500  # ~5.8s of audio per chunk

        audio_segments: list = []
        for chunk_idx, merged_codes in enumerate(all_chunk_codes):
            # Split this chunk's codes into sub-chunks for the codec
            total_tokens = merged_codes.shape[1]
            sub_audios = []
            for start in range(0, total_tokens, _CODEC_CHUNK_TOKENS):
                end = min(start + _CODEC_CHUNK_TOKENS, total_tokens)
                sub_codes = merged_codes[:, start:end].to(device)
                sub_audio = decode_to_audio(sub_codes, codec)
                sub_audios.append(sub_audio.cpu().float())
                del sub_codes, sub_audio
                torch.cuda.empty_cache()

            chunk_np = torch.cat(sub_audios, dim=-1).numpy()
            del sub_audios
            audio_segments.append(chunk_np)
            chunk_secs = len(chunk_np) / sample_rate
            log.info(
                "Fish Speech: decoded chunk %d/%d → %.1fs (%d tokens, %d sub-chunks)",
                chunk_idx + 1, len(all_chunk_codes), chunk_secs,
                total_tokens, (total_tokens + _CODEC_CHUNK_TOKENS - 1) // _CODEC_CHUNK_TOKENS,
            )

        # Offload codec immediately
        codec.to(offload_device)
        gc.collect()
        torch.cuda.empty_cache()

        # Stitch segments with crossfade (100ms) for seamless transitions
        if len(audio_segments) > 1:
            final_audio_np = _crossfade_concat(
                audio_segments, sample_rate, crossfade_ms=100
            )
            log.info(
                "Fish Speech: stitched %d segments (%.1fs total, 100ms crossfade)",
                len(audio_segments), len(final_audio_np) / sample_rate,
            )
        else:
            final_audio_np = audio_segments[0]

        audio_seconds = len(final_audio_np) / sample_rate
        log.info(
            "Fish Speech: generated %.1fs of audio at %dHz",
            audio_seconds, sample_rate,
        )

        # Save output
        output_path = os.path.join(output_dir, "fish_speech_output.wav")
        audio_tensor = torch.from_numpy(final_audio_np)
        _save_audio_wav(audio_tensor, output_path, sample_rate)
        log.info("Fish Speech: saved output → %s", output_path)

        return output_path

    finally:
        # Belt-and-suspenders: ensure both models are on CPU
        try:
            _llm = models.get("llama_model")
            if _llm is not None:
                _llm.to(offload_device)
            codec.to(offload_device)
        except Exception:
            pass
        gc.collect()
        try:
            import torch as _torch
            if _torch.cuda.is_available():
                _torch.cuda.empty_cache()
        except Exception:
            pass
        _vram_utils.soft_empty_cache()


def clone_voice(
    reference_audio: str,
    text: str,
    reference_text: Optional[str] = None,
    **kwargs,
) -> str:
    """Clone a voice and generate speech.

    Convenience wrapper around generate_speech with voice cloning defaults.

    Args:
        reference_audio: Path to reference audio (10-30s).
        text: Text to synthesize in the cloned voice.
        reference_text: Optional transcript of reference audio.
        **kwargs: Additional kwargs passed to generate_speech.

    Returns:
        Path to the generated WAV file.
    """
    return generate_speech(
        text=text,
        reference_audio=reference_audio,
        reference_text=reference_text,
        **kwargs,
    )
