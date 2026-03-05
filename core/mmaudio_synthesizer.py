"""MMAudio integration for AI-powered audio synthesis in FFMPEGA.

Generates synchronized audio from video content and/or text prompts
using the MMAudio model (CVPR 2025).

Supports:
- **Video-to-Audio**: Analyzes video frames and generates matching sounds
- **Text-to-Audio**: Generates audio from a text description alone
- **Long video handling**: Automatically chunks videos > 8s and crossfades

Architecture:
- In-process inference with GPU↔CPU offloading
- Models cached globally and moved to GPU only during inference
- Uses ``model_manager`` for download guards and mirror support
- Models stored in ``ComfyUI/models/mmaudio/``
- Native safetensors loading via ``comfy.utils.load_torch_file``
- Memory-efficient model init via ``accelerate``

License note:
    MMAudio code is MIT.  Model checkpoints are CC-BY-NC 4.0
    (non-commercial).  Users download weights on first use and accept
    that license themselves.  See https://huggingface.co/hkchengrex/MMAudio
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

_HF_REPO = "hkchengrex/MMAudio"
_MIRROR_REPO = "AEmotionStudio/mmaudio-models"

# Files needed — all stored as fp16 safetensors on mirror
_MODEL_FILES = {
    "model": "mmaudio_large_44k_v2.safetensors",
    "vae": "v1-44.safetensors",
    "synchformer": "synchformer_state_dict.safetensors",
    "clip": "apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors",
}

# For upstream HF fallback (original .pth files)
_HF_UPSTREAM_FILES = {
    "model": ("weights", "mmaudio_large_44k_v2.pth"),
    "vae": ("ext_weights", "v1-44.pth"),
    "synchformer": ("ext_weights", "synchformer_state_dict.pth"),
}


def _get_model_dir() -> str:
    """Return the MMAudio model directory, creating it if needed.

    Checks (in order):
    1. FFMPEGA_MMAUDIO_MODEL_DIR env var (set by subprocess wrapper)
    2. ComfyUI/models/mmaudio/ (standard ComfyUI convention)
    3. ComfyUI/models/mmaudio/ (same path via standalone fallback)
    """
    env_dir = os.environ.get("FFMPEGA_MMAUDIO_MODEL_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir

    from .platform import get_models_dir
    return get_models_dir("mmaudio")


def _find_or_download_model(model_key: str) -> str:
    """Find or download a model file.

    Tries safetensors from mirror first, then falls back to upstream .pth.

    Args:
        model_key: One of "model", "vae", "synchformer", "clip".

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

    # Also check for old .pth format (backward compat)
    if filename.endswith(".safetensors"):
        pth_name = filename.replace(".safetensors", ".pth")
        pth_path = os.path.join(model_dir, pth_name)
        if os.path.isfile(pth_path):
            return pth_path

    # Guard: check if downloads are allowed
    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed  # type: ignore[no-redef]
    require_downloads_allowed("mmaudio")

    # Try mirror first (direct safetensors download — no conversion needed)
    try:
        from .model_manager import try_mirror_download, download_with_progress
    except ImportError:
        from core.model_manager import try_mirror_download, download_with_progress  # type: ignore[no-redef]

    mirror_path = try_mirror_download(
        model_key="mmaudio",
        filename=filename,
        local_dir=model_dir,
    )
    if mirror_path:
        _log_license_notice()
        return mirror_path

    # CLIP doesn't have an upstream .pth — only available from mirror
    if model_key == "clip":
        raise RuntimeError(
            f"Failed to download CLIP model for MMAudio from mirror. "
            f"Download manually from {_MIRROR_REPO} and place in: {model_dir}"
        )

    # Download from upstream HuggingFace (original .pth format)
    if model_key in _HF_UPSTREAM_FILES:
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            raise RuntimeError(
                "huggingface_hub is required to download MMAudio models. "
                "Install with: pip install huggingface_hub"
            )

        subdir, upstream_filename = _HF_UPSTREAM_FILES[model_key]
        hf_path = f"{subdir}/{upstream_filename}"
        upstream_local = os.path.join(model_dir, upstream_filename)

        def _download():
            return hf_hub_download(
                repo_id=_HF_REPO,
                filename=hf_path,
                local_dir=model_dir,
                local_dir_use_symlinks=False,
            )

        downloaded = download_with_progress("mmaudio", _download, extra=upstream_filename)

        # hf_hub_download may put file in a subdirectory — move to flat dir
        if isinstance(downloaded, str) and os.path.isfile(downloaded):
            if downloaded != upstream_local:
                import shutil
                shutil.move(downloaded, upstream_local)
                subdir_path = os.path.join(model_dir, subdir)
                if os.path.isdir(subdir_path):
                    try:
                        os.rmdir(subdir_path)
                    except OSError:
                        pass

        if os.path.isfile(upstream_local):
            _log_license_notice()
            return upstream_local

    raise RuntimeError(f"Failed to download MMAudio {model_key}: {filename}")


