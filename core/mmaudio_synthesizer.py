"""MMAudio integration for AI-powered audio synthesis in FFMPEGA.

Generates synchronized audio from video content and/or text prompts
using the MMAudio model (CVPR 2025).

Supports:
- **Video-to-Audio**: Analyzes video frames and generates matching sounds
- **Text-to-Audio**: Generates audio from a text description alone
- **Long video handling**: Automatically chunks videos > 8s and crossfades

Architecture:
- Runs inference in a subprocess to prevent CUDA memory leaks
  (same pattern as ``sam3_masker.py``)
- Uses ``model_manager`` for download guards and mirror support
- Models stored in ``ComfyUI/models/mmaudio/``
- Native safetensors loading via ``comfy.utils.load_torch_file``
- Memory-efficient model init via ``accelerate``

License note:
    MMAudio code is MIT.  Model checkpoints are CC-BY-NC 4.0
    (non-commercial).  Users download weights on first use and accept
    that license themselves.  See https://huggingface.co/hkchengrex/MMAudio
"""

import atexit
import logging
import os
import subprocess
import sys
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
    3. Extension's own models/mmaudio/ (fallback for testing)
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

    Tries comfy.utils.load_torch_file first (supports both formats natively),
    falls back to torch.load / safetensors.torch.load_file.
    """
    try:
        from .platform import load_torch_file
        return load_torch_file(path)  # type: ignore[call-arg]
    except ImportError:
        pass

    if path.endswith(".safetensors"):
        from safetensors.torch import load_file
        return load_file(path, device=device)
    else:
        import torch
        return torch.load(path, map_location=device, weights_only=True)


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

def _free_vram():
    """Free ComfyUI VRAM before loading MMAudio."""
    from .platform import free_comfyui_vram
    free_comfyui_vram()

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _get_offload_device():
    """Get the ComfyUI offload device (CPU), or fallback to 'cpu'."""
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        return mm.unet_offload_device()
    except ImportError:
        import torch
        return torch.device("cpu")


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

    Uses native safetensors loading and memory-efficient model initialization
    via ``accelerate``.

    Args:
        video_path: Path to input video (None for text-to-audio mode).
        prompt: Text description to guide audio generation.
        negative_prompt: What to avoid in generated audio.
        duration: Override duration in seconds (default: video length or 8s).
        seed: Random seed for reproducibility.
        cfg_strength: Classifier-free guidance strength.
        output_dir: Where to save output. Uses tempdir if not specified.

    Returns:
        Path to generated audio file (.flac).

    Raises:
        ImportError: If MMAudio is not installed.
        RuntimeError: If inference fails.
    """
    import torch
    import torchaudio

    from mmaudio.eval_utils import generate, load_video
    from mmaudio.model.flow_matching import FlowMatching
    from mmaudio.model.networks import MMAudio as MMAudioNet, get_my_mmaudio
    from mmaudio.model.utils.features_utils import FeaturesUtils
    from mmaudio.model.sequence_config import CONFIG_44K
    from mmaudio.ext.synchformer import Synchformer
    from mmaudio.ext.autoencoder import AutoEncoderModule
    from mmaudio.ext.bigvgan_v2.bigvgan import BigVGAN as BigVGANv2

    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_mmaudio_")

    # ── Device / dtype setup ──────────────────────────────────────
    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = "mps"
    dtype = torch.bfloat16
    offload_device = _get_offload_device()

    log.info("MMAudio: loading models (device=%s, dtype=%s)", device, dtype)

    # ── Resolve model paths ───────────────────────────────────────
    model_path = _find_or_download_model("model")
    vae_path = _find_or_download_model("vae")
    synchformer_path = _find_or_download_model("synchformer")
    clip_path = _find_or_download_model("clip")
    bigvgan_dir = _find_or_download_bigvgan()

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
                net, name, device=device, dtype=dtype, value=model_sd[name]
            )
        del model_sd
        log.info("MMAudio: loaded model via accelerate (%s, v2=%s)", size, is_v2)

    except ImportError:
        # Fallback: standard loading
        log.info("MMAudio: accelerate not available — using standard loading")
        if size == "small":
            net = get_my_mmaudio("small_16k").to(device, dtype).eval()
        else:
            model_name = "large_44k_v2" if is_v2 else "large_44k"
            net = get_my_mmaudio(model_name).to(device, dtype).eval()
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
                synchformer, name, device=device, dtype=dtype, value=synch_sd[name]
            )
    except ImportError:
        synchformer = Synchformer().eval()
        synchformer.load_state_dict(synch_sd)
        synchformer = synchformer.to(device, dtype)
    del synch_sd
    log.info("MMAudio: loaded Synchformer")

    # ── Load BigVGAN vocoder ──────────────────────────────────────
    bigvgan_vocoder = BigVGANv2.from_pretrained(bigvgan_dir).eval().to(device, dtype)
    log.info("MMAudio: loaded BigVGAN vocoder")

    # ── Load VAE ──────────────────────────────────────────────────
    vae_sd = _load_state_dict(vae_path, device=str(offload_device))
    vae = AutoEncoderModule(
        vae_state_dict=vae_sd,
        bigvgan_vocoder=bigvgan_vocoder,
        mode="44k",
    )
    vae = vae.eval().to(device, dtype)
    del vae_sd
    log.info("MMAudio: loaded VAE")

    # ── Load CLIP ─────────────────────────────────────────────────
    clip_sd = _load_state_dict(clip_path, device=str(offload_device))

    try:
        from open_clip import CLIP as OpenCLIP
        import json

        # Load CLIP config
        clip_config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "mmaudio_clip_config.json",
        )
        if not os.path.isfile(clip_config_path):
            # Try from mmaudio package
            import mmaudio
            pkg_dir = os.path.dirname(os.path.abspath(mmaudio.__file__ or ""))
            clip_config_path = os.path.join(pkg_dir, "..", "configs", "DFN5B-CLIP-ViT-H-14-384.json")

        if os.path.isfile(clip_config_path):
            with open(clip_config_path) as f:
                clip_config = json.load(f)
            model_cfg = clip_config.get("model_cfg", clip_config)
        else:
            # Hardcode the known config for DFN5B-CLIP-ViT-H-14-384
            model_cfg = {
                "embed_dim": 1024,
                "vision_cfg": {
                    "image_size": 384,
                    "layers": 32,
                    "width": 1280,
                    "head_width": 80,
                    "mlp_ratio": 4,
                    "patch_size": 14,
                },
                "text_cfg": {
                    "context_length": 77,
                    "vocab_size": 49408,
                    "width": 1024,
                    "heads": 16,
                    "layers": 24,
                },
            }

        try:
            from accelerate import init_empty_weights
            from accelerate.utils import set_module_tensor_to_device

            with init_empty_weights():
                try:
                    clip_model = OpenCLIP(**model_cfg).eval()
                except TypeError:
                    model_cfg["nonscalar_logit_scale"] = True
                    clip_model = OpenCLIP(**model_cfg).eval()

            for name, _param in clip_model.named_parameters():
                if name in clip_sd:
                    set_module_tensor_to_device(
                        clip_model, name, device=device, dtype=dtype, value=clip_sd[name]
                    )
        except ImportError:
            try:
                clip_model = OpenCLIP(**model_cfg).eval()
            except TypeError:
                model_cfg["nonscalar_logit_scale"] = True
                clip_model = OpenCLIP(**model_cfg).eval()
            clip_model.load_state_dict(clip_sd, strict=False)
            clip_model = clip_model.to(device, dtype)

        del clip_sd
        log.info("MMAudio: loaded CLIP")

    except ImportError:
        log.warning("open_clip not available — CLIP will be loaded by FeaturesUtils internally")
        clip_model = None
        del clip_sd

    # ── Assemble FeaturesUtils ────────────────────────────────────
    feature_utils = FeaturesUtils(
        vae=vae,
        synchformer=synchformer,
        clip_model=clip_model,
        enable_conditions=True,
    )
    feature_utils = feature_utils.to(device, dtype).eval()

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

    # ── Save output ───────────────────────────────────────────────
    sampling_rate = seq_cfg.sampling_rate
    output_path = os.path.join(output_dir, "mmaudio_output.flac")
    torchaudio.save(output_path, audio, sampling_rate)
    log.info("MMAudio: audio saved to %s", output_path)

    # ── Cleanup GPU memory ────────────────────────────────────────
    # In subprocess mode this is redundant (process exits anyway),
    # but for in-process fallback, move to offload device.
    try:
        net.to(offload_device)
        feature_utils.to(offload_device)
    except Exception:
        pass
    del net, feature_utils, fm
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return output_path


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

    sampling_rate = seq_cfg.sampling_rate
    step = _CHUNK_DURATION - _OVERLAP_SECS
    chunks = []
    offset = 0.0

    while offset < total_duration:
        chunk_dur = min(_CHUNK_DURATION, total_duration - offset)
        if chunk_dur < 1.0:
            break

        log.info(
            "MMAudio: generating chunk %.1f–%.1fs",
            offset, offset + chunk_dur,
        )

        # For video mode, we'd ideally extract the segment.
        # MMAudio's load_video reads from the start, so for chunking
        # we generate text-guided audio for each segment.
        # TODO: Once we add segment extraction, pass video segments.
        audio_chunk = _generate_chunk(
            video_path=video_path if offset == 0 else None,
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
        chunks.append(audio_chunk)
        offset += step

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


# ---------------------------------------------------------------------------
#  Subprocess wrapper (prevents CUDA memory leaks)
# ---------------------------------------------------------------------------

def generate_audio_subprocess(
    video_path: Optional[str] = None,
    prompt: str = "",
    negative_prompt: str = "",
    duration: Optional[float] = None,
    seed: int = 42,
    cfg_strength: float = 4.5,
    output_dir: Optional[str] = None,
) -> str:
    """Run generate_audio() in a subprocess to avoid CUDA memory leaks.

    Same interface as generate_audio(). All args are JSON-serialized to
    the child process via stdin, and the audio path is returned via stdout.
    Falls back to in-process generate_audio() if the subprocess fails.
    """
    import json

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_mmaudio_")
        atexit.register(lambda d=output_dir: _cleanup_dir(d))

    args_dict = {
        "video_path": video_path,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "duration": duration,
        "seed": seed,
        "cfg_strength": cfg_strength,
        "output_dir": output_dir,
    }

    # Inline script for the child process
    child_script = """
import sys, json, importlib.util
args = json.loads(sys.stdin.read())
mod_path = args.pop("_module_path")
spec = importlib.util.spec_from_file_location("mmaudio_synthesizer", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.generate_audio(**args)
print("RESULT:" + result, flush=True)
"""

    try:
        _this_dir = os.path.dirname(os.path.abspath(__file__))
        _project_root = os.path.dirname(_this_dir)
        _module_path = os.path.abspath(__file__)

        args_dict["_module_path"] = _module_path

        env = os.environ.copy()
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = _project_root + (
            os.pathsep + existing_pp if existing_pp else ""
        )
        env["FFMPEGA_MMAUDIO_MODEL_DIR"] = str(_get_model_dir())
        env["PYTHONUNBUFFERED"] = "1"

        log.info(
            "MMAudio subprocess: starting (video=%s, prompt=%r)",
            video_path, prompt,
        )

        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", child_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=_project_root,
            env=env,
        )

        # Send args via stdin
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(args_dict))
        proc.stdin.close()

        # Stream stderr in real-time
        import threading

        def _stream_stderr():
            try:
                assert proc.stderr is not None
                for line in proc.stderr:
                    line = line.rstrip()
                    if not line:
                        continue
                    if "pkg_resources" in line or "slated for removal" in line:
                        continue
                    log.info("[MMAudio] %s", line)
            except ValueError:
                pass
            finally:
                try:
                    if proc.stderr is not None:
                        proc.stderr.close()
                except OSError:
                    pass

        stderr_thread = threading.Thread(target=_stream_stderr, daemon=True)
        stderr_thread.start()

        # Wait for process (timeout: 30 minutes for long videos)
        try:
            proc.wait(timeout=1800)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError("MMAudio subprocess timed out after 30 minutes")

        try:
            assert proc.stdout is not None
            stdout_data = proc.stdout.read()
        finally:
            if proc.stdout is not None:
                proc.stdout.close()

        stderr_thread.join(timeout=5)

        if proc.returncode != 0:
            raise RuntimeError(
                f"MMAudio subprocess exited with code {proc.returncode}"
            )

        # Extract result path
        audio_path = None
        for line in stdout_data.strip().split("\n"):
            if line.startswith("RESULT:"):
                audio_path = line[7:].strip()
                break

        if not audio_path:
            raise RuntimeError(
                "MMAudio subprocess did not return a result path"
            )
        if not os.path.isfile(audio_path):
            raise RuntimeError(
                f"MMAudio subprocess returned non-existent path: {audio_path}"
            )

        log.info("MMAudio subprocess: completed — audio at %s", audio_path)
        return audio_path

    except Exception as e:
        log.error("MMAudio subprocess failed: %s", e)
        log.info("MMAudio: falling back to in-process generation")
        _free_vram()
        return generate_audio(
            video_path=video_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            duration=duration,
            seed=seed,
            cfg_strength=cfg_strength,
            output_dir=output_dir,
        )


def _cleanup_dir(d: str):
    """Remove a temporary directory on exit."""
    import shutil
    try:
        shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass
