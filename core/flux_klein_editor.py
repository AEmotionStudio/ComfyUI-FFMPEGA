"""FLUX Klein Editor — per-frame image editing and removal using FLUX.2 Klein (4B / 9B).

Uses the ``diffusers`` library's ``Flux2KleinPipeline`` for text-guided
image editing via reference-image conditioning.  Each video frame is
processed individually with consistent seeding for temporal coherence.

Key capabilities:
- **Object removal**: mask + reference image → "fill naturally"
- **Text-guided editing**: mask + prompt → "change hair to blonde", etc.

Model: FLUX.2 [klein] 4B or 9B (Apache 2.0), selectable per call
VRAM:  ~8–13 GB (4B) / ~16–24 GB (9B), bf16/fp16 with sequential CPU offload
Speed: 4-step inference, sub-second per frame

License: Apache 2.0 (compatible with GPL-3.0)
"""

from __future__ import annotations

import gc
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

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

# Per-variant model configuration, keyed by model size ("4b" / "9b" / "9b_fp8").
# Mirrors the multi-variant pattern used by core/kiwi_edit_synthesizer.py.
_HF_REPOS = {
    "4b": "black-forest-labs/FLUX.2-klein-4B",
    "9b": "black-forest-labs/FLUX.2-klein-9B",
    "9b_fp8": "black-forest-labs/FLUX.2-klein-9B",  # same pipeline; transformer is local FP8
}
_MIRROR_REPOS = {
    "4b": "AEmotionStudio/flux-klein",
    "9b": "AEmotionStudio/flux-klein-9b",
    "9b_fp8": "AEmotionStudio/flux-klein-9b",
}
_MODEL_DIR_NAMES = {"4b": "flux_klein", "9b": "flux_klein_9b", "9b_fp8": "flux_klein_9b"}
_MM_KEYS = {
    "4b": "flux_klein",
    "9b": "flux_klein_9b",
    "9b_fp8": "flux_klein_9b_fp8",
}  # model_manager registry keys

# Standard filename for the FP8 transformer in ComfyUI's diffusion_models folder
_FP8_TRANSFORMER_FILENAME = "flux-2-klein-9b-fp8.safetensors"

_DEFAULT_MODEL = "4b"

# Default prompt for object removal (narrative prose per BFL best practices)
_REMOVAL_PROMPT = (
    "A clean, natural image where the masked region has been seamlessly "
    "filled with the surrounding background, matching lighting, texture, "
    "and perspective perfectly. No artifacts or visible boundaries."
)

# Pipeline inference defaults
_NUM_STEPS = 4
_GUIDANCE_SCALE = 1.0
_OUTPUT_SIZE = 1024  # Klein generates at 1024x1024

# Cached pipeline
_pipeline = None
_pipeline_variant: str = ""  # which variant is currently loaded


# ---------------------------------------------------------------------------
#  Model directory and downloading
# ---------------------------------------------------------------------------

def _find_fp8_transformer() -> Path:
    """Locate the local FP8 transformer safetensors file.

    Searches ComfyUI's standard diffusion_models folder and the home
    ComfyUI install.  Raises FileNotFoundError if not found so callers
    can show a clear error before attempting inference.
    """
    candidates = [
        Path(__file__).resolve().parents[3] / "models" / "diffusion_models" / _FP8_TRANSFORMER_FILENAME,
        Path.home() / "ComfyUI" / "models" / "diffusion_models" / _FP8_TRANSFORMER_FILENAME,
    ]
    try:
        import folder_paths  # type: ignore[import-not-found]
        for name in folder_paths.get_filename_list("diffusion_models"):
            p = Path(folder_paths.get_full_path("diffusion_models", name))
            if p.name == _FP8_TRANSFORMER_FILENAME and p.is_file():
                return p
    except Exception:
        pass

    for p in candidates:
        if p.is_file():
            return p

    raise FileNotFoundError(
        f"FLUX Klein 9B FP8 transformer not found.\n"
        f"Expected at: {candidates[0]}\n"
        f"Place {_FP8_TRANSFORMER_FILENAME} in "
        f"ComfyUI/models/diffusion_models/ and retry."
    )


# Standard filename for the Qwen3 text encoder in ComfyUI's text_encoders folder.
# The FLUX.2 Klein 9B pipeline uses a Qwen3-8B text encoder.  Rather than the
# sharded diffusers ``text_encoder/`` weights, we load ComfyUI's single-file
# mixed fp8/nvfp4 checkpoint and dequantise it on load (see
# ``_build_qwen_text_encoder``).  Variants that share the Qwen3 encoder:
_QWEN_TE_FILENAME = "qwen_3_8b_fp8mixed.safetensors"
_QWEN_TE_VARIANTS = {"9b", "9b_fp8"}