def _find_or_download_bigvgan() -> str:
    """Find or download BigVGAN v2 vocoder for 44kHz mode.

    Tries our mirror first, then falls back to nvidia's snapshot.

    Returns:
        Path to BigVGAN directory.
    """
    model_dir = _get_model_dir()
    bigvgan_dir = os.path.join(model_dir, "bigvgan_v2_44khz_128band_512x")

    # Check if already downloaded
    generator_path = os.path.join(bigvgan_dir, "bigvgan_generator.pt")
    config_path = os.path.join(bigvgan_dir, "config.json")
    if os.path.isfile(generator_path) and os.path.isfile(config_path):
        return bigvgan_dir

    try:
        from .model_manager import require_downloads_allowed
    except ImportError:
        from core.model_manager import require_downloads_allowed  # type: ignore[no-redef]
    require_downloads_allowed("mmaudio")

    # Try mirror first
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise RuntimeError(
            "huggingface_hub is required to download BigVGAN. "
            "Install with: pip install huggingface_hub"
        )

    log.info("MMAudio: downloading BigVGAN vocoder...")
    try:
        snapshot_download(
            repo_id=_MIRROR_REPO,
            allow_patterns=["bigvgan_v2_44khz_128band_512x/*"],
            local_dir=model_dir,
        )
        if os.path.isfile(generator_path):
            log.info("MMAudio: BigVGAN downloaded from mirror")
            return bigvgan_dir
    except Exception as e:
        log.debug("Mirror BigVGAN download failed: %s — trying nvidia", e)

    # Fallback: download from nvidia
    log.info("MMAudio: downloading BigVGAN from nvidia...")
    snapshot_download(
        repo_id="nvidia/bigvgan_v2_44khz_128band_512x",
        ignore_patterns=["*3m*"],
        local_dir=bigvgan_dir,
    )
    return bigvgan_dir


_license_logged = False


def _log_license_notice():
    """Log the CC-BY-NC license notice (once per session)."""
    global _license_logged
    if _license_logged:
        return
    _license_logged = True
    log.info(
        "⚠️  MMAudio model checkpoints are licensed CC-BY-NC 4.0 (non-commercial). "
        "By using these models you agree to: https://creativecommons.org/licenses/by-nc/4.0/"
    )


# ---------------------------------------------------------------------------
#  Model loading helpers
# ---------------------------------------------------------------------------

def _load_state_dict(path: str, device: str = "cpu"):
    """Load a state dict from .safetensors or .pth using best available loader.

    Delegates to ``platform.load_torch_file`` which tries
    ``comfy.utils.load_torch_file`` first, then falls back to
    ``safetensors.torch.load_file`` / ``torch.load``.
    """
    from .platform import load_torch_file

    return load_torch_file(path, device=device)


def _detect_model_variant(sd: dict) -> tuple[str, bool]:
    """Detect MMAudio model variant from state dict shapes.

    Returns:
        Tuple of (size, is_v2) where size is "small" or "large".
    """
    bias_key = "audio_input_proj.0.bias"
    if bias_key not in sd:
        log.warning("Cannot detect model variant — defaulting to large_44k_v2")
        return "large", True

    bias_shape = sd[bias_key].shape[0]
    if bias_shape == 448:
        return "small", False
    elif bias_shape == 896:
        # Check v2
        t_key = "t_embed.mlp.0.weight"
        is_v2 = t_key in sd and sd[t_key].shape[1] == 896
        return "large", is_v2
    else:
        log.warning("Unknown model variant (bias shape=%d) — defaulting to large", bias_shape)
        return "large", True


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

