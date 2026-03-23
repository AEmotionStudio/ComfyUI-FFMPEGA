# coding: utf-8
"""FlashVSR Synthesizer — one-step diffusion video super-resolution.

Uses the vendored FlashVSR library (core/flashvsr/) based on the
1038lab BSA-free implementation, which replaces Block-Sparse Attention
with a tiered fallback: sparse_sageattn → sageattn → flash_attn →
F.scaled_dot_product_attention.

Key capabilities:
- **4× video super-resolution** via one-step diffusion
- **Three variants**: Full (best quality), Tiny (fast), Tiny Long (low VRAM)
- **SageAttention optimization**: ~20-30% speedup when available
- **Tiled processing**: for high-res videos on limited VRAM
- **Wavelet color correction**: prevents color shift from diffusion

Model: FlashVSR v1.1 (CVPR 2026)
VRAM:  ~8-16 GB depending on variant and tiling
Speed: Near real-time on A100, ~1-3 FPS on RTX 4070

License: GPL-3.0
"""

from __future__ import annotations

import gc
import logging
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

try:
    from .sanitize import validate_video_path, validate_output_file_path
except ImportError:
    from core.sanitize import validate_video_path, validate_output_file_path  # type: ignore

try:
    from .bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin
except ImportError:
    from core.bin_paths import get_ffmpeg_bin as _get_ffmpeg_bin  # type: ignore

log = logging.getLogger("ffmpega")


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

_HF_REPO_MIRROR = "AEmotionStudio/flashvsr-models"
_HF_REPO_UPSTREAM = "1038lab/FlashVSR"
_MODEL_DIR_NAME = "FlashVSR"

_REQUIRED_FILES = [
    "FlashVSR1_1.safetensors",
    "Wan2.1_VAE.safetensors",
    "LQ_proj_in.safetensors",
    "TCDecoder.safetensors",
    "Prompt.safetensors",
]

# Minimum frame count for FlashVSR
_MIN_FRAMES = 21

# Model variant configs
FLASHVSR_CONFIGS = {
    "flashvsr_full": {
        "description": "FlashVSR Full — best quality, full VAE decode (~12-16 GB VRAM)",
        "mode": "full",
        "sparse_ratio": 2.0,
        "kv_ratio": 3.0,
        "local_range": 11,
        "size": "~5 GB (shared weights)",
    },
    "flashvsr_tiny": {
        "description": "FlashVSR Tiny — fast, TCDecoder (~8-12 GB VRAM)",
        "mode": "tiny",
        "sparse_ratio": 2.0,
        "kv_ratio": 2.0,
        "local_range": 11,
        "size": "~5 GB (shared weights)",
    },
    "flashvsr_tiny_long": {
        "description": "FlashVSR Tiny Long — streaming for long videos, low VRAM (~8-12 GB)",
        "mode": "tiny-long",
        "sparse_ratio": 2.0,
        "kv_ratio": 2.0,
        "local_range": 11,
        "size": "~5 GB (shared weights)",
    },
}

# Cached pipeline state
_pipeline = None
_pipeline_mode: str = ""


# ---------------------------------------------------------------------------
#  Model directory and downloading
# ---------------------------------------------------------------------------

def _get_model_dir() -> Path:
    """Get or create the FlashVSR model directory.

    Checks (in order):
    1. FFMPEGA_FLASHVSR_MODEL_DIR env var
    2. ComfyUI/models/FlashVSR/ (standard convention)
    3. Extension's own models/FlashVSR/ (fallback)
    """
    env_dir = os.environ.get("FFMPEGA_FLASHVSR_MODEL_DIR")
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