def _find_qwen_text_encoder() -> Path:
    """Locate the local Qwen3 text-encoder safetensors file.

    Search order:
    1. ``FFMPEGA_FLUX_KLEIN_TEXT_ENCODER`` env var (full path override)
    2. ComfyUI ``folder_paths`` "text_encoders" registry
    3. ``models/text_encoders/<filename>`` under the ComfyUI install / home

    Raises FileNotFoundError with a clear message if not found.
    """
    override = os.environ.get("FFMPEGA_FLUX_KLEIN_TEXT_ENCODER")
    if override:
        p = Path(override)
        if p.is_file():
            return p

    try:
        import folder_paths  # type: ignore[import-not-found]
        for name in folder_paths.get_filename_list("text_encoders"):
            p = Path(folder_paths.get_full_path("text_encoders", name))
            if p.name == _QWEN_TE_FILENAME and p.is_file():
                return p
    except Exception:
        pass

    for p in [
        Path(__file__).resolve().parents[3] / "models" / "text_encoders" / _QWEN_TE_FILENAME,
        Path.home() / "ComfyUI" / "models" / "text_encoders" / _QWEN_TE_FILENAME,
    ]:
        if p.is_file():
            return p

    raise FileNotFoundError(
        f"FLUX Klein Qwen3 text encoder not found.\n"
        f"Place '{_QWEN_TE_FILENAME}' in ComfyUI/models/text_encoders/ "
        f"(or set FFMPEGA_FLUX_KLEIN_TEXT_ENCODER to its full path)."
    )


def _dequantize_comfy_state_dict(te_path: Path, target_shapes: dict, dtype) -> dict:
    """Dequantise a ComfyUI mixed-fp8/nvfp4 checkpoint to a plain state dict.

    ComfyUI stores each quantised linear weight as several tensors:
    ``<L>.weight`` (fp8, or packed nvfp4 uint8), ``<L>.weight_scale`` (and
    ``<L>.weight_scale_2`` for nvfp4), plus a ``<L>.comfy_quant`` JSON blob
    naming the format.  We rebuild ComfyUI's own ``QuantizedTensor`` for each
    and call ``.dequantize()`` so the numerics exactly match ComfyUI rather
    than re-implementing the fp4 maths.  Non-quantised tensors (layernorms,
    embeddings, q/k norms) pass through.  Only keys present in
    ``target_shapes`` are kept; the original tensor shape supplies the
    ``orig_shape`` the dequantiser needs to unpack packed formats.
    """
    import torch
    from safetensors import safe_open

    try:
        from comfy.quant_ops import QUANT_ALGOS, get_layout_class
        from comfy_kitchen.tensor import QuantizedTensor
    except ImportError as e:
        raise ImportError(
            "ComfyUI quantisation support (comfy.quant_ops / comfy_kitchen) is "
            "required to load the fp8 Qwen3 text encoder."
        ) from e

    device = "cuda" if torch.cuda.is_available() else "cpu"
    out: dict = {}

    with safe_open(str(te_path), framework="pt") as f:
        keys = set(f.keys())
        quant_bases = {
            k[: -len(".comfy_quant")] for k in keys if k.endswith(".comfy_quant")
        }

        for base in sorted(quant_bases):
            wkey = base + ".weight"
            orig_shape = target_shapes.get(wkey)
            if orig_shape is None:
                continue  # key not used by our model (e.g. lm_head)

            fmt = json.loads(
                bytes(f.get_tensor(base + ".comfy_quant").tolist()).decode("utf-8")
            )["format"]
            algo = QUANT_ALGOS.get(fmt)
            if algo is None:
                raise ValueError(f"Unsupported quant format {fmt!r} for layer {base}")
            layout_cls = get_layout_class(algo["comfy_tensor_layout"])

            w = f.get_tensor(wkey).to(device)
            if fmt in ("float8_e4m3fn", "float8_e5m2"):
                scales = {"scale": f.get_tensor(base + ".weight_scale").to(device)}
            elif fmt == "nvfp4":
                scales = {
                    "scale": f.get_tensor(base + ".weight_scale_2").to(device),
                    "block_scale": f.get_tensor(base + ".weight_scale")
                    .to(device)
                    .view(torch.float8_e4m3fn),
                }
            else:
                raise ValueError(f"Unsupported quant format {fmt!r} for layer {base}")

            params = layout_cls.Params(
                orig_dtype=dtype, orig_shape=tuple(orig_shape), **scales
            )
            qt = QuantizedTensor(
                w.to(algo["storage_t"]), algo["comfy_tensor_layout"], params
            )
            out[wkey] = qt.dequantize().to(dtype=dtype, device="cpu")
            del w, qt

        # Non-quantised tensors pass straight through (cast to compute dtype).
        quant_aux = set()
        for base in quant_bases:
            quant_aux.update({
                base + ".weight", base + ".weight_scale",
                base + ".weight_scale_2", base + ".comfy_quant",
            })
        for k in keys:
            if k in quant_aux or k not in target_shapes:
                continue
            out[k] = f.get_tensor(k).to(dtype=dtype, device="cpu")

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return out