_freeing_vram = False


def _free_vram():
    """Free all GPU VRAM before loading MMAudio.

    Follows WanVideoWrapper's pattern:
    1. Tell ComfyUI to unload ALL cached models from GPU
    2. Free SAM3 models if loaded
    3. Free FLUX Klein pipeline if loaded
    4. Empty CUDA cache + gc.collect

    Uses a re-entrancy guard (``_freeing_vram``) to prevent infinite
    recursion — ``flux_klein_editor._free_vram()`` calls back into
    ``mmaudio_synthesizer.cleanup()``.
    """
    global _freeing_vram
    if _freeing_vram:
        return
    _freeing_vram = True
    try:
        from .platform import free_comfyui_vram
        free_comfyui_vram()

        # Free SAM3 if loaded
        try:
            try:
                from . import sam3_masker
            except ImportError:
                from core import sam3_masker  # type: ignore
            sam3_masker.cleanup()
        except Exception:
            pass

        # Free FLUX Klein if loaded
        try:
            try:
                from . import flux_klein_editor
            except ImportError:
                from core import flux_klein_editor  # type: ignore
            flux_klein_editor.cleanup()
        except Exception:
            pass

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        gc.collect()
    finally:
        _freeing_vram = False


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
    """Load and cache all MMAudio models.

    On first call, downloads models if needed, frees VRAM from other
    AI models (ComfyUI, SAM3, FLUX Klein), and loads all 5 components
    (MMAudio net, Synchformer, BigVGAN, VAE, CLIP) into a cached dict.

    Subsequent calls return the cached models immediately.

    Returns:
        Dict with keys: net, feature_utils, seq_cfg, device, dtype,
        offload_device.
    """
    global _models
    if _models is not None:
        return _models

    import torch
    import torch.nn as nn

    from mmaudio.model.flow_matching import FlowMatching
    from mmaudio.model.networks import MMAudio as MMAudioNet
    from mmaudio.model.utils.features_utils import FeaturesUtils
    from mmaudio.model.sequence_config import CONFIG_44K
    from mmaudio.ext.synchformer import Synchformer
    from mmaudio.ext.autoencoder import AutoEncoderModule

    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    # Device / dtype setup
    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    dtype = torch.bfloat16
    offload_device = _get_offload_device()

    # Resolve model paths (downloads if needed)
    model_path = _find_or_download_model("model")
    vae_path = _find_or_download_model("vae")
    synchformer_path = _find_or_download_model("synchformer")
    clip_path = _find_or_download_model("clip")
    bigvgan_dir = _find_or_download_bigvgan()

    # Free VRAM from other models
    _free_vram()

    log.info("MMAudio: loading models (device=%s, dtype=%s)", device, dtype)

    # ── Load MMAudio main model (memory-efficient) ────────────────
    model_sd = _load_state_dict(model_path, device=str(offload_device))
    size, is_v2 = _detect_model_variant(model_sd)

    try:
        from accelerate import init_empty_weights
        from accelerate.utils import set_module_tensor_to_device

        if size == "small":
            num_heads = 7
            with init_empty_weights():
                net = MMAudioNet(
                    latent_dim=40, clip_dim=1024, sync_dim=768, text_dim=1024,
                    hidden_dim=64 * num_heads, depth=12, fused_depth=8,
                    num_heads=num_heads,
                    latent_seq_len=345, clip_seq_len=64, sync_seq_len=192,
                ).eval()
        else:
            num_heads = 14
            with init_empty_weights():
                net = MMAudioNet(
                    latent_dim=40, clip_dim=1024, sync_dim=768, text_dim=1024,
                    hidden_dim=64 * num_heads, depth=21, fused_depth=14,
                    num_heads=num_heads,
                    latent_seq_len=345, clip_seq_len=64, sync_seq_len=192,
                    v2=is_v2,
                ).eval()

        for name, _param in net.named_parameters():
            set_module_tensor_to_device(
                net, name, device=str(offload_device), dtype=dtype, value=model_sd[name]
            )
        # Also materialize any buffers left as meta tensors
        for name, buf in net.named_buffers():
            if buf.device.type == "meta":
                if name in model_sd:
                    set_module_tensor_to_device(
                        net, name, device=str(offload_device), dtype=dtype, value=model_sd[name]
                    )
                else:
                    # Buffer not in checkpoint — create a zero tensor
                    set_module_tensor_to_device(
                        net, name, device=str(offload_device), dtype=dtype,
                        value=torch.zeros(buf.shape, dtype=dtype),
                    )
        del model_sd
        log.info("MMAudio: loaded model via accelerate (%s, v2=%s)", size, is_v2)

    except ImportError:
        log.info("MMAudio: accelerate not available — using standard loading")
        if size == "small":
            from mmaudio.model.networks import get_my_mmaudio
            net = get_my_mmaudio("small_16k").to(str(offload_device), dtype).eval()
        else:
            from mmaudio.model.networks import get_my_mmaudio
            model_name = "large_44k_v2" if is_v2 else "large_44k"
            net = get_my_mmaudio(model_name).to(str(offload_device), dtype).eval()
        net.load_weights(model_sd)
        del model_sd

    seq_cfg = CONFIG_44K

    # ── Load Synchformer ──────────────────────────────────────────
    synch_sd = _load_state_dict(synchformer_path, device=str(offload_device))
    try:
        from accelerate import init_empty_weights
        from accelerate.utils import set_module_tensor_to_device

        with init_empty_weights():
            synchformer = Synchformer().eval()
        for name, _param in synchformer.named_parameters():
            set_module_tensor_to_device(
                synchformer, name, device=str(offload_device), dtype=dtype, value=synch_sd[name]
            )
    except ImportError:
        synchformer = Synchformer().eval()
        synchformer.load_state_dict(synch_sd)
        synchformer = synchformer.to(str(offload_device), dtype)
    del synch_sd
    log.info("MMAudio: loaded Synchformer")

    # ── Load VAE + BigVGAN (bypass AutoEncoderModule constructor) ──
    # Upstream AutoEncoderModule uses torch.load(weights_only=True) on .pth
    # files, but our models are .safetensors. We construct it manually.
    from mmaudio.ext.autoencoder.vae import get_my_vae
    from mmaudio.ext.bigvgan_v2.bigvgan import BigVGAN as BigVGANv2
    from mmaudio.ext.mel_converter import get_mel_converter

    # Load VAE from safetensors
    vae_sd = _load_state_dict(vae_path, device=str(offload_device))
    vae_inner = get_my_vae("44k").eval()
    vae_inner.load_state_dict(vae_sd)
    vae_inner.remove_weight_norm()
    del vae_sd

    # Load BigVGAN from pretrained (HuggingFace, already downloaded)
    bigvgan_vocoder = BigVGANv2.from_pretrained(
        bigvgan_dir, use_cuda_kernel=False
    ).eval()
    bigvgan_vocoder.remove_weight_norm()

    # Manually assemble AutoEncoderModule
    autoencoder = AutoEncoderModule.__new__(AutoEncoderModule)
    nn.Module.__init__(autoencoder)
    autoencoder.vae = vae_inner
    autoencoder.vocoder = bigvgan_vocoder
    for param in autoencoder.parameters():
        param.requires_grad = False
    autoencoder = autoencoder.eval().to(str(offload_device), dtype)
    log.info("MMAudio: loaded VAE + BigVGAN vocoder")

    # ── Load CLIP via open_clip ───────────────────────────────────
    # Upstream FeaturesUtils downloads CLIP from HuggingFace. We load ours
    # from the cached safetensors instead.
    import open_clip
    from torchvision.transforms import Normalize as TVNormalize
    from mmaudio.model.utils.features_utils import patch_clip

    clip_sd = _load_state_dict(clip_path, device=str(offload_device))

    # Create CLIP model from open_clip and load our weights
    clip_model = open_clip.create_model('ViT-H-14-378-quickgelu', pretrained=False)
    clip_model.load_state_dict(clip_sd, strict=False)
    clip_model = patch_clip(clip_model)
    clip_model = clip_model.eval().to(str(offload_device), dtype)
    del clip_sd
    log.info("MMAudio: loaded CLIP")

    # ── Manually assemble FeaturesUtils ──────────────────────────
    # Bypass the upstream constructor which tries to download CLIP from HF
    # and load synchformer/VAE from .pth files. We set sub-modules directly.
    # Tested against mmaudio v0.3.x (hkchengrex/MMAudio@main 2025-03).
    # If upstream renames attributes, load_models tests will catch it.
    feature_utils = FeaturesUtils.__new__(FeaturesUtils)
    nn.Module.__init__(feature_utils)

    # Set CLIP components (matching upstream FeaturesUtils.__init__)
    feature_utils.clip_model = clip_model
    feature_utils.clip_preprocess = TVNormalize(
        mean=[0.48145466, 0.4578275, 0.40821073],
        std=[0.26862954, 0.26130258, 0.27577711],
    )
    feature_utils.synchformer = synchformer
    feature_utils.tokenizer = open_clip.get_tokenizer('ViT-H-14-378-quickgelu')

    # Set VAE/vocoder components
    feature_utils.mel_converter = get_mel_converter("44k")
    feature_utils.tod = autoencoder

    feature_utils = feature_utils.eval().to(str(offload_device), dtype)

    log.info("MMAudio: all models loaded and cached (offloaded to %s)", offload_device)

    _models = {
        "net": net,
        "feature_utils": feature_utils,
        "seq_cfg": seq_cfg,
        "device": device,
        "dtype": dtype,
        "offload_device": offload_device,
    }
    return _models