def _download_models(model_dir: Path) -> None:
    """Download FlashVSR model weights from HuggingFace if not present."""
    missing = [f for f in _REQUIRED_FILES if not (model_dir / f).is_file()]
    if not missing:
        return

    try:
        from . import model_manager as _mm
    except ImportError:
        from core import model_manager as _mm  # type: ignore

    _mm.require_downloads_allowed("flashvsr")

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise ImportError(
            "huggingface_hub is required to download FlashVSR models. "
            "Install with: pip install huggingface_hub"
        )

    log.info("FlashVSR: missing model files: %s. Downloading...", missing)

    # Try AEmotionStudio mirror first, fall back to upstream
    for repo_id in (_HF_REPO_MIRROR, _HF_REPO_UPSTREAM):
        try:
            log.info("FlashVSR: trying %s ...", repo_id)
            _mm.download_with_progress(
                "flashvsr",
                lambda _repo=repo_id: snapshot_download(
                    repo_id=_repo,
                    local_dir=str(model_dir),
                    local_dir_use_symlinks=False,
                    resume_download=True,
                ),
                extra="~5 GB total",
            )
            log.info("FlashVSR models downloaded from %s", repo_id)
            return
        except Exception as e:
            log.warning("FlashVSR: download from %s failed: %s", repo_id, e)

    raise RuntimeError(
        "Failed to download FlashVSR models from both mirror and upstream. "
        f"Tried: {_HF_REPO_MIRROR}, {_HF_REPO_UPSTREAM}"
    )


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Free all GPU VRAM before loading FlashVSR."""
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="flashvsr_synthesizer")


def cleanup() -> None:
    """Free GPU memory and clear cached pipeline."""
    global _pipeline, _pipeline_mode
    if _pipeline is not None:
        del _pipeline
    _pipeline = None
    _pipeline_mode = ""
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
    log.info("FlashVSR pipeline unloaded")


def _flush_vram() -> None:
    """Lightweight inter-phase GPU flush (no model unloading)."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


# ---------------------------------------------------------------------------
#  Dtype patching
# ---------------------------------------------------------------------------