def _build_qwen_text_encoder(model_dir: Path, dtype):
    """Construct the FLUX Klein Qwen3 text encoder from ComfyUI's single-file
    fp8 checkpoint instead of the sharded diffusers ``text_encoder/`` weights.

    The pipeline only consumes intermediate hidden states (layers 9/18/27 in
    ``Flux2KleinPipeline._get_qwen3_prompt_embeds``), so the absent ``lm_head``
    is harmless — we materialise it with zeros so no parameter is left on the
    meta device (which would crash during sequential CPU offload).
    """
    import torch
    from transformers import Qwen3ForCausalLM, AutoConfig

    te_path = _find_qwen_text_encoder()
    config_dir = model_dir / "text_encoder"
    if not (config_dir / "config.json").is_file():
        raise FileNotFoundError(
            f"FLUX Klein text_encoder/config.json not found under {model_dir}"
        )
    config = AutoConfig.from_pretrained(str(config_dir))

    log.info("Building FLUX Klein Qwen3 text encoder from %s", te_path)
    try:
        from accelerate import init_empty_weights
        with init_empty_weights():
            model = Qwen3ForCausalLM(config)
    except ImportError:
        model = Qwen3ForCausalLM(config)

    target_shapes = {k: tuple(v.shape) for k, v in model.state_dict().items()}
    state = _dequantize_comfy_state_dict(te_path, target_shapes, dtype)

    # lm_head is unused by the pipeline and absent from the fp8 file; fill it
    # so no parameter remains on the meta device after assignment.
    if "lm_head.weight" in target_shapes and "lm_head.weight" not in state:
        state["lm_head.weight"] = torch.zeros(
            target_shapes["lm_head.weight"], dtype=dtype
        )

    missing, unexpected = model.load_state_dict(state, strict=False, assign=True)
    real_missing = [k for k in missing if k != "lm_head.weight"]
    if real_missing:
        log.warning(
            "Qwen3 text encoder: %d unexpected missing keys (e.g. %s)",
            len(real_missing), real_missing[:5],
        )
    if unexpected:
        log.warning(
            "Qwen3 text encoder: %d unexpected keys (e.g. %s)",
            len(unexpected), unexpected[:5],
        )

    # Guard: any parameter left on meta would crash during offload/inference.
    still_meta = [n for n, p in model.named_parameters() if p.is_meta]
    if still_meta:
        raise RuntimeError(
            f"Qwen3 text encoder has {len(still_meta)} uninitialised parameters "
            f"after load (e.g. {still_meta[:5]})"
        )

    model.eval()
    log.info("FLUX Klein Qwen3 text encoder ready (dtype=%s)", dtype)
    return model


def _get_model_dir(model: str = _DEFAULT_MODEL) -> Path:
    """Get or create the FLUX Klein model directory for the given variant.

    Checks (in order):
    1. Variant-specific env var (FFMPEGA_FLUX_KLEIN_MODEL_DIR for 4b,
       FFMPEGA_FLUX_KLEIN_9B_MODEL_DIR for 9b; set by subprocess wrapper)
    2. ComfyUI/models/<dir>/ (standard ComfyUI convention)
    3. Extension's own models/<dir>/ (fallback)

    where <dir> is ``flux_klein`` (4b) or ``flux_klein_9b`` (9b).
    """
    dir_name = _MODEL_DIR_NAMES[model]

    env_var = (
        "FFMPEGA_FLUX_KLEIN_MODEL_DIR" if model == "4b"
        else "FFMPEGA_FLUX_KLEIN_9B_MODEL_DIR"
    )
    env_dir = os.environ.get(env_var)
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    for candidate in [
        Path(__file__).resolve().parents[3] / "models" / dir_name,
        Path.home() / "ComfyUI" / "models" / dir_name,
    ]:
        if candidate.parent.is_dir():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate

    fallback = Path.home() / ".cache" / dir_name
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback




def _download_model(model_dir: Path, model: str = _DEFAULT_MODEL) -> None:
    """Download model weights from HuggingFace if not present.

    Tries the AEmotionStudio mirror first, then falls back to the
    official BFL repo, for the requested variant ("4b" / "9b").
    """
    mm_key = _MM_KEYS[model]
    mirror_repo = _MIRROR_REPOS[model]
    hf_repo = _HF_REPOS[model]

    # For the FP8 variant the transformer comes from a local safetensors file.
    # We only need the pipeline components (text encoders, scheduler, etc.).
    # model_index.json present is sufficient — the 9b snapshot may not have a
    # separate vae/ subdir depending on how it was downloaded.
    if model == "9b_fp8":
        if (model_dir / "model_index.json").is_file():
            return
    else:
        # Check if already downloaded — require both the diffusers marker
        # AND the transformer weights to avoid treating partial downloads
        # as complete (e.g. from a previous selective download).
        transformer_weights = model_dir / "transformer" / "diffusion_pytorch_model.safetensors"
        if (model_dir / "model_index.json").is_file() and transformer_weights.is_file():
            return

    try:
        from . import model_manager as _mm
    except ImportError:
        from core import model_manager as _mm  # type: ignore

    _mm.require_downloads_allowed(mm_key)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise ImportError(
            "huggingface_hub is required to download FLUX Klein. "
            "Install with: pip install huggingface_hub"
        )

    # Try AEmotionStudio mirror first
    log.info("FLUX Klein %s weights not found. Downloading...", model)
    try:
        _mm.download_with_progress(
            mm_key,
            lambda: snapshot_download(
                repo_id=mirror_repo,
                local_dir=str(model_dir),
            ),
            extra="~8 GB fp16" if model == "4b" else "~35 GB bf16",
        )
        log.info("FLUX Klein %s downloaded from AEmotionStudio mirror", model)
        return
    except Exception as e:
        log.warning("Mirror download failed: %s — trying official repo", e)

    # Fall back to official BFL repo
    _mm.download_with_progress(
        mm_key,
        lambda: snapshot_download(
            repo_id=hf_repo,
            local_dir=str(model_dir),
        ),
        extra="~8 GB" if model == "4b" else "~35 GB",
    )
    log.info("FLUX Klein %s downloaded from official repo: %s", model, hf_repo)


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------


def _free_vram() -> None:
    """Free all GPU VRAM before loading FLUX Klein.

    Delegates to the shared ``_vram_utils.free_for_module`` which handles
    ComfyUI eviction, cross-synthesizer cleanup, and CUDA cache clearing
    with a re-entrancy guard.
    """
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="flux_klein_editor")