def cleanup() -> None:
    """Free GPU memory and clear cached MMAudio models.

    Moves models to CPU offload device, clears the cache, empties
    CUDA cache, and runs garbage collection.
    """
    global _models
    if _models is None:
        return

    # Capture and clear the global ref first so gc.collect() can reclaim
    models = _models
    _models = None

    try:
        offload = models["offload_device"]
        models["net"].to(offload)
        models["feature_utils"].to(offload)
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
    log.info("MMAudio: models unloaded")


# ---------------------------------------------------------------------------
#  Core inference
# ---------------------------------------------------------------------------

_CHUNK_DURATION = 8.0   # MMAudio training duration
_OVERLAP_SECS = 1.0     # Crossfade overlap between chunks


def generate_audio(
    video_path: Optional[str] = None,
    prompt: str = "",
    negative_prompt: str = "",
    duration: Optional[float] = None,
    seed: int = 42,
    cfg_strength: float = 4.5,
    output_dir: Optional[str] = None,
) -> str:
    """Generate audio from video and/or text using MMAudio.

    Uses cached in-process models with GPU↔CPU offloading.
    Models are loaded on first call and cached for reuse.
    After inference, models are offloaded back to CPU.

    Args:
        video_path: Path to input video (None for text-to-audio mode).
        prompt: Text description to guide audio generation.
        negative_prompt: What to avoid in generated audio.
        duration: Override duration in seconds (default: video length or 8s).
        seed: Random seed for reproducibility.
        cfg_strength: Classifier-free guidance strength.
        output_dir: Where to save output. Uses tempdir if not specified.

    Returns:
        Path to generated audio file (.wav).

    Raises:
        ImportError: If MMAudio is not installed.
        RuntimeError: If inference fails.
    """
    # Validate video path to prevent path traversal
    if video_path is not None:
        try:
            from .sanitize import validate_video_path
        except ImportError:
            from core.sanitize import validate_video_path  # type: ignore
        video_path = validate_video_path(video_path)

    import torch

    from mmaudio.eval_utils import generate, load_video
    from mmaudio.model.flow_matching import FlowMatching

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_mmaudio_")

    # ── Load or reuse cached models ───────────────────────────────
    models = load_models()
    net = models["net"]
    feature_utils = models["feature_utils"]
    seq_cfg = models["seq_cfg"]
    device = models["device"]
    offload_device = models["offload_device"]

    # Move models to GPU for inference
    log.info("MMAudio: moving models to %s for inference", device)
    net.to(device)
    feature_utils.to(device)

    rng = torch.Generator(device=device)
    rng.manual_seed(seed)
    fm = FlowMatching(min_sigma=0, inference_mode="euler", num_steps=25)

    # ── Determine total duration ──────────────────────────────────
    if video_path and os.path.isfile(video_path):
        try:
            import av
            with av.open(video_path) as container:
                stream = container.streams.video[0]
                if stream.duration is not None and stream.time_base is not None:
                    total_duration = float(stream.duration * stream.time_base)
                else:
                    total_duration = duration or _CHUNK_DURATION
        except Exception:
            total_duration = duration or _CHUNK_DURATION
        if duration is not None:
            total_duration = min(total_duration, duration)
    else:
        total_duration = duration or _CHUNK_DURATION
        video_path = None

    log.info(
        "MMAudio: generating %.1fs audio (video=%s, prompt=%r)",
        total_duration, video_path or "none", prompt,
    )

    # ── Generate audio ────────────────────────────────────────────
    try:
        if total_duration <= _CHUNK_DURATION + 0.5:
            audio = _generate_chunk(
                video_path=video_path,
                prompt=prompt,
                negative_prompt=negative_prompt,
                duration=total_duration,
                net=net,
                feature_utils=feature_utils,
                fm=fm,
                rng=rng,
                cfg_strength=cfg_strength,
                seq_cfg=seq_cfg,
                load_video_fn=load_video,
                generate_fn=generate,
            )
        else:
            audio = _generate_chunked(
                video_path=video_path,
                prompt=prompt,
                negative_prompt=negative_prompt,
                total_duration=total_duration,
                net=net,
                feature_utils=feature_utils,
                fm=fm,
                rng=rng,
                cfg_strength=cfg_strength,
                seq_cfg=seq_cfg,
                load_video_fn=load_video,
                generate_fn=generate,
            )

        # ── Save output (inside try so errors don't hit save code) ──
        sampling_rate = seq_cfg.sampling_rate
        output_path = os.path.join(output_dir, "mmaudio_output.wav")

        # Use scipy instead of torchaudio to avoid torchcodec dependency.
        # float32 WAV preserves full model precision (old code used FLAC).
        import numpy as np
        from scipy.io import wavfile
        audio_np = audio.cpu().float().numpy()
        # audio shape is (channels, samples) — scipy expects (samples,) or (samples, channels)
        if audio_np.ndim == 2:
            audio_np = audio_np.T  # (samples, channels)
        audio_np = np.clip(audio_np, -1.0, 1.0).astype(np.float32)
        wavfile.write(output_path, sampling_rate, audio_np)
        log.info("MMAudio: audio saved to %s", output_path)

        return output_path
    finally:
        # ── Offload models back to CPU ────────────────────────────
        log.info("MMAudio: offloading models to %s", offload_device)
        try:
            net.to(offload_device)
            feature_utils.to(offload_device)
        except Exception:
            pass
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        try:
            import comfy.model_management as mm  # type: ignore[import-not-found]
            mm.soft_empty_cache()
        except (ImportError, AttributeError):
            pass