def _patch_dit_dtypes():
    """Patch the vendored wan_video_dit to use float32 for positional embeddings.

    Prevents NaN issues with bfloat16/float16 in sinusoidal embeddings and RoPE.
    """
    try:
        from .flashvsr.models import wan_video_dit as _dit
    except ImportError:
        from core.flashvsr.models import wan_video_dit as _dit  # type: ignore

    if getattr(_dit, "_flashvsr_dtype_patch", False):
        return

    import torch
    from einops import rearrange

    def sinusoidal_embedding_1d(dim, position):
        work_dtype = torch.float32
        half_dim = max(dim // 2, 1)
        scale = torch.arange(half_dim, dtype=work_dtype, device=position.device)
        inv_freq = torch.pow(10000.0, -scale / half_dim)
        sinusoid = torch.outer(position.to(work_dtype), inv_freq)
        x = torch.cat([torch.cos(sinusoid), torch.sin(sinusoid)], dim=1)
        return x.to(position.dtype)

    def precompute_freqs_cis(dim: int, end: int = 1024, theta: float = 10000.0):
        work_dtype = torch.float32
        half_dim = max(dim // 2, 1)
        base = torch.arange(0, dim, 2, dtype=work_dtype)[:half_dim]
        freqs = torch.pow(theta, -base / max(dim, 1))
        steps = torch.arange(end, dtype=work_dtype)
        angles = torch.outer(steps, freqs)
        return torch.polar(torch.ones_like(angles), angles)

    def rope_apply(x, freqs, num_heads):
        x = rearrange(x, "b s (n d) -> b s n d", n=num_heads)
        orig_dtype = x.dtype
        work_dtype = torch.float32 if orig_dtype in (torch.float16, torch.bfloat16) else orig_dtype
        reshaped = x.to(work_dtype).reshape(x.shape[0], x.shape[1], x.shape[2], -1, 2)
        x_complex = torch.view_as_complex(reshaped)
        freqs = freqs.to(dtype=x_complex.dtype, device=x_complex.device)
        x_out = torch.view_as_real(x_complex * freqs).flatten(2)
        return x_out.to(orig_dtype)

    _dit.sinusoidal_embedding_1d = sinusoidal_embedding_1d
    _dit.precompute_freqs_cis = precompute_freqs_cis
    _dit.rope_apply = rope_apply
    _dit._flashvsr_dtype_patch = True


# ---------------------------------------------------------------------------
#  Pipeline loading
# ---------------------------------------------------------------------------

def _load_pipeline(mode: str = "full"):
    """Load and cache the FlashVSR pipeline.

    Args:
        mode: Pipeline variant — "full", "tiny", or "tiny-long".

    Returns:
        Initialized FlashVSR pipeline ready for inference.
    """
    global _pipeline, _pipeline_mode

    if _pipeline is not None and _pipeline_mode == mode:
        return _pipeline

    # Mode changed — discard old pipeline
    if _pipeline is not None:
        log.info("FlashVSR: mode changed (%s → %s), reloading", _pipeline_mode, mode)
        cleanup()

    import torch
    from safetensors.torch import load_file  # noqa: F811

    # Apply dtype patches before importing models
    _patch_dit_dtypes()

    try:
        from .flashvsr import ModelManager, FlashVSRFullPipeline, FlashVSRTinyPipeline, FlashVSRTinyLongPipeline
        from .flashvsr.models.TCDecoder import build_tcdecoder
        from .flashvsr.models.utils import Buffer_LQ4x_Proj
    except ImportError:
        from core.flashvsr import ModelManager, FlashVSRFullPipeline, FlashVSRTinyPipeline, FlashVSRTinyLongPipeline  # type: ignore
        from core.flashvsr.models.TCDecoder import build_tcdecoder  # type: ignore
        from core.flashvsr.models.utils import Buffer_LQ4x_Proj  # type: ignore

    model_dir = _get_model_dir()
    _download_models(model_dir)

    _free_vram()

    # Resolve device and dtype
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16
    if torch.cuda.is_available():
        cap = torch.cuda.get_device_capability()
        if cap[0] < 8:
            dtype = torch.float16
            log.info("FlashVSR: Using float16 (GPU compute capability %d.%d)", *cap)

    ckpt = str(model_dir / "FlashVSR1_1.safetensors")
    vae = str(model_dir / "Wan2.1_VAE.safetensors")
    lq = str(model_dir / "LQ_proj_in.safetensors")
    tcd = str(model_dir / "TCDecoder.safetensors")
    prompt = str(model_dir / "Prompt.safetensors")

    log.info("FlashVSR: loading pipeline (mode=%s, dtype=%s)", mode, dtype)

    mm = ModelManager(torch_dtype=dtype, device="cpu")

    if mode == "full":
        mm.load_models([ckpt, vae])
        pipe = FlashVSRFullPipeline.from_model_manager(mm, device=device)
        pipe.vae.model.encoder = None
        pipe.vae.model.conv1 = None
    else:
        mm.load_models([ckpt])
        if mode == "tiny":
            pipe = FlashVSRTinyPipeline.from_model_manager(mm, device=device)
        else:  # tiny-long
            pipe = FlashVSRTinyLongPipeline.from_model_manager(mm, device=device)

        pipe.TCDecoder = build_tcdecoder([512, 256, 128, 128], device, dtype, 16 + 768)
        pipe.TCDecoder.load_state_dict(load_file(tcd, device=device), strict=False)
        pipe.TCDecoder.clean_mem()

    # Load LQ projection
    pipe.denoising_model().LQ_proj_in = Buffer_LQ4x_Proj(3, 1536, 1).to(device, dtype)
    if os.path.exists(lq):
        lq_state_dict = load_file(lq, device="cpu")
        cleaned = {}
        prefix = "LQ_proj_in."
        for k, v in lq_state_dict.items():
            cleaned[k[len(prefix):] if k.startswith(prefix) else k] = v
        pipe.denoising_model().LQ_proj_in.load_state_dict(cleaned, strict=True)

    pipe.denoising_model().LQ_proj_in.to(device)
    pipe.to(device, dtype)
    pipe.enable_vram_management(num_persistent_param_in_dit=None)
    pipe.init_cross_kv(prompt_path=prompt)
    pipe.load_models_to_device(["dit", "vae"])

    _pipeline = pipe
    _pipeline_mode = mode
    log.info("FlashVSR pipeline loaded (mode=%s)", mode)
    return _pipeline


# ---------------------------------------------------------------------------
#  Video processing helpers
# ---------------------------------------------------------------------------

def _compute_dims(w: int, h: int, scale: int, align: int = 128):
    """Compute scaled and aligned dimensions."""
    sw, sh = w * scale, h * scale
    tw = math.ceil(sw / align) * align
    th = math.ceil(sh / align) * align
    return sw, sh, tw, th


def _align_frames(n: int) -> int:
    """Align frame count for FlashVSR's temporal requirements."""
    return 0 if n < 1 else ((n - 1) // 8) * 8 + 1


def _repeat_last_frame(frames, repeat_count: int):
    """Repeat the last frame for padding."""
    import torch
    if repeat_count <= 0:
        return frames
    repeats = [repeat_count] + [1 for _ in range(frames.ndim - 1)]
    tail = frames[-1:].repeat(*repeats)
    return torch.cat([frames, tail], dim=0)


def _pad_video_sequence(frames):
    """Pad video to meet FlashVSR frame alignment requirements."""
    frames = _repeat_last_frame(frames, 2)
    added_frames = 0
    remainder = (frames.shape[0] - 5) % 8
    if remainder != 0:
        added_frames = 8 - remainder
        frames = _repeat_last_frame(frames, added_frames)
    return frames, added_frames


def _restore_video_sequence(result, added_frames: int, expected_frames: int):
    """Remove padding and duplicate frames from FlashVSR output."""
    if added_frames > 0 and result.shape[0] > added_frames:
        result = result[:-added_frames]
    if result.shape[0] > 2:
        result = result[2:]  # Remove first 2 duplicated frames
    # Adjust to expected count
    if result.shape[0] > expected_frames:
        result = result[:expected_frames]
    elif result.shape[0] < expected_frames:
        import torch
        padding = result[-1:].repeat(expected_frames - result.shape[0], *([1] * (result.ndim - 1)))
        result = torch.cat([result, padding], dim=0)
    return result


def _prepare_video(frames, device: str, scale: int, dtype):
    """Prepare video frames for FlashVSR input.

    Converts [N,H,W,C] float32 [0,1] → [1,C,F,H,W] dtype [-1,1].
    """
    import torch
    import torch.nn.functional as F

    N, H, W, C = frames.shape
    sw, sh, tw, th = _compute_dims(W, H, scale)

    num_padded = N + 4
    aligned = _align_frames(num_padded)
    if aligned == 0:
        raise ValueError(f"Need at least {_MIN_FRAMES} frames, got {N}")

    processed = []
    for i in range(aligned):
        if i < 2:
            idx = 0
        elif i > N + 1:
            idx = N - 1
        else:
            idx = i - 2

        frame = frames[idx].permute(2, 0, 1).unsqueeze(0)
        upscaled = F.interpolate(frame, size=(sh, sw), mode='bicubic', align_corners=False)

        pad_h, pad_w = th - sh, tw - sw
        if pad_h > 0 or pad_w > 0:
            upscaled = F.pad(upscaled, (0, pad_w, 0, pad_h), mode='replicate')

        normalized = upscaled * 2.0 - 1.0
        processed.append(normalized.squeeze(0).cpu().to(dtype))

    video = torch.stack(processed, 0).permute(1, 0, 2, 3).unsqueeze(0)
    return video, th, tw, aligned, sh, sw


def _to_frames(video):
    """Convert FlashVSR output [1,C,F,H,W] → [F,H,W,C] float32 [0,1]."""
    from einops import rearrange
    v = video.squeeze(0)
    v = rearrange(v, "C F H W -> F H W C")
    return (v.float() + 1.0) / 2.0


def _calc_tiles(h: int, w: int, size: int, overlap: int):
    """Calculate tile positions for tiled processing."""
    tiles = []
    stride = size - overlap
    rows = math.ceil((h - overlap) / stride)
    cols = math.ceil((w - overlap) / stride)

    for r in range(rows):
        for c in range(cols):
            y1, x1 = r * stride, c * stride
            y2, x2 = min(y1 + size, h), min(x1 + size, w)
            if y2 - y1 < size:
                y1 = max(0, y2 - size)
            if x2 - x1 < size:
                x1 = max(0, x2 - size)
            tiles.append((x1, y1, x2, y2))
    return tiles


def _make_tile_mask(h: int, w: int, overlap: int):
    """Create a blending mask for seamless tile stitching."""
    import torch
    mask = torch.ones(1, 1, h, w)
    ramp = torch.linspace(0, 1, overlap)

    mask[:, :, :, :overlap] *= ramp.view(1, 1, 1, -1)
    mask[:, :, :, -overlap:] *= ramp.flip(0).view(1, 1, 1, -1)
    mask[:, :, :overlap, :] *= ramp.view(1, 1, -1, 1)
    mask[:, :, -overlap:, :] *= ramp.flip(0).view(1, 1, -1, 1)
    return mask


# ---------------------------------------------------------------------------
#  Core inference
# ---------------------------------------------------------------------------

def _run_full(frames, pipe, scale: int, sparse_ratio: float, kv_ratio: float,
              local_range: int, color_fix: bool, unload_dit: bool,
              vae_tiling: bool, seed: int, device: str, dtype):
    """Run FlashVSR on full video (no tiling)."""
    vid, th, tw, nf, sh, sw = _prepare_video(frames, device, scale, dtype)

    if "long" not in pipe.__class__.__name__.lower():
        vid = vid.to(device)

    out = pipe(
        prompt="", negative_prompt="", cfg_scale=1.0, num_inference_steps=1,
        seed=seed, tiled=vae_tiling, LQ_video=vid,
        num_frames=nf, height=th, width=tw, is_full_block=False, if_buffer=True,
        topk_ratio=sparse_ratio * 768 * 1280 / (th * tw),
        kv_ratio=kv_ratio, local_range=local_range,
        color_fix=color_fix, unload_dit=unload_dit,
    )

    return _to_frames(out).cpu()[:frames.shape[0], :sh, :sw, :]


def _run_tiled(frames, pipe, scale: int, tile_size: int, tile_overlap: int,
               sparse_ratio: float, kv_ratio: float, local_range: int,
               color_fix: bool, unload_dit: bool, vae_tiling: bool,
               seed: int, device: str, dtype):
    """Run FlashVSR with tiled processing for lower VRAM."""
    import torch
    try:
        from .flashvsr.models.utils import clean_vram
    except ImportError:
        from core.flashvsr.models.utils import clean_vram  # type: ignore

    N, H, W, C = frames.shape
    nf = _align_frames(N + 4) - 4
    oh, ow = H * scale, W * scale

    canvas = torch.zeros((nf, oh, ow, C), dtype=torch.float32)
    weights = torch.zeros_like(canvas)
    tiles = _calc_tiles(H, W, tile_size, tile_overlap)

    log.info("FlashVSR: processing %d tiles", len(tiles))

    for i, (x1, y1, x2, y2) in enumerate(tiles):
        log.info("FlashVSR: tile %d/%d", i + 1, len(tiles))

        tf = frames[:, y1:y2, x1:x2, :]
        tv_tensor, th, tw, tnf, tsh, tsw = _prepare_video(tf, device, scale, dtype)

        if "long" not in pipe.__class__.__name__.lower():
            tv_tensor = tv_tensor.to(device)

        tout = pipe(
            prompt="", negative_prompt="", cfg_scale=1.0, num_inference_steps=1,
            seed=seed, tiled=vae_tiling, LQ_video=tv_tensor,
            num_frames=tnf, height=th, width=tw, is_full_block=False, if_buffer=True,
            topk_ratio=sparse_ratio * 768 * 1280 / (th * tw),
            kv_ratio=kv_ratio, local_range=local_range,
            color_fix=color_fix, unload_dit=unload_dit,
        )

        tres = _to_frames(tout).cpu()[:nf, :tsh, :tsw, :]

        ah, aw = tres.shape[1], tres.shape[2]
        mask = _make_tile_mask(ah, aw, min(tile_overlap * scale, ah // 4, aw // 4))
        mask = mask.permute(0, 2, 3, 1)

        oy1, ox1 = y1 * scale, x1 * scale
        oy2, ox2 = min(oy1 + ah, oh), min(ox1 + aw, ow)
        ath, atw = oy2 - oy1, ox2 - ox1

        tres = tres[:, :ath, :atw, :]
        mask = mask[:, :ath, :atw, :]

        canvas[:, oy1:oy2, ox1:ox2, :] += tres * mask
        weights[:, oy1:oy2, ox1:ox2, :] += mask

        del tv_tensor, tout, tres
        if (i + 1) % 4 == 0 or i == len(tiles) - 1:
            clean_vram()

    weights[weights == 0] = 1.0
    return canvas / weights


# ---------------------------------------------------------------------------
#  Frame I/O (FFmpeg-based, our pattern)
# ---------------------------------------------------------------------------

def _extract_frames(video_path: str):
    """Extract video frames as [N,H,W,C] float32 [0,1] tensor + fps."""
    from PIL import Image
    import torch

    tmpdir = tempfile.mkdtemp(prefix="flashvsr_in_")
    subprocess.run(
        [_get_ffmpeg_bin(), "-i", video_path, "-q:v", "2",
         os.path.join(tmpdir, "%06d.png")],
        capture_output=True, check=True,
    )

    frame_files = sorted(Path(tmpdir).glob("*.png"))
    if not frame_files:
        raise RuntimeError(f"No frames extracted from {video_path}")

    frames = []
    for f in frame_files:
        img = Image.open(f).convert("RGB")
        arr = np.array(img, dtype=np.float32) / 255.0
        frames.append(arr)

    frames_tensor = torch.from_numpy(np.stack(frames, axis=0))

    # Get FPS
    try:
        from .sam3_masker import _get_video_fps
    except ImportError:
        from core.sam3_masker import _get_video_fps  # type: ignore
    fps = _get_video_fps(video_path)

    return frames_tensor, fps, tmpdir


def _encode_video(frames, output_path: str, fps: float, audio_src: str | None = None) -> str:
    """Encode [N,H,W,C] float32 [0,1] frames to video."""
    tmpdir = tempfile.mkdtemp(prefix="flashvsr_out_")
    frames_np = (frames.clamp(0, 1).numpy() * 255).astype(np.uint8)

    from PIL import Image
    for i, frame in enumerate(frames_np):
        Image.fromarray(frame).save(os.path.join(tmpdir, f"{i:06d}.png"))

    cmd = [
        _get_ffmpeg_bin(), "-y",
        "-framerate", str(fps),
        "-i", os.path.join(tmpdir, "%06d.png"),
    ]
    if audio_src and os.path.isfile(audio_src):
        cmd += ["-i", audio_src, "-c:a", "aac", "-shortest"]
    cmd += [
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    import shutil
    try:
        shutil.rmtree(tmpdir)
    except OSError:
        pass

    return output_path


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def upscale_video(
    input_path: str,
    model_name: str = "flashvsr_full",
    output_path: Optional[str] = None,
    scale: int = 4,
    color_fix: bool = True,
    tiled: bool = True,
    tile_size: int = 384,
    tile_overlap: int = 24,
    seed: int = 1,
) -> str:
    """Upscale a video using FlashVSR.

    Args:
        input_path: path to source video
        model_name: one of FLASHVSR_CONFIGS keys
        output_path: output path (auto-generated if None)
        scale: upscale factor (2 or 4, 4 recommended)
        color_fix: enable wavelet color correction
        tiled: use tiled processing (lower VRAM)
        tile_size: tile size in pixels (before upscale)
        tile_overlap: tile overlap for blending
        seed: random seed

    Returns:
        Path to the upscaled video.
    """
    import torch

    input_path = validate_video_path(input_path)
    if output_path is not None:
        output_path = validate_output_file_path(output_path)
    else:
        tmpdir = tempfile.mkdtemp(prefix="flashvsr_result_")
        output_path = os.path.join(tmpdir, "upscaled.mp4")

    cfg = FLASHVSR_CONFIGS.get(model_name, FLASHVSR_CONFIGS["flashvsr_full"])
    mode = cfg["mode"]

    # Extract frames
    log.info("FlashVSR: extracting frames from %s", input_path)
    frames, fps, frames_dir = _extract_frames(input_path)

    original_count = frames.shape[0]
    if original_count < _MIN_FRAMES:
        raise ValueError(
            f"FlashVSR requires at least {_MIN_FRAMES} frames, got {original_count}. "
            f"Try a longer video or use a different upscaler."
        )

    # Pad for alignment
    frames, added_frames = _pad_video_sequence(frames)
    if frames.shape[0] != original_count:
        log.info("FlashVSR: padded %d → %d frames for alignment",
                 original_count, frames.shape[0])

    try:
        pipe = _load_pipeline(mode)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16
        if torch.cuda.is_available():
            cap = torch.cuda.get_device_capability()
            if cap[0] < 8:
                dtype = torch.float16

        with torch.no_grad():
            if tiled:
                result = _run_tiled(
                    frames, pipe, scale, tile_size, tile_overlap,
                    cfg["sparse_ratio"], cfg["kv_ratio"], cfg["local_range"],
                    color_fix, False, True, seed, device, dtype,
                )
            else:
                result = _run_full(
                    frames, pipe, scale,
                    cfg["sparse_ratio"], cfg["kv_ratio"], cfg["local_range"],
                    color_fix, False, True, seed, device, dtype,
                )

        # Restore original frame count
        result = _restore_video_sequence(result, added_frames, original_count)

        # Encode output
        log.info("FlashVSR: encoding %d frames to %s", result.shape[0], output_path)
        _encode_video(result, output_path, fps, audio_src=input_path)

        log.info("FlashVSR: upscale complete → %s", output_path)
        return output_path
    finally:
        # Clean up frame extraction dir
        import shutil
        try:
            shutil.rmtree(frames_dir)
        except OSError:
            pass
        _flush_vram()
        # Always cleanup pipeline after use to free VRAM
        cleanup()


def upscale_image(
    input_path: str,
    model_name: str = "flashvsr_full",
    output_path: Optional[str] = None,
    scale: int = 4,
    seed: int = 1,
) -> str:
    """Upscale a single image using FlashVSR.

    FlashVSR is optimized for video, so for single images we duplicate
    the frame to meet the minimum frame count, process, and return
    only the first output frame.

    Args:
        input_path: path to source image
        model_name: one of FLASHVSR_CONFIGS keys
        output_path: output path (auto-generated if None)
        scale: upscale factor (2 or 4)
        seed: random seed

    Returns:
        Path to the upscaled image.
    """
    import torch
    from PIL import Image

    input_path = validate_video_path(input_path)
    if output_path is not None:
        output_path = validate_output_file_path(output_path)
    else:
        tmpdir = tempfile.mkdtemp(prefix="flashvsr_img_")
        output_path = os.path.join(tmpdir, "upscaled.png")

    cfg = FLASHVSR_CONFIGS.get(model_name, FLASHVSR_CONFIGS["flashvsr_full"])
    mode = cfg["mode"]

    # Load image as single frame
    img = Image.open(input_path).convert("RGB")
    arr = np.array(img, dtype=np.float32) / 255.0
    single = torch.from_numpy(arr).unsqueeze(0)  # [1,H,W,C]

    # Duplicate to meet minimum frame count
    frames = single.repeat(_MIN_FRAMES, 1, 1, 1)

    # Pad for alignment
    frames, added_frames = _pad_video_sequence(frames)

    try:
        pipe = _load_pipeline(mode)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16
        if torch.cuda.is_available():
            cap = torch.cuda.get_device_capability()
            if cap[0] < 8:
                dtype = torch.float16

        with torch.no_grad():
            result = _run_full(
                frames, pipe, scale,
                cfg["sparse_ratio"], cfg["kv_ratio"], cfg["local_range"],
                True, False, True, seed, device, dtype,
            )

        # Take first frame
        result = _restore_video_sequence(result, added_frames, _MIN_FRAMES)
        out_frame = result[0]  # [H,W,C] float32 [0,1]
        out_img = Image.fromarray(
            (out_frame.clamp(0, 1).numpy() * 255).astype(np.uint8)
        )
        out_img.save(output_path)

        log.info("FlashVSR: image upscale complete → %s", output_path)
        return output_path
    finally:
        _flush_vram()
        cleanup()