# ---------------------------------------------------------------------------
#  Pipeline loading
# ---------------------------------------------------------------------------

def load_pipeline(model: str = _DEFAULT_MODEL):
    """Load and cache the FLUX Klein pipeline for the given variant.

    Downloads from the AEmotionStudio mirror if not already present.
    The pipeline is cached per-variant: requesting a different variant
    than the one currently loaded evicts the old pipeline first.

    Args:
        model: which variant to load — "4b" (default), "9b", or "9b_fp8".
            "9b_fp8" loads the 9b pipeline components from flux_klein_9b/
            and swaps in the transformer weights from the local FP8 file
            (ComfyUI/models/diffusion_models/flux-2-klein-9b-fp8.safetensors).

    Returns:
        Flux2KleinPipeline instance ready for inference.

    Raises:
        ImportError: If diffusers is not installed or too old.
        FileNotFoundError: If "9b_fp8" is selected but the local FP8 file
            is not found in ComfyUI/models/diffusion_models/.
        RuntimeError: If model download fails.
    """
    global _pipeline, _pipeline_variant

    if model not in _MODEL_DIR_NAMES:
        raise ValueError(
            f"Unknown FLUX Klein model variant {model!r}; "
            f"expected one of {sorted(_MODEL_DIR_NAMES)}"
        )

    # Return the cached pipeline only when it matches the requested
    # variant — otherwise evict it before loading the new one.
    if _pipeline is not None:
        if _pipeline_variant == model:
            return _pipeline
        log.info(
            "FLUX Klein variant change (%s → %s); reloading pipeline",
            _pipeline_variant, model,
        )
        cleanup()

    try:
        from diffusers import Flux2KleinPipeline  # type: ignore[attr-defined]
    except ImportError:
        raise ImportError(
            "diffusers with FLUX.2 Klein support is required. "
            "Install with: pip install git+https://github.com/huggingface/diffusers.git"
        )

    model_dir = _get_model_dir(model)
    _download_model(model_dir, model)

    _free_vram()

    log.info("Loading FLUX Klein %s pipeline from %s", model, model_dir)

    import torch

    # Use bfloat16 for best quality on supported hardware,
    # fall back to float16 if bfloat16 is not supported
    dtype = torch.bfloat16
    if torch.cuda.is_available():
        cap = torch.cuda.get_device_capability()
        if cap[0] < 8:  # Pre-Ampere GPUs don't support bfloat16 well
            dtype = torch.float16
            log.info("Using float16 (GPU compute capability %d.%d)", *cap)

    # The 9b variants use a Qwen3-8B text encoder.  Load it from ComfyUI's
    # single-file fp8 checkpoint (dequantised) instead of the sharded
    # text_encoder/ weights — passing the instance makes diffusers skip the
    # text_encoder/ subfolder entirely.
    te_kwargs = {}
    if model in _QWEN_TE_VARIANTS:
        te_kwargs["text_encoder"] = _build_qwen_text_encoder(model_dir, dtype)

    pipe = Flux2KleinPipeline.from_pretrained(
        str(model_dir),
        torch_dtype=dtype,
        **te_kwargs,
    )

    if model == "9b_fp8":
        # Swap in the local FP8 transformer weights.
        # The FP8 safetensors contains only the transformer state dict
        # (ComfyUI diffusion_models convention).  We cast to the pipeline
        # dtype on load so diffusers' sequential-offload path works unchanged.
        fp8_path = _find_fp8_transformer()
        log.info("Loading FP8 transformer weights from %s", fp8_path)
        from safetensors.torch import load_file as _st_load_file
        fp8_sd = {k: v.to(dtype) for k, v in _st_load_file(str(fp8_path)).items()}
        missing, unexpected = pipe.transformer.load_state_dict(fp8_sd, strict=False)
        if missing:
            log.warning("FP8 transformer: %d missing keys (e.g. %s)", len(missing), missing[:3])
        if unexpected:
            log.warning("FP8 transformer: %d unexpected keys (e.g. %s)", len(unexpected), unexpected[:3])
        log.info("FP8 transformer loaded and cast to %s", dtype)

    # Sequential offload moves individual *layers* to GPU one at a time,
    # keeping peak VRAM at ~2-3 GB instead of ~8+ GB.
    # We cannot use enable_model_cpu_offload() because Klein's __call__
    # invokes vae.encode() for the reference image BEFORE the transformer
    # denoising loop, but model_cpu_offload_seq is "text_encoder->
    # transformer->vae" — so the text_encoder stays on GPU during VAE
    # encoding, blowing past 12 GB cards.
    pipe.enable_sequential_cpu_offload()

    _pipeline = pipe
    _pipeline_variant = model
    log.info("FLUX Klein %s pipeline loaded successfully (dtype=%s)", model, dtype)
    return _pipeline


def cleanup() -> None:
    """Free GPU memory and clear cached pipeline.

    Follows WanVideoWrapper's cleanup pattern: release pipeline,
    empty CUDA cache, run gc, and tell ComfyUI to reclaim memory.
    """
    global _pipeline
    _pipeline = None
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
    log.info("FLUX Klein pipeline unloaded")


# ---------------------------------------------------------------------------
#  Frame I/O helpers (shared with lama_inpainter)
# ---------------------------------------------------------------------------