def _generate_chunk(
    video_path,
    prompt,
    negative_prompt,
    duration,
    net,
    feature_utils,
    fm,
    rng,
    cfg_strength,
    seq_cfg,
    load_video_fn,
    generate_fn,
    start_sec=0.0,
):
    """Generate audio for a single chunk (≤ 8s)."""

    if video_path is not None:
        video_info = load_video_fn(Path(video_path), duration)
        clip_frames = video_info.clip_frames.unsqueeze(0)
        sync_frames = video_info.sync_frames.unsqueeze(0)
        chunk_duration = video_info.duration_sec
    else:
        clip_frames = sync_frames = None
        chunk_duration = duration

    seq_cfg.duration = chunk_duration
    net.update_seq_lengths(
        seq_cfg.latent_seq_len, seq_cfg.clip_seq_len, seq_cfg.sync_seq_len
    )

    audios = generate_fn(
        clip_frames,
        sync_frames,
        [prompt],
        negative_text=[negative_prompt],
        feature_utils=feature_utils,
        net=net,
        fm=fm,
        rng=rng,
        cfg_strength=cfg_strength,
    )
    return audios.float().cpu()[0]


def _generate_chunked(
    video_path,
    prompt,
    negative_prompt,
    total_duration,
    net,
    feature_utils,
    fm,
    rng,
    cfg_strength,
    seq_cfg,
    load_video_fn,
    generate_fn,
):
    """Generate audio for a long video by chunking into segments."""
    import subprocess
    import tempfile

    sampling_rate = seq_cfg.sampling_rate
    step = _CHUNK_DURATION - _OVERLAP_SECS
    chunks = []
    offset = 0.0

    try:
        while offset < total_duration:
            chunk_dur = min(_CHUNK_DURATION, total_duration - offset)
            if chunk_dur < 1.0:
                break

            log.info(
                "MMAudio: generating chunk %.1f–%.1fs",
                offset, offset + chunk_dur,
            )

            # Extract video segment for this chunk so MMAudio gets visual
            # context for every chunk, not just the first one.
            chunk_video_path = video_path
            segment_tmp = None
            if video_path is not None and offset > 0:
                try:
                    from .bin_paths import get_ffmpeg_bin  # type: ignore[import-not-found]
                    _ffmpeg = get_ffmpeg_bin()
                except ImportError:
                    _ffmpeg = "ffmpeg"
                try:
                    _seg_f = tempfile.NamedTemporaryFile(
                        suffix=".mp4", delete=False, prefix="mmaudio_seg_"
                    )
                    segment_tmp = _seg_f.name
                    _seg_f.close()
                    cmd = [
                        _ffmpeg, "-y",
                        "-ss", str(offset),
                        "-i", video_path,
                        "-t", str(chunk_dur),
                        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                        "-an", "-pix_fmt", "yuv420p",
                        segment_tmp,
                    ]
                    proc = subprocess.run(cmd, capture_output=True, timeout=60)
                    if proc.returncode == 0:
                        chunk_video_path = segment_tmp
                    else:
                        log.warning(
                            "MMAudio: segment extraction failed for %.1f–%.1fs, "
                            "falling back to text-only",
                            offset, offset + chunk_dur,
                        )
                        chunk_video_path = None
                except Exception as exc:
                    log.warning("MMAudio: segment extraction error: %s", exc)
                    chunk_video_path = None

            try:
                try:
                    audio_chunk = _generate_chunk(
                        video_path=chunk_video_path,
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        duration=chunk_dur,
                        net=net,
                        feature_utils=feature_utils,
                        fm=fm,
                        rng=rng,
                        cfg_strength=cfg_strength,
                        seq_cfg=seq_cfg,
                        load_video_fn=load_video_fn,
                        generate_fn=generate_fn,
                        start_sec=offset,
                    )
                except Exception as chunk_err:
                    raise RuntimeError(
                        f"MMAudio: failed to process chunk "
                        f"{offset:.1f}–{offset + chunk_dur:.1f}s: {chunk_err}"
                    ) from chunk_err
            finally:
                # Clean up temp segment file
                if segment_tmp and os.path.exists(segment_tmp):
                    try:
                        os.remove(segment_tmp)
                    except OSError:
                        pass

            chunks.append(audio_chunk)
            offset += step
    except Exception:
        # Release accumulated chunk tensors so GPU memory is freed faster
        chunks.clear()
        raise

    if len(chunks) == 1:
        return chunks[0]

    # Crossfade chunks together
    return _crossfade_chunks(chunks, sampling_rate, _OVERLAP_SECS)


def _crossfade_chunks(chunks, sampling_rate, overlap_secs):
    """Crossfade audio chunks with linear fade."""
    import torch

    overlap_samples = int(overlap_secs * sampling_rate)
    result = chunks[0]

    for chunk in chunks[1:]:
        # Create crossfade
        if result.shape[1] >= overlap_samples and chunk.shape[1] >= overlap_samples:
            fade_out = torch.linspace(1.0, 0.0, overlap_samples)
            fade_in = torch.linspace(0.0, 1.0, overlap_samples)

            # Apply fades to overlap regions
            result_end = result[:, -overlap_samples:] * fade_out
            chunk_start = chunk[:, :overlap_samples] * fade_in
            crossfaded = result_end + chunk_start

            # Concatenate: result[:-overlap] + crossfaded + chunk[overlap:]
            result = torch.cat([
                result[:, :-overlap_samples],
                crossfaded,
                chunk[:, overlap_samples:],
            ], dim=1)
        else:
            # No overlap possible — just concatenate
            result = torch.cat([result, chunk], dim=1)

    return result