def _load_video_frames(video_path: str):
    """Load video frames as PIL Images.

    Returns:
        (frames_pil, fps, tmpdir)
    """
    from PIL import Image

    tmpdir = tempfile.mkdtemp(prefix="fk_frames_")
    subprocess.run(
        [
            _get_ffmpeg_bin(), "-i", video_path,
            "-q:v", "2",
            os.path.join(tmpdir, "%06d.png"),
        ],
        capture_output=True,
        check=True,
    )

    frame_files = sorted(Path(tmpdir).glob("*.png"))
    frames = [Image.open(f).convert("RGB") for f in frame_files]

    # Get FPS
    try:
        from .sam3_masker import _get_video_fps
    except ImportError:
        from core.sam3_masker import _get_video_fps  # type: ignore
    fps = _get_video_fps(video_path)

    if not frames:
        raise RuntimeError(f"No frames extracted from {video_path}")

    return frames, fps, tmpdir


def _load_mask_frames(mask_video_path: str, num_frames: int):
    """Load mask frames as PIL Images (mode 'L').

    Returns:
        (masks, tmpdir)
    """
    from PIL import Image

    tmpdir = tempfile.mkdtemp(prefix="fk_masks_")
    subprocess.run(
        [
            _get_ffmpeg_bin(), "-i", mask_video_path,
            "-q:v", "2",
            os.path.join(tmpdir, "%06d.png"),
        ],
        capture_output=True,
        check=True,
    )

    mask_files = sorted(Path(tmpdir).glob("*.png"))
    masks = [Image.open(f).convert("L") for f in mask_files[:num_frames]]

    if masks and len(masks) < num_frames:
        while len(masks) < num_frames:
            masks.append(Image.new("L", masks[0].size, 0))

    return masks, tmpdir


def _encode_video(frames: list, output_path: str, fps: float) -> str:
    """Encode PIL frames to a video file."""
    tmpdir = tempfile.mkdtemp(prefix="fk_out_")
    for i, frame in enumerate(frames):
        frame.save(os.path.join(tmpdir, f"{i:06d}.png"))

    subprocess.run(
        [
            _get_ffmpeg_bin(), "-y",
            "-framerate", str(fps),
            "-i", os.path.join(tmpdir, "%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            output_path,
        ],
        capture_output=True,
        check=True,
    )

    import shutil
    try:
        shutil.rmtree(tmpdir)
    except OSError:
        pass

    return output_path


def _encode_video_from_dir(frame_dir: str, output_path: str, fps: float) -> str:
    """Encode PNG frames from an existing directory to a video file.

    Expects **0-indexed** filenames (``000000.png``, ``000001.png``, ...).
    ``_load_video_frames`` produces 1-indexed files — do NOT pass its output
    directory here directly.

    Raises:
        FileNotFoundError: If ``000000.png`` is missing (wrong indexing).
    """
    first_frame = os.path.join(frame_dir, "000000.png")
    if not os.path.isfile(first_frame):
        raise FileNotFoundError(
            f"_encode_video_from_dir expects 0-indexed frames but "
            f"{first_frame} does not exist. Check the caller."
        )
    subprocess.run(
        [
            _get_ffmpeg_bin(), "-y",
            "-framerate", str(fps),
            "-start_number", "0",
            "-i", os.path.join(frame_dir, "%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            output_path,
        ],
        capture_output=True,
        check=True,
    )
    return output_path


# ---------------------------------------------------------------------------
#  Temporal smoothing
# ---------------------------------------------------------------------------

def _temporal_smooth(
    frames: list,
    masks: list,
    window: int = 5,
) -> list:
    """Apply temporal Gaussian smoothing to edited regions only.

    Reduces per-frame flickering by blending neighboring results
    in the masked area. Original pixels are untouched.
    """
    import numpy as np
    from scipy.ndimage import gaussian_filter1d

    n = len(frames)
    if n <= 1:
        return frames

    stack = np.stack(frames).astype(np.float32)
    mask_stack = np.stack(masks)
    # Ensure masks are 2D (H×W) — squeeze trailing channel dim if present
    if mask_stack.ndim == 4:
        mask_stack = mask_stack.squeeze(-1)
    sigma = window / 3.0
    smoothed = gaussian_filter1d(stack, sigma=sigma, axis=0)

    result = []
    for i in range(n):
        m = mask_stack[i][:, :, None]
        blended = stack[i] * (1 - m) + smoothed[i] * m
        result.append(np.clip(blended, 0, 255).astype(np.uint8))

    return result


def _temporal_smooth_adaptive(
    frames: list,
    masks: list,
    threshold: float = 30.0,
    window: int = 5,
) -> list:
    """Adaptive temporal smoothing — only correct outlier frames.

    Compares each frame to its temporal neighbors in the masked region.
    If the per-pixel difference exceeds *threshold*, blend with neighbors.
    Otherwise, keep the original frame untouched.

    This preserves sharp per-frame detail while fixing occasional
    flickering artifacts.
    """
    import numpy as np

    n = len(frames)
    if n <= 1:
        return frames

    stack = np.stack(frames).astype(np.float32)
    mask_stack = np.stack(masks)
    # Ensure masks are 2D (H×W) — squeeze trailing channel dim if present
    if mask_stack.ndim == 4:
        mask_stack = mask_stack.squeeze(-1)
    half_w = window // 2

    result = []
    for i in range(n):
        m = mask_stack[i]
        if m.max() < 0.01:
            result.append(frames[i])
            continue

        # Compute mean of neighbors in the window (exclude frame i itself
        # so the outlier doesn't dilute its own deviation signal)
        lo = max(0, i - half_w)
        hi = min(n, i + half_w + 1)
        neighbor_idx = [j for j in range(lo, hi) if j != i]
        if not neighbor_idx:
            result.append(frames[i])
            continue
        neighbors = stack[neighbor_idx]
        neighbor_mean = neighbors.mean(axis=0)

        # Per-pixel diff in masked region
        diff = np.abs(stack[i] - neighbor_mean)
        masked_diff = diff * m[:, :, None]
        avg_diff = masked_diff.sum() / max(m.sum() * 3, 1)

        if avg_diff > threshold:
            # This frame is an outlier — blend with neighbors
            blended = stack[i] * (1 - m[:, :, None]) + neighbor_mean * m[:, :, None]
            result.append(np.clip(blended, 0, 255).astype(np.uint8))
        else:
            result.append(frames[i])

    return result


# ---------------------------------------------------------------------------
#  Per-frame editing
# ---------------------------------------------------------------------------

def _edit_frame(
    pipe,
    image,
    prompt: str,
    seed: int = 42,
    reference_images: "list | None" = None,
    num_steps: int = _NUM_STEPS,
    guidance_scale: float = _GUIDANCE_SCALE,
    width: int = _OUTPUT_SIZE,
    height: int = _OUTPUT_SIZE,
):
    """Edit a single frame using FLUX Klein reference-image conditioning.

    Args:
        pipe: Flux2KleinPipeline instance
        image: PIL.Image.Image — source frame (used as reference)
        prompt: Text describing the desired edit
        seed: Random seed for reproducibility
        reference_images: Optional list of extra PIL.Image.Image references.
            When provided they are prepended to Klein's ``image`` list so
            they condition the generation alongside the source frame.
        num_steps: Number of denoising steps
        guidance_scale: CFG scale
        width: Output width in pixels
        height: Output height in pixels

    Returns:
        PIL.Image.Image — edited result at the original resolution
    """
    import torch
    from PIL import Image

    orig_w, orig_h = image.size

    # Resize to model's expected resolution
    ref_image = image.resize((width, height), Image.LANCZOS)  # type: ignore[attr-defined]

    # Build the image list: source frame first (strongest influence),
    # then extra references for style conditioning
    image_list: list = [ref_image]
    if reference_images:
        for ri in reference_images:
            image_list.append(
                ri.resize((width, height), Image.LANCZOS)  # type: ignore[attr-defined]
            )

    device = pipe._execution_device if hasattr(pipe, '_execution_device') else "cuda"
    generator = torch.Generator(device=device).manual_seed(seed)

    result = pipe(
        prompt=prompt,
        image=image_list,
        height=height,
        width=width,
        guidance_scale=guidance_scale,
        num_inference_steps=num_steps,
        generator=generator,
    ).images[0]

    # Resize back to original resolution
    if result.size != (orig_w, orig_h):
        result = result.resize((orig_w, orig_h), Image.LANCZOS)  # type: ignore[attr-defined]

    return result


def _remove_frame(
    pipe,
    image,
    mask,
    seed: int = 42,
    num_steps: int = _NUM_STEPS,
    guidance_scale: float = _GUIDANCE_SCALE,
    width: int = _OUTPUT_SIZE,
    height: int = _OUTPUT_SIZE,
):
    """Remove masked region from a single frame using FLUX Klein.

    Creates a masked version of the image (region blacked out) as the
    reference, then prompts FLUX Klein to fill naturally.

    Args:
        pipe: Flux2KleinPipeline instance
        image: PIL.Image.Image (RGB)
        mask: PIL.Image.Image (L, 255 = region to remove)
        seed: Random seed
        num_steps: Number of denoising steps
        guidance_scale: CFG scale
        width: Output width in pixels
        height: Output height in pixels

    Returns:
        PIL.Image.Image — result with object removed
    """
    import numpy as np
    import torch
    from PIL import Image

    orig_w, orig_h = image.size

    # Create masked image: black out the region to remove
    img_arr = np.array(image).copy()
    mask_arr = np.array(mask.resize(image.size, Image.NEAREST))  # type: ignore[attr-defined]
    img_arr[mask_arr > 128] = 0
    masked_image = Image.fromarray(img_arr)

    # Resize to model resolution
    ref_image = masked_image.resize((width, height), Image.LANCZOS)  # type: ignore[attr-defined]

    device = pipe._execution_device if hasattr(pipe, '_execution_device') else "cuda"
    generator = torch.Generator(device=device).manual_seed(seed)

    result = pipe(
        prompt=_REMOVAL_PROMPT,
        image=[ref_image],
        height=height,
        width=width,
        guidance_scale=guidance_scale,
        num_inference_steps=num_steps,
        generator=generator,
    ).images[0]

    # Resize back to original resolution
    if result.size != (orig_w, orig_h):
        result = result.resize((orig_w, orig_h), Image.LANCZOS)  # type: ignore[attr-defined]

    return result


# ---------------------------------------------------------------------------
#  Compositing
# ---------------------------------------------------------------------------

def _composite_frame(
    original,
    edited,
    mask,
) -> "np.ndarray":  # type: ignore[name-defined]
    """Composite edited pixels onto original using the mask.

    Args:
        original: PIL.Image.Image — original frame
        edited: PIL.Image.Image — edited/inpainted frame
        mask: PIL.Image.Image (L) — mask

    Returns:
        (H, W, 3) uint8 composited result
    """
    import numpy as np
    from PIL import Image

    orig_arr = np.array(original).astype(np.float32)
    edit_arr = np.array(edited).astype(np.float32)
    mask_pil = mask.resize(original.size, Image.NEAREST) if mask.size != original.size else mask  # type: ignore[attr-defined]
    mask_arr = np.array(mask_pil).astype(np.float32) / 255.0
    mask_3ch = mask_arr[:, :, None]

    result = orig_arr * (1 - mask_3ch) + edit_arr * mask_3ch
    return result.astype(np.uint8)


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def remove_object(
    video_path: str,
    mask_video_path: str,
    output_path: Optional[str] = None,
    smoothing: str = "none",
    model: str = _DEFAULT_MODEL,
) -> str:
    """Remove an object from a video using FLUX Klein per-frame inpainting.

    This is the main entry point called by the auto_mask handler when
    effect="remove".

    Args:
        video_path: path to the original video
        mask_video_path: path to the mask video (white = object to remove)
        output_path: output path (auto-generated if None)

    Returns:
        Path to the inpainted video.

    Raises:
        ImportError: If diffusers is not installed.
        RuntimeError: If model download or inference fails.
    """
    return edit_video(
        video_path=video_path,
        mask_video_path=mask_video_path,
        prompt=_REMOVAL_PROMPT,
        output_path=output_path,
        mode="remove",
        smoothing=smoothing,
        model=model,
    )


def edit_single_image(
    image_path: str,
    prompt: str,
    output_path: Optional[str] = None,
    seed: int = 42,
    reference_images: "list | None" = None,
    num_steps: int = _NUM_STEPS,
    guidance_scale: float = _GUIDANCE_SCALE,
    width: int = _OUTPUT_SIZE,
    height: int = _OUTPUT_SIZE,
    model: str = _DEFAULT_MODEL,
) -> str:
    """Edit a single image using FLUX Klein (no mask, full-frame).

    Loads the image, runs Klein reference-image-conditioned editing,
    and saves the result.  Designed for the ``flux_klein`` no_llm_mode
    when the input is a single image rather than a video.

    Args:
        image_path: path to the source image
        prompt: text describing the desired edit
        output_path: output path (auto-generated if None)
        seed: random seed for reproducibility
        reference_images: optional list of extra PIL images to condition on
        num_steps: number of denoising steps
        guidance_scale: classifier-free guidance scale
        width: output width in pixels
        height: output height in pixels

    Returns:
        Path to the edited image.
    """
    from PIL import Image

    image_path = validate_video_path(image_path)  # reuses path validation
    if output_path is not None:
        output_path = validate_output_file_path(output_path)

    if output_path is None:
        tmpdir = tempfile.mkdtemp(prefix="fk_img_")
        output_path = os.path.join(tmpdir, "edited.png")

    image = Image.open(image_path).convert("RGB")

    try:
        pipe = load_pipeline(model)

        import torch
        with torch.no_grad():
            result = _edit_frame(
                pipe, image, prompt, seed=seed,
                reference_images=reference_images,
                num_steps=num_steps,
                guidance_scale=guidance_scale,
                width=width,
                height=height,
            )

        result.save(output_path)
        log.info("FLUX Klein single-image edit complete: %s", output_path)
        return output_path
    finally:
        # Always free pipeline (~8 GB VRAM) after use, matching edit_video().
        cleanup()


def edit_video(
    video_path: str,
    mask_video_path: Optional[str] = None,
    prompt: str = "",
    output_path: Optional[str] = None,
    mode: str = "edit",
    smoothing: str = "none",
    reference_images: "list | None" = None,
    seed: int = 42,
    num_steps: int = _NUM_STEPS,
    guidance_scale: float = _GUIDANCE_SCALE,
    width: int = _OUTPUT_SIZE,
    height: int = _OUTPUT_SIZE,
    model: str = _DEFAULT_MODEL,
) -> str:
    """Edit a video using FLUX Klein per-frame image editing.

    Supports two modes:
    - "remove": fills masked regions with surrounding context
    - "edit": applies text-guided changes to masked regions

    When ``mask_video_path`` is ``None``, runs full-frame editing on
    every frame without compositing — the raw Klein output replaces
    the original frame entirely.  This is useful for testing temporal
    consistency and for standalone no-LLM mode.

    Args:
        video_path: path to the original video
        mask_video_path: path to the mask video (white = region to edit),
            or None for full-frame editing
        prompt: text prompt describing the desired edit
        output_path: output path (auto-generated if None)
        mode: "remove" or "edit"
        smoothing: temporal smoothing mode:
            - "none": no smoothing (best for high-quality per-frame edits)
            - "gaussian": full Gaussian blur across time (reduces flicker,
              but can muddy motion)
            - "adaptive": only smooth frames that deviate significantly
              from neighbors (preserves good frames, fixes outliers)

    Returns:
        Path to the edited video.
    """
    video_path = validate_video_path(video_path)
    if mask_video_path is not None:
        mask_video_path = validate_video_path(mask_video_path)
    if output_path is not None:
        output_path = validate_output_file_path(output_path)

    maskless = mask_video_path is None

    import numpy as np
    from PIL import Image

    if output_path is None:
        tmpdir = tempfile.mkdtemp(prefix="fk_result_")
        output_path = os.path.join(tmpdir, "edited.mp4")

    # Load frames
    log.info("Loading video frames from %s", video_path)
    frames, fps, frames_tmpdir = _load_video_frames(video_path)
    total_frames = len(frames)
    log.info(
        "Loaded %d frames at %.1f FPS (%dx%d)",
        total_frames, fps, frames[0].width, frames[0].height,
    )

    # Load masks (skip for full-frame / maskless mode)
    masks_tmpdir = None
    comp_tmpdir = None
    masks = None

    try:
        if not maskless:
            log.info("Loading mask frames from %s", mask_video_path)
            masks, masks_tmpdir = _load_mask_frames(mask_video_path, total_frames)

        # Load pipeline
        pipe = load_pipeline(model)

        # Flush VRAM fragments left by pipeline + model load so the
        # subsequent VAE encode has enough contiguous memory.
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Use a fixed seed for temporal consistency across frames
        base_seed = seed

        # Per-frame processing — write composited frames to disk to
        # avoid accumulating ~135 MiB of numpy arrays in memory.
        _mode_label = "full-frame edit" if maskless else mode
        log.info("Running FLUX Klein %s on %d frames...", _mode_label, total_frames)
        comp_tmpdir = tempfile.mkdtemp(prefix="fk_comp_")
        mask_np_list = []

        for i in range(total_frames):
            if i % 10 == 0:
                log.info("  Frame %d/%d", i + 1, total_frames)

            frame_i = frames[i]

            if maskless:
                # Full-frame mode — edit entire frame, no compositing
                with torch.no_grad():
                    edited = _edit_frame(pipe, frame_i, prompt, seed=base_seed, reference_images=reference_images, num_steps=num_steps, guidance_scale=guidance_scale, width=width, height=height)
                edited.save(os.path.join(comp_tmpdir, f"{i:06d}.png"))
                del edited
                frames[i] = None  # type: ignore[assignment]
            else:
                mask_i = masks[i]

                # Check if mask has any content (skip blank masks)
                mask_arr = np.array(mask_i)
                if mask_arr.max() < 10:
                    Image.fromarray(np.array(frame_i)).save(
                        os.path.join(comp_tmpdir, f"{i:06d}.png")
                    )
                    mask_np_list.append(
                        np.zeros(
                            (frame_i.height, frame_i.width),
                            dtype=np.float32,
                        )
                    )
                    # Release PIL sources immediately
                    frames[i] = None  # type: ignore[assignment]
                    masks[i] = None  # type: ignore[assignment]
                    continue

                # Edit or remove the frame (no_grad prevents autograd from
                # accumulating graph memory across frames)
                with torch.no_grad():
                    if mode == "remove":
                        edited = _remove_frame(pipe, frame_i, mask_i, seed=base_seed, num_steps=num_steps, guidance_scale=guidance_scale, width=width, height=height)
                    else:
                        edited = _edit_frame(pipe, frame_i, prompt, seed=base_seed, reference_images=reference_images, num_steps=num_steps, guidance_scale=guidance_scale, width=width, height=height)

                # Composite and write to disk
                result = _composite_frame(frame_i, edited, mask_i)
                Image.fromarray(result).save(
                    os.path.join(comp_tmpdir, f"{i:06d}.png")
                )
                del edited, result  # drop refs before cache flush

                mask_np = np.array(
                    mask_i.resize(frame_i.size, Image.NEAREST)  # type: ignore[attr-defined]
                    if mask_i.size != frame_i.size
                    else mask_i
                ).astype(np.float32) / 255.0
                mask_np_list.append(mask_np)

                # Release PIL sources — they're only needed once
                frames[i] = None  # type: ignore[assignment]
                masks[i] = None  # type: ignore[assignment]

            # Per-frame cleanup: gc.collect + empty_cache every frame to
            # minimise OOM risk.  Adds ~10-50 ms/frame overhead but avoids
            # accumulating unreachable tensors across long videos.
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # Temporal smoothing (only applicable in masked mode)
        if not maskless and smoothing != "none":
            # Reload composited frames from disk for smoothing pass
            comp_files = sorted(Path(comp_tmpdir).glob("*.png"))
            composited_np = [np.array(Image.open(f)) for f in comp_files]

            if smoothing == "gaussian":
                log.info("Applying temporal Gaussian smoothing...")
                smoothed = _temporal_smooth(composited_np, mask_np_list, window=5)
            else:
                log.info("Applying adaptive temporal smoothing...")
                smoothed = _temporal_smooth_adaptive(
                    composited_np, mask_np_list, threshold=30.0, window=5,
                )
            del composited_np  # free before writing

            # Overwrite disk frames with smoothed versions
            for idx, arr in enumerate(smoothed):
                Image.fromarray(arr).save(
                    os.path.join(comp_tmpdir, f"{idx:06d}.png")
                )
            del smoothed
            del mask_np_list  # free ~2.4 GB for 1080p/300-frame videos
        else:
            if maskless:
                log.info("Full-frame mode — temporal smoothing skipped")
            else:
                log.info("Temporal smoothing disabled")
            del mask_np_list  # free mask list (empty in maskless mode)

        # Encode directly from the composited frames directory
        log.info("Encoding edited video to %s", output_path)
        _encode_video_from_dir(comp_tmpdir, output_path, fps)
    finally:
        import shutil
        for d in (frames_tmpdir, masks_tmpdir, comp_tmpdir):
            if d is None:
                continue
            try:
                shutil.rmtree(d)
            except OSError:
                pass

        # Free VRAM — always runs (even on OOM) to reclaim ~8 GB.
        # The pipeline is re-loaded on next call via load_pipeline().
        cleanup()

    log.info("FLUX Klein %s complete: %s", "full-frame edit" if maskless else mode, output_path)
    return output_path

