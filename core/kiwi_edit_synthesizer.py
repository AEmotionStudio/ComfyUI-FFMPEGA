# coding: utf-8
"""Kiwi-Edit — native video editing via instruction and reference guidance.

Uses the Kiwi-Edit diffusers pipeline (Wan 2.2 TI2V-5B DiT + Qwen2.5-VL-3B
MLLM encoder) for temporally consistent video editing.  Supports three model
variants:

- **instruct-only**: text instruction → video edit
- **reference-only**: reference image → video edit
- **instruct-reference**: text + reference image → video edit

Key capabilities:
- Object removal, addition, replacement
- Style transfer, background changes
- Reference-guided precise visual control
- Native temporal consistency (no per-frame hacks)

Architecture follows the synthesizer pattern (flux_klein_editor, seedvr):
- In-process execution with GPU↔CPU pipeline offloading
- Cached model state with explicit load/cleanup
- ``comfy.model_management`` VRAM coordination
- FFmpeg frame extraction / re-encoding

License: MIT (Kiwi-Edit) / Apache-2.0 (Qwen2.5-VL)
"""

from __future__ import annotations

import gc
import logging
import os
import shutil
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

try:
    from .bin_paths import get_ffprobe_bin as _get_ffprobe_bin
except ImportError:
    from core.bin_paths import get_ffprobe_bin as _get_ffprobe_bin  # type: ignore

log = logging.getLogger("ffmpega")


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

# HF repos for each variant
_HF_REPOS = {
    "instruct": "linyq/kiwi-edit-5b-instruct-only-diffusers",
    "reference": "linyq/kiwi-edit-5b-reference-only-diffusers",
    "instruct_reference": "linyq/kiwi-edit-5b-instruct-reference-diffusers",
}

# AEmotionStudio mirror repos (BF16)
_MIRROR_REPOS = {
    "instruct": "AEmotionStudio/kiwi-edit-instruct",
    "reference": "AEmotionStudio/kiwi-edit-reference",
    "instruct_reference": "AEmotionStudio/kiwi-edit-instruct-reference",
}

# Model directory names
_MODEL_DIR_NAMES = {
    "instruct": "kiwi_edit_instruct",
    "reference": "kiwi_edit_reference",
    "instruct_reference": "kiwi_edit_instruct_reference",
}

# Pipeline defaults
_DEFAULT_STEPS = 30
_DEFAULT_GUIDANCE = 5.0
_DEFAULT_FLOW_SHIFT = 5.0
_DEFAULT_MAX_FRAMES = 81
_DEFAULT_FPS = 15
_CHUNK_OVERLAP = 8  # overlap frames between chunks for long video



# Resolution presets: (height, width)
RESOLUTION_PRESETS = {
    "auto": None,
    "480p": (480, 640),
    "512": (512, 512),
    "640": (640, 640),
    "720p": (720, 1280),
    "custom": None,
}

# Enhanced prompt templates for temporal consistency (from Kiwi-Edit repo)
TASK_PROMPT_ENHANCEMENTS = {
    "global_style": [
        "Ensure seamless temporal consistency across all frames of the video.",
        "Retain the original motion, character actions, and camera movements throughout the sequence.",
        "Maintain strict frame-by-frame consistency to ensure visual harmony.",
    ],
    "local_change": [
        "Ensure the object maintains the exact same position and pose within the video scene.",
        "The modified element must stay aligned with the subject's original physical orientation.",
        "Keep the same pose and position for the subject throughout the entire video.",
    ],
    "background_change": [
        "The subject in the foreground must remain perfectly still throughout the video.",
        "Ensure the foreground subject remains perfectly still while the background transforms.",
        "Include subtle movements of environmental elements, such as shifting sunlight and shadows.",
    ],
    "local_remove": [
        "The background must be reconstructed with temporal consistency to match the original context.",
        "All other video content must remain entirely unchanged after the object is removed.",
        "Ensure the background is inpainted smoothly across all frames to avoid visual artifacts.",
    ],
    "local_add": [
        "The added object must be perfectly tracked to the specified surface as the camera moves.",
        "Maintain consistent shadows and lighting for the added object across all frames.",
        "All other parts of the video must remain unchanged after the new object is overlaid.",
    ],
}


# Cached pipeline state
_pipeline = None
_pipeline_variant: str = ""
_pipeline_precision: str = ""


# ---------------------------------------------------------------------------
#  Model directory and downloading
# ---------------------------------------------------------------------------

def _get_model_dir(variant: str) -> Path:
    """Get or create the model directory for a Kiwi-Edit variant.

    Checks (in order):
    1. FFMPEGA_KIWI_EDIT_MODEL_DIR env var
    2. ComfyUI/models/<variant_name>/ (standard ComfyUI convention)
    3. Extension's own models/<variant_name>/ (fallback)
    """
    dir_name = _MODEL_DIR_NAMES.get(variant, _MODEL_DIR_NAMES["instruct"])

    env_dir = os.environ.get("FFMPEGA_KIWI_EDIT_MODEL_DIR")
    if env_dir:
        p = Path(env_dir) / dir_name
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


def _download_model(model_dir: Path, variant: str) -> None:
    """Download BF16 model weights from HuggingFace if not present.

    Tries the AEmotionStudio mirror first, then falls back to the
    official repo.
    """
    if (model_dir / "model_index.json").is_file():
        return

    try:
        from . import model_manager as _mm
    except ImportError:
        from core import model_manager as _mm  # type: ignore

    model_key = f"kiwi_edit_{variant}"
    _mm.require_downloads_allowed(model_key)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise ImportError(
            "huggingface_hub is required to download Kiwi-Edit. "
            "Install with: pip install huggingface_hub"
        )

    mirror_repo = _MIRROR_REPOS.get(variant)
    hf_repo = _HF_REPOS[variant]

    log.info("Kiwi-Edit %s BF16 weights not found. Downloading...", variant)

    # Try mirror first
    if mirror_repo:
        try:
            _mm.download_with_progress(
                model_key,
                lambda: snapshot_download(
                    repo_id=mirror_repo,
                    local_dir=str(model_dir),
                ),
                extra="~10 GB",
            )
            log.info("Kiwi-Edit %s downloaded from AEmotionStudio mirror", variant)
            return
        except Exception as e:
            log.warning("Mirror download failed: %s — trying official repo", e)

    # Fall back to official repo
    _mm.download_with_progress(
        model_key,
        lambda: snapshot_download(
            repo_id=hf_repo,
            local_dir=str(model_dir),
        ),
        extra="~10 GB",
    )
    log.info("Kiwi-Edit %s downloaded from official repo: %s", variant, hf_repo)





# ---------------------------------------------------------------------------
#  Auto-select model variant
# ---------------------------------------------------------------------------

def auto_select_variant(
    prompt: str | None,
    ref_images: list | None,
    manual_variant: str = "auto",
) -> str:
    """Auto-select the best model variant based on available inputs.

    Args:
        prompt: Text editing instruction (may be empty/None).
        ref_images: Reference images (may be empty/None).
        manual_variant: User override ("auto", "instruct", "reference",
                        "instruct_reference").

    Returns:
        One of "instruct", "reference", "instruct_reference".
    """
    if manual_variant != "auto":
        return manual_variant

    has_prompt = bool(prompt and prompt.strip())
    has_ref = bool(ref_images)

    if has_prompt and has_ref:
        return "instruct_reference"
    elif has_ref:
        return "reference"
    else:
        return "instruct"


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Free all GPU VRAM before loading Kiwi-Edit.

    Delegates to the shared ``_vram_utils.free_for_module`` which handles
    ComfyUI eviction, cross-synthesizer cleanup, and CUDA cache clearing.
    """
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="kiwi_edit_synthesizer")


def _flush_vram() -> None:
    """Aggressive inter-phase VRAM flush."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _setup_component_offloading(pipe) -> None:
    """Configure pipeline for manual GPU offloading.

    The Kiwi-Edit pipeline's custom code bypasses standard ``forward()`` hooks:
    - ``_model_forward()`` directly accesses ``self.transformer`` sub-modules
    - Custom VAE has non-standard ``encode()``/``decode()``

    This means diffusers' ``enable_model_cpu_offload()`` and
    ``enable_sequential_cpu_offload()`` are both useless here.
    Instead we keep all components on CPU and manually move them to GPU
    one-at-a-time in ``_run_pipeline()``.
    """
    import torch

    # Determine GPU device
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        gpu_device = mm.get_torch_device()
    except ImportError:
        gpu_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Store GPU device for _run_pipeline
    pipe._kiwi_gpu_device = gpu_device

    # Ensure all components start on CPU
    for name, comp in pipe.components.items():
        if isinstance(comp, torch.nn.Module):
            comp.to("cpu")

    log.info(
        "[KiwiEdit] Manual offloading configured (GPU: %s) — "
        "components stay on CPU, moved to GPU per-phase in _run_pipeline",
        gpu_device,
    )

# ---------------------------------------------------------------------------
#  Pipeline loading
# ---------------------------------------------------------------------------

def load_pipeline(
    model_variant: str = "instruct",
    precision: str = "auto",
):
    """Load and cache the Kiwi-Edit pipeline.

    Args:
        model_variant: Which variant to load ("instruct", "reference",
                        "instruct_reference").
        precision: Weight precision (``"auto"`` or ``"bf16"``).  Both use
                   native BF16 weights from HuggingFace.

    Returns:
        KiwiEditPipeline instance ready for inference.
    """
    global _pipeline, _pipeline_variant, _pipeline_precision

    # Re-use cached pipeline if variant + precision match
    if (
        _pipeline is not None
        and _pipeline_variant == model_variant
        and _pipeline_precision == precision
    ):
        return _pipeline

    # Variant/precision changed — discard old pipeline
    if _pipeline is not None:
        log.info(
            "Model variant changed (%s/%s → %s/%s), reloading pipeline",
            _pipeline_variant, _pipeline_precision, model_variant, precision,
        )
        cleanup()

    from diffusers import DiffusionPipeline  # type: ignore[import-untyped]

    model_dir = _get_model_dir(model_variant)
    _download_model(model_dir, model_variant)

    _free_vram()

    log.info(
        "Loading Kiwi-Edit pipeline: variant=%s from %s",
        model_variant, model_dir,
    )

    import torch

    dtype = torch.bfloat16
    if torch.cuda.is_available():
        cap = torch.cuda.get_device_capability()
        if cap[0] < 8:  # Pre-Ampere GPUs don't support bfloat16 well
            dtype = torch.float16
            log.info("Using float16 (GPU compute capability %d.%d)", *cap)

    # Add model dir to sys.path so diffusers can import custom modules
    # (mllm_encoder, wan_video_vae, conditional_embedder, etc.)
    import sys
    model_dir_str = str(model_dir)
    path_added = model_dir_str not in sys.path
    if path_added:
        sys.path.insert(0, model_dir_str)

    try:
        # Suppress noisy warnings from diffusers/transformers about custom
        # modules — these are expected with trust_remote_code pipelines.
        import warnings
        import logging as _logging
        import io, sys as _sys
        _prev_tf_level = _logging.getLogger("transformers.modeling_utils").level
        _logging.getLogger("transformers.modeling_utils").setLevel(_logging.ERROR)
        _real_stderr = _sys.stderr
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*Config not found.*")
            warnings.filterwarnings("ignore", message=".*Something went wrong.*")
            _sys.stderr = io.StringIO()
            try:
                pipe = DiffusionPipeline.from_pretrained(
                    model_dir_str,
                    torch_dtype=dtype,
                    trust_remote_code=True,
                    custom_pipeline=model_dir_str,
                )
            finally:
                _sys.stderr = _real_stderr
        _logging.getLogger("transformers.modeling_utils").setLevel(_prev_tf_level)
    finally:
        if path_added and model_dir_str in sys.path:
            sys.path.remove(model_dir_str)

    # Scheduler is set dynamically in edit_video() via _set_scheduler()
    # to allow changing scheduler between runs without reloading the model.

    # --- Offloading strategy -----------------------------------------------
    _setup_component_offloading(pipe)

    _pipeline = pipe
    _pipeline_variant = model_variant
    _pipeline_precision = precision
    log.info("Kiwi-Edit pipeline loaded successfully: %s (%s)", model_variant, dtype)
    return _pipeline


def _set_scheduler(pipe, scheduler: str = "unipc", flow_shift: float = _DEFAULT_FLOW_SHIFT) -> None:
    """Configure the pipeline scheduler.

    Args:
        pipe: The diffusion pipeline.
        scheduler: Scheduler name — 'unipc', 'euler', 'heun', 'dpm++'.
        flow_shift: Flow matching shift for compatible schedulers.
    """
    try:
        if scheduler == "euler":
            from diffusers import FlowMatchEulerDiscreteScheduler  # type: ignore[import-untyped]
            pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(
                pipe.scheduler.config,
            )
            # Flow shift applied via sigma_shift in __call__, not scheduler config
            log.info("Scheduler set to FlowMatchEuler")
        elif scheduler == "heun":
            from diffusers import FlowMatchHeunDiscreteScheduler  # type: ignore[import-untyped]
            pipe.scheduler = FlowMatchHeunDiscreteScheduler.from_config(
                pipe.scheduler.config,
            )
            log.info("Scheduler set to FlowMatchHeun (2x cost per step)")
        elif scheduler == "dpm++":
            from diffusers import DPMSolverMultistepScheduler  # type: ignore[import-untyped]
            pipe.scheduler = DPMSolverMultistepScheduler.from_config(
                pipe.scheduler.config,
                flow_shift=flow_shift,
            )
            log.info("Scheduler set to DPM++ Multistep (flow_shift=%.1f)", flow_shift)
        else:
            # Default: UniPC
            from diffusers import UniPCMultistepScheduler  # type: ignore[import-untyped]
            pipe.scheduler = UniPCMultistepScheduler.from_config(
                pipe.scheduler.config,
                flow_shift=flow_shift,
            )
            log.info("Scheduler set to UniPC (flow_shift=%.1f)", flow_shift)
    except Exception as e:
        log.warning("Could not set %s scheduler, using default: %s", scheduler, e)

def cleanup() -> None:
    """Free GPU memory and clear cached pipeline.

    Follows the standard synthesizer cleanup pattern (VDA, NormalCrafter):
    move to CPU → release pipeline → gc.collect → empty CUDA cache →
    soft_empty_cache → log.
    """
    global _pipeline, _pipeline_variant, _pipeline_precision

    if _pipeline is None:
        return

    pipe = _pipeline
    _pipeline = None
    _pipeline_variant = ""
    _pipeline_precision = ""

    try:
        import torch
        # Move all components to CPU before deletion
        for name, comp in pipe.components.items():
            if isinstance(comp, torch.nn.Module):
                try:
                    comp.cpu()
                except Exception:
                    pass
    except (ImportError, AttributeError):
        pass
    del pipe

    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass
    log.info("Kiwi-Edit pipeline unloaded")


def offload_to_cpu() -> None:
    """Offload cached pipeline components to CPU without destroying them.

    Follows the VDA/SeedVR pattern: keep the pipeline in RAM for fast re-use,
    but free VRAM. ``_vram_utils.free_for_module()`` will call ``cleanup()``
    if another synthesizer needs VRAM later.
    """
    if _pipeline is None:
        return
    try:
        import torch
        for name, comp in _pipeline.components.items():
            if isinstance(comp, torch.nn.Module):
                try:
                    comp.cpu()
                except Exception:
                    pass
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        log.info("Kiwi-Edit pipeline offloaded to CPU")
    except ImportError:
        pass


# ---------------------------------------------------------------------------
#  Frame I/O helpers
# ---------------------------------------------------------------------------

def _get_video_fps(video_path: str) -> float:
    """Get video FPS using ffprobe."""
    try:
        result = subprocess.run(
            [
                _get_ffprobe_bin(), "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "csv=p=0",
                video_path,
            ],
            capture_output=True, text=True, check=True,
        )
        rate = result.stdout.strip()
        if "/" in rate:
            num, den = rate.split("/")
            return float(num) / float(den)
        return float(rate)
    except Exception:
        return 24.0


def _get_video_frame_count(video_path: str) -> int:
    """Get number of frames in a video using ffprobe."""
    try:
        result = subprocess.run(
            [
                _get_ffprobe_bin(), "-v", "quiet",
                "-count_frames",
                "-select_streams", "v:0",
                "-show_entries", "stream=nb_read_frames",
                "-of", "csv=p=0",
                video_path,
            ],
            capture_output=True, text=True, check=True, timeout=60,
        )
        return int(result.stdout.strip())
    except Exception:
        return 0


def _load_video_frames(
    video_path: str,
    max_frames: int = _DEFAULT_MAX_FRAMES,
    max_pixels: int = 720 * 1280,
    target_height: int | None = None,
    target_width: int | None = None,
) -> tuple[list, float]:
    """Load video frames as a list of PIL Images, resized to fit constraints.

    Args:
        video_path: Path to the input video.
        max_frames: Maximum number of frames to load.
        max_pixels: Maximum total pixels per frame (height * width).
        target_height: Explicit target height (overrides max_pixels).
        target_width: Explicit target width (overrides max_pixels).

    Returns:
        (frames, fps) — list of PIL.Image.Image and the source FPS.
    """
    from PIL import Image

    fps = _get_video_fps(video_path)

    tmpdir = tempfile.mkdtemp(prefix="kiwi_frames_")
    try:
        subprocess.run(
            [
                _get_ffmpeg_bin(), "-i", video_path,
                "-q:v", "2",
                "-frames:v", str(max_frames),
                os.path.join(tmpdir, "%06d.png"),
            ],
            capture_output=True,
            check=True,
        )

        frame_files = sorted(Path(tmpdir).glob("*.png"))
        frames = []
        for f in frame_files[:max_frames]:
            img = Image.open(f).convert("RGB")
            w, h = img.size

            if target_height and target_width:
                new_w = target_width // 16 * 16
                new_h = target_height // 16 * 16
                if new_w != w or new_h != h:
                    img = img.resize((new_w, new_h), Image.LANCZOS)  # type: ignore[attr-defined]
            else:
                # Scale to fit max_pixels while preserving aspect ratio
                scale = min(1.0, (max_pixels / (w * h)) ** 0.5)
                if scale < 1.0:
                    new_w = int(w * scale) // 16 * 16
                    new_h = int(h * scale) // 16 * 16
                    img = img.resize((new_w, new_h), Image.LANCZOS)  # type: ignore[attr-defined]

            frames.append(img)

        if not frames:
            raise RuntimeError(f"No frames extracted from {video_path}")

        return frames, fps
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# VRAM-based resolution tiers (free VRAM in GiB → preset)
# Each tier is (min_free_vram_gib, preset_name, (height, width))
_VRAM_RESOLUTION_TIERS_BF16 = [
    (20.0, "720p", (720, 1280)),
    (14.0, "640",  (640, 640)),
    (10.0, "512",  (512, 512)),
    (0.0,  "480p", (480, 640)),
]

_VRAM_RESOLUTION_TIERS_FP8 = [
    (14.0, "720p", (720, 1280)),
    (10.0, "640",  (640, 640)),
    (6.0,  "512",  (512, 512)),
    (0.0,  "480p", (480, 640)),
]

# Approximate VRAM saved per transformer block offloaded to CPU (~200 MB each)
_BLOCK_SWAP_VRAM_SAVINGS_MB = 200


def _auto_detect_resolution(
    precision: str = "auto",
    block_swap_blocks: int = 0,
) -> tuple[str, tuple[int, int]]:
    """Select the best resolution preset based on available VRAM.

    Queries the current free GPU memory, applies adjustments for FP8
    precision and block swap offloading, then selects the highest
    resolution tier the GPU can handle.

    Args:
        precision: Weight precision ("auto", "fp8", "bf16").
        block_swap_blocks: Number of transformer blocks offloaded to CPU.

    Returns:
        (preset_name, (height, width)) tuple.
    """
    # Query free VRAM
    free_vram_bytes = 0
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        free_vram_bytes = mm.get_free_memory()
    except (ImportError, AttributeError):
        pass

    if free_vram_bytes == 0:
        try:
            import torch
            if torch.cuda.is_available():
                free_vram_bytes = torch.cuda.mem_get_info()[0]
        except (ImportError, RuntimeError):
            pass

    free_vram_gib = free_vram_bytes / (1024 ** 3)

    # Account for block swap: each offloaded block frees ~200 MB
    if block_swap_blocks > 0:
        bonus_gib = (block_swap_blocks * _BLOCK_SWAP_VRAM_SAVINGS_MB) / 1024
        effective_free = free_vram_gib + bonus_gib
        log.info(
            "[KiwiEdit] Auto resolution: %.1f GiB free + %.1f GiB block_swap (%d blocks) = %.1f GiB effective",
            free_vram_gib, bonus_gib, block_swap_blocks, effective_free,
        )
    else:
        effective_free = free_vram_gib

    # Select tier table based on precision
    is_fp8 = precision == "fp8" or (
        precision == "auto" and _get_fp8_model_dir("instruct") is not None
    )
    tiers = _VRAM_RESOLUTION_TIERS_FP8 if is_fp8 else _VRAM_RESOLUTION_TIERS_BF16
    precision_label = "fp8" if is_fp8 else "bf16"

    # Find the highest tier the GPU can handle
    for min_vram, preset_name, resolution in tiers:
        if effective_free >= min_vram:
            log.info(
                "[FFMPEGA] Kiwi-Edit auto-selected: %dx%d (%s) — "
                "%.1f GiB free VRAM, %s precision",
                resolution[1], resolution[0], preset_name,
                free_vram_gib, precision_label,
            )
            return preset_name, resolution

    # Fallback (should not reach here due to 0.0 threshold)
    fallback = tiers[-1]
    log.warning(
        "[FFMPEGA] Kiwi-Edit auto-resolution fallback: %s (%.1f GiB free)",
        fallback[1], free_vram_gib,
    )
    return fallback[1], fallback[2]


def _resolve_resolution(
    source_frames: list,
    resolution_preset: str = "auto",
    custom_width: int = 0,
    custom_height: int = 0,
    precision: str = "auto",
    block_swap_blocks: int = 0,
) -> tuple[int, int]:
    """Resolve target resolution from preset or custom values.

    When preset is ``"auto"``, queries free VRAM and selects the highest
    resolution the GPU can handle, accounting for precision and block swap.

    Returns (height, width) — aligned to multiples of 16.
    """
    if resolution_preset == "custom" and custom_width > 0 and custom_height > 0:
        return (custom_height // 16 * 16, custom_width // 16 * 16)

    preset = RESOLUTION_PRESETS.get(resolution_preset)
    if preset:
        return preset

    # "auto" — VRAM-aware resolution detection
    _preset_name, resolution = _auto_detect_resolution(
        precision=precision,
        block_swap_blocks=block_swap_blocks,
    )
    return resolution


# ---------------------------------------------------------------------------
#  Enhanced prompt builder
# ---------------------------------------------------------------------------

def _enhance_prompt(prompt: str, task_type: str = "auto") -> str:
    """Auto-detect the edit task type and prepend temporal stability hints.

    Uses simple keyword matching to classify the edit and add relevant
    temporal consistency instructions from the Kiwi-Edit task templates.

    Args:
        prompt: The raw edit instruction.
        task_type: Override task type. "auto" = detect from keywords.
    """
    if task_type != "auto" and task_type in TASK_PROMPT_ENHANCEMENTS:
        task = task_type
    else:
        lower = prompt.lower()
        # Detect task type from keywords
        if any(kw in lower for kw in ("remove", "delete", "erase")):
            task = "local_remove"
        elif any(kw in lower for kw in ("add", "place", "insert", "put")):
            task = "local_add"
        elif any(kw in lower for kw in ("background", "scene", "environment", "landscape")):
            task = "background_change"
        elif any(kw in lower for kw in ("style", "aesthetic", "artistic", "painting", "cartoon")):
            task = "global_style"
        else:
            task = "local_change"

    log.debug("Prompt task type: %s (override=%s)", task, task_type)
    hints = TASK_PROMPT_ENHANCEMENTS.get(task, [])
    if hints:
        # Append two relevant hints
        suffix = " ".join(hints[:2])
        return f"{prompt} {suffix}"

    return prompt


# ---------------------------------------------------------------------------
#  Core pipeline execution
# ---------------------------------------------------------------------------

def _run_pipeline(
    pipe,
    source_frames: list,
    prompt: str | None = None,
    ref_images: list | None = None,
    height: int = 640,
    width: int = 640,
    num_frames: int = _DEFAULT_MAX_FRAMES,
    steps: int = _DEFAULT_STEPS,
    guidance_scale: float = _DEFAULT_GUIDANCE,
    seed: int = 0,
    flow_shift: float = _DEFAULT_FLOW_SHIFT,
) -> list:
    """Run the Kiwi-Edit pipeline using pipe().__call__ with diffusers offloading.

    Diffusers' ``enable_model_cpu_offload()`` handles most components, but the
    custom VAE (wan_video_vae) has non-standard ``encode()``/``decode()`` methods
    that bypass accelerate's ``forward()`` hooks.  We patch these methods to
    auto-move the VAE to GPU only during their operation, then back to CPU.
    """
    import torch
    from PIL import Image as PILImage
    from tqdm import tqdm

    actual_frames = min(num_frames, len(source_frames))

    log.info(
        "[KiwiEdit] Running pipeline: %d frames, %dx%d, %d steps, cfg=%.1f",
        actual_frames, width, height, steps, guidance_scale,
    )

    gpu_device = getattr(pipe, '_kiwi_gpu_device', torch.device("cuda"))
    cpu_device = torch.device("cpu")

    # Free VRAM from other ComfyUI models before we start
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.free_memory(mm.get_free_memory(gpu_device), gpu_device)
        mm.soft_empty_cache()
    except ImportError:
        pass

    # -----------------------------------------------------------------------
    # Manual per-component GPU staging
    # -----------------------------------------------------------------------
    # The Kiwi-Edit pipeline bypasses standard forward() hooks:
    #   - _model_forward() accesses transformer sub-modules directly
    #   - Custom VAE has non-standard encode()/decode()
    #   - mllm_encoder lazy-loads Qwen in forward()
    # We patch each component's entry method to:
    #   1. Evict all OTHER components to CPU
    #   2. Move THIS component to GPU
    #   3. Run the original method
    #   4. Move THIS component back to CPU
    # -----------------------------------------------------------------------

    _all_nn_comps = {
        name: c for name, c in pipe.components.items()
        if isinstance(c, torch.nn.Module)
    }

    # Override _execution_device so the pipeline creates all tensors on GPU.
    # Without enable_model_cpu_offload(), this property returns CPU (since all
    # components start on CPU). But we need tensors on GPU for the component
    # wrappers to work correctly.
    _pipe_cls = type(pipe)
    _orig_exec_device_prop = _pipe_cls.__dict__.get('_execution_device', None)
    _pipe_cls._execution_device = property(lambda self: gpu_device)

    def _evict_all_except(*keep_names: str):
        """Move all components EXCEPT the named ones to CPU."""
        keep = set(keep_names)
        for name, c in _all_nn_comps.items():
            if name not in keep:
                c.to(cpu_device)
        torch.cuda.empty_cache()

    # Remove any leftover accelerate hooks (from previous runs)
    try:
        from accelerate.hooks import remove_hook_from_module
        for name, c in _all_nn_comps.items():
            if hasattr(c, '_hf_hook'):
                remove_hook_from_module(c, recurse=True)
    except ImportError:
        pass

    # --- Patch mllm_encoder.forward ---
    _orig_mllm_forward = pipe.mllm_encoder.forward

    def _gpu_mllm_forward(*args, **kwargs):
        _evict_all_except("mllm_encoder")
        pipe.mllm_encoder.to(gpu_device)
        try:
            return _orig_mllm_forward(*args, **kwargs)
        finally:
            pipe.mllm_encoder.to(cpu_device)
            torch.cuda.empty_cache()

    pipe.mllm_encoder.forward = _gpu_mllm_forward

    # --- Patch source_embedder.forward ---
    _orig_se_forward = pipe.source_embedder.forward

    def _gpu_se_forward(*args, **kwargs):
        # Keep transformer alive — source_embedder is called from _model_forward
        _evict_all_except("source_embedder", "transformer")
        pipe.source_embedder.to(gpu_device)
        args = tuple(a.to(gpu_device) if isinstance(a, torch.Tensor) else a for a in args)
        kwargs = {k: v.to(gpu_device) if isinstance(v, torch.Tensor) else v for k, v in kwargs.items()}
        try:
            return _orig_se_forward(*args, **kwargs)
        finally:
            pipe.source_embedder.to(cpu_device)
            torch.cuda.empty_cache()

    pipe.source_embedder.forward = _gpu_se_forward

    # --- Patch ref_embedder.forward ---
    _orig_re_forward = pipe.ref_embedder.forward

    def _gpu_re_forward(*args, **kwargs):
        # Keep transformer alive — ref_embedder is called from _model_forward
        _evict_all_except("ref_embedder", "transformer")
        pipe.ref_embedder.to(gpu_device)
        args = tuple(a.to(gpu_device) if isinstance(a, torch.Tensor) else a for a in args)
        kwargs = {k: v.to(gpu_device) if isinstance(v, torch.Tensor) else v for k, v in kwargs.items()}
        try:
            return _orig_re_forward(*args, **kwargs)
        finally:
            pipe.ref_embedder.to(cpu_device)
            torch.cuda.empty_cache()

    pipe.ref_embedder.forward = _gpu_re_forward

    # --- Patch VAE encode/decode ---
    _orig_encode = pipe.vae.encode
    _orig_decode = pipe.vae.decode

    # ComfyUI's NVIDIA Conv3d memory bug workaround (cuDNN 91002 + torch 2.10).
    # The VAE uses native nn.Conv3d (CausalConv3d) which doesn't get ComfyUI's
    # comfy.ops.Conv3d fix. We apply the same torch.cudnn_convolution workaround
    # by temporarily monkey-patching nn.Conv3d._conv_forward during VAE ops.
    try:
        from comfy.ops import NVIDIA_MEMORY_CONV_BUG_WORKAROUND
    except ImportError:
        NVIDIA_MEMORY_CONV_BUG_WORKAROUND = False

    _orig_conv3d_conv_forward = torch.nn.Conv3d._conv_forward

    def _patched_conv3d_conv_forward(self, input, weight, bias):
        """Apply ComfyUI's cudnn_convolution workaround for NVIDIA bug."""
        if NVIDIA_MEMORY_CONV_BUG_WORKAROUND and weight.dtype in (torch.float16, torch.bfloat16):
            out = torch.cudnn_convolution(
                input, weight, self.padding, self.stride,
                self.dilation, self.groups,
                benchmark=False, deterministic=False, allow_tf32=True,
            )
            if bias is not None:
                out += bias.reshape((1, -1) + (1,) * (out.ndim - 2))
            return out
        return _orig_conv3d_conv_forward(self, input, weight, bias)

    def _gpu_encode(*args, **kwargs):
        _evict_all_except("vae")
        pipe.vae.to(gpu_device)
        torch.nn.Conv3d._conv_forward = _patched_conv3d_conv_forward
        # Move input tensors to GPU (pipeline creates them on CPU since
        # _execution_device returns CPU without enable_model_cpu_offload)
        args = tuple(a.to(gpu_device) if isinstance(a, torch.Tensor) else a for a in args)
        kwargs = {k: v.to(gpu_device) if isinstance(v, torch.Tensor) else v for k, v in kwargs.items()}
        try:
            return _orig_encode(*args, **kwargs)
        finally:
            torch.nn.Conv3d._conv_forward = _orig_conv3d_conv_forward
            pipe.vae.to(cpu_device)
            torch.cuda.empty_cache()

    def _gpu_decode(*args, **kwargs):
        _evict_all_except("vae")
        pipe.vae.to(gpu_device)
        torch.nn.Conv3d._conv_forward = _patched_conv3d_conv_forward
        args = tuple(a.to(gpu_device) if isinstance(a, torch.Tensor) else a for a in args)
        kwargs = {k: v.to(gpu_device) if isinstance(v, torch.Tensor) else v for k, v in kwargs.items()}
        try:
            return _orig_decode(*args, **kwargs)
        finally:
            torch.nn.Conv3d._conv_forward = _orig_conv3d_conv_forward
            pipe.vae.to(cpu_device)
            torch.cuda.empty_cache()

    pipe.vae.encode = _gpu_encode
    pipe.vae.decode = _gpu_decode

    # --- Patch _model_forward to stage transformer (block-by-block) ---
    # The full transformer (~14B params) doesn't fit in VRAM (~12GB RTX 4070).
    # Strategy: keep small components on GPU permanently during denoising,
    # swap each transformer block to GPU via forward hooks.
    _orig_model_forward = pipe._model_forward
    _block_hooks = []  # track hooks for cleanup

    def _setup_transformer_hooks():
        """Install forward hooks on each transformer block for GPU staging."""
        t = pipe.transformer

        # Move small components to GPU (these are tiny, < 100MB total)
        for name in ['patch_embedding', 'condition_embedder', 'norm_out',
                      'proj_out']:
            sub = getattr(t, name, None)
            if sub is not None:
                sub.to(device=gpu_device, dtype=torch.bfloat16)

        # scale_shift_table and rope are parameters — use .data for in-place move
        if hasattr(t, 'scale_shift_table') and t.scale_shift_table is not None:
            t.scale_shift_table.data = t.scale_shift_table.data.to(
                device=gpu_device, dtype=torch.bfloat16)
        if hasattr(t, 'rope') and t.rope is not None:
            if isinstance(t.rope, torch.nn.Module):
                t.rope.to(device=gpu_device, dtype=torch.bfloat16)
            elif isinstance(t.rope, (torch.Tensor, torch.nn.Parameter)):
                t.rope.data = t.rope.data.to(device=gpu_device)

        # Install pre/post hooks on each transformer block
        for block in t.blocks:
            def _pre_hook(module, args):
                module.to(device=gpu_device, dtype=torch.bfloat16)
            def _post_hook(module, args, output):
                module.to(cpu_device)
                torch.cuda.empty_cache()
            h1 = block.register_forward_pre_hook(_pre_hook)
            h2 = block.register_forward_hook(_post_hook)
            _block_hooks.extend([h1, h2])

    def _gpu_model_forward(*args, **kwargs):
        # Keep source_embedder + ref_embedder — both are called inside _model_forward
        _evict_all_except("transformer", "source_embedder", "ref_embedder")
        if not _block_hooks:
            _setup_transformer_hooks()
        # Activate conv3d workaround for patch_embedding (also a Conv3d)
        torch.nn.Conv3d._conv_forward = _patched_conv3d_conv_forward
        try:
            return _orig_model_forward(*args, **kwargs)
        finally:
            torch.nn.Conv3d._conv_forward = _orig_conv3d_conv_forward

    pipe._model_forward = _gpu_model_forward

    log.info("[KiwiEdit] All components patched for manual GPU staging")

    # Prepare source frames
    src_frames = source_frames[:actual_frames]
    src_resized = [f.resize((width, height), PILImage.LANCZOS) for f in src_frames]

    # Prepare ref images if provided
    ref_for_pipe = ref_images if ref_images else None

    try:
        output_frames = pipe(
            prompt=prompt or "",
            source_video=src_resized,
            ref_image=ref_for_pipe,
            height=height,
            width=width,
            num_frames=actual_frames,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            sigma_shift=flow_shift,
            seed=seed if seed != 0 else None,
            tiled=True,
            progress_bar=tqdm,
        )
    finally:
        # Remove transformer block hooks
        for h in _block_hooks:
            h.remove()
        _block_hooks.clear()

        # Restore original methods
        pipe.vae.encode = _orig_encode
        pipe.vae.decode = _orig_decode
        pipe.mllm_encoder.forward = _orig_mllm_forward
        pipe.source_embedder.forward = _orig_se_forward
        pipe.ref_embedder.forward = _orig_re_forward
        pipe._model_forward = _orig_model_forward
        torch.nn.Conv3d._conv_forward = _orig_conv3d_conv_forward
        # Restore _execution_device property
        if _orig_exec_device_prop is not None:
            _pipe_cls._execution_device = _orig_exec_device_prop
        elif hasattr(_pipe_cls, '_execution_device'):
            del _pipe_cls._execution_device

        # Offload all components to CPU (keeps pipeline cached for re-use)
        offload_to_cpu()

    # Handle nested list (some pipelines return [[frame1, frame2, ...]])
    if (
        isinstance(output_frames, list)
        and len(output_frames) == 1
        and isinstance(output_frames[0], list)
    ):
        output_frames = output_frames[0]

    log.info("[KiwiEdit] Pipeline produced %d output frames", len(output_frames))
    return output_frames


# ---------------------------------------------------------------------------
#  Chunked long-video processing
# ---------------------------------------------------------------------------

def _process_long_video(
    pipe,
    source_frames: list,
    prompt: str | None = None,
    ref_images: list | None = None,
    height: int = 640,
    width: int = 640,
    max_frames: int = _DEFAULT_MAX_FRAMES,
    steps: int = _DEFAULT_STEPS,
    guidance_scale: float = _DEFAULT_GUIDANCE,
    seed: int = 0,
    flow_shift: float = _DEFAULT_FLOW_SHIFT,
) -> list:
    """Process a long video by splitting into overlapping chunks.

    Each chunk is processed independently. The last frame of chunk N
    is used as temporal context for chunk N+1's output. Overlap regions
    are blended using a linear crossfade.

    Args:
        source_frames: Full list of source PIL frames.
        max_frames: Maximum frames per chunk.
        Other args match _run_pipeline.

    Returns:
        List of all edited PIL frames, stitched together.
    """
    total = len(source_frames)
    if total <= max_frames:
        return _run_pipeline(
            pipe, source_frames, prompt, ref_images,
            height, width, total, steps, guidance_scale, seed,
            flow_shift=flow_shift,
        )

    log.info(
        "[KiwiEdit] Long video mode: %d frames, chunk size=%d, overlap=%d",
        total, max_frames, _CHUNK_OVERLAP,
    )

    stride = max_frames - _CHUNK_OVERLAP
    all_chunks: list[tuple[int, int, list]] = []  # (start, end, frames)

    chunk_idx = 0
    start = 0
    while start < total:
        end = min(start + max_frames, total)
        chunk_frames = source_frames[start:end]

        log.info(
            "[KiwiEdit] Processing chunk %d: frames %d–%d (%d frames)",
            chunk_idx, start, end - 1, len(chunk_frames),
        )

        chunk_output = _run_pipeline(
            pipe, chunk_frames, prompt, ref_images,
            height, width, len(chunk_frames), steps, guidance_scale, seed,
            flow_shift=flow_shift,
        )

        all_chunks.append((start, end, chunk_output))

        _flush_vram()

        start += stride
        chunk_idx += 1

    # Stitch chunks with crossfade blending in overlap regions
    return _stitch_chunks(all_chunks, total)


def _stitch_chunks(
    chunks: list[tuple[int, int, list]],
    total_frames: int,
) -> list:
    """Stitch overlapping chunks using linear crossfade blending.

    Args:
        chunks: List of (start_idx, end_idx, output_frames) tuples.
        total_frames: Total number of expected output frames.

    Returns:
        Final list of blended PIL frames.
    """
    import numpy as np
    from PIL import Image

    if len(chunks) == 1:
        return chunks[0][2]

    result: list = [None] * total_frames

    for chunk_i, (start, end, frames) in enumerate(chunks):
        for local_i, global_i in enumerate(range(start, end)):
            if global_i >= total_frames:
                break

            if result[global_i] is None:
                # No overlap — take frame directly
                result[global_i] = frames[local_i]
            else:
                # Overlap region — blend with existing frame
                prev_arr = np.array(result[global_i]).astype(np.float32)
                curr_arr = np.array(frames[local_i]).astype(np.float32)

                # Linear blend: weight increases from 0→1 across overlap
                # Find overlap position within this chunk
                overlap_start = start
                overlap_end = start + _CHUNK_OVERLAP
                overlap_pos = global_i - overlap_start
                alpha = overlap_pos / max(_CHUNK_OVERLAP - 1, 1)

                blended = prev_arr * (1 - alpha) + curr_arr * alpha
                result[global_i] = Image.fromarray(
                    blended.clip(0, 255).astype(np.uint8)
                )

    # Fill any remaining None slots (shouldn't happen in normal operation)
    for i, frame in enumerate(result):
        if frame is None and i > 0:
            result[i] = result[i - 1]

    return [f for f in result if f is not None]


# ---------------------------------------------------------------------------
#  Video encoding
# ---------------------------------------------------------------------------

def _encode_output_video(
    frames: list,
    output_path: str,
    fps: float,
) -> str:
    """Encode PIL frames to a video file using ffmpeg.

    Args:
        frames: List of PIL.Image frames.
        output_path: Output video path.
        fps: Target frame rate.

    Returns:
        Path to the encoded video.
    """
    tmpdir = tempfile.mkdtemp(prefix="kiwi_out_")
    try:
        for i, frame in enumerate(frames):
            frame.save(os.path.join(tmpdir, f"{i:06d}.png"))

        subprocess.run(
            [
                _get_ffmpeg_bin(), "-y",
                "-framerate", str(fps),
                "-start_number", "0",
                "-i", os.path.join(tmpdir, "%06d.png"),
                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                output_path,
            ],
            capture_output=True,
            check=True,
        )

        return output_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _mux_audio(
    video_path: str,
    original_path: str,
    output_path: str,
) -> bool:
    """Mux audio from the original video into the output.

    Returns True if audio was successfully muxed.
    """
    ffprobe = _get_ffprobe_bin()
    ffmpeg = _get_ffmpeg_bin()

    # Check if original has audio
    try:
        probe = subprocess.run(
            [ffprobe, "-v", "quiet", "-select_streams", "a:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0",
             original_path],
            capture_output=True, text=True, timeout=10,
        )
        has_audio = probe.returncode == 0 and "audio" in probe.stdout
    except Exception:
        has_audio = False

    if not has_audio:
        return False

    muxed_path = output_path + ".muxed.mp4"
    result = subprocess.run(
        [ffmpeg, "-y",
         "-i", video_path, "-i", original_path,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-map", "0:v:0", "-map", "1:a:0",
         "-shortest",
         muxed_path],
        capture_output=True, text=True,
    )

    if result.returncode == 0 and os.path.isfile(muxed_path):
        os.replace(muxed_path, output_path)
        log.info("[KiwiEdit] Audio muxed from original")
        return True
    else:
        try:
            os.remove(muxed_path)
        except OSError:
            pass
        log.warning("[KiwiEdit] Audio mux failed — output is video-only")
        return False


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def edit_video(
    video_path: str,
    prompt: str | None = None,
    ref_image_paths: list[str] | None = None,
    ref_images_pil: list | None = None,
    output_path: Optional[str] = None,
    model_variant: str = "auto",
    resolution_preset: str = "auto",
    custom_width: int = 0,
    custom_height: int = 0,
    max_frames: int = _DEFAULT_MAX_FRAMES,
    steps: int = _DEFAULT_STEPS,
    guidance_scale: float = _DEFAULT_GUIDANCE,
    seed: int = 0,
    precision: str = "auto",
    long_video: bool = False,
    block_swap_blocks: int = 0,
    flow_shift: float = _DEFAULT_FLOW_SHIFT,
    task_type: str = "auto",
    scheduler: str = "unipc",

) -> str:
    """Edit a video using Kiwi-Edit.

    This is the main public entry point. Auto-selects the model variant
    based on available inputs (prompt, reference images).

    Args:
        video_path: Path to the source video.
        prompt: Text editing instruction (required for instruct/instruct_reference).
        ref_image_paths: List of reference image file paths.
        ref_images_pil: List of PIL.Image reference images (alternative to paths).
        output_path: Output video path (auto-generated if None).
        model_variant: "auto", "instruct", "reference", "instruct_reference".
        resolution_preset: "auto", "480p", "512", "640", "720p", "custom".
        custom_width: Custom width (only used with preset="custom").
        custom_height: Custom height (only used with preset="custom").
        max_frames: Maximum frames per processing chunk (default 81).
        steps: Number of inference steps (default 30).
        guidance_scale: Classifier-free guidance scale (default 5.0).
        seed: Random seed for reproducibility.
        precision: "auto", "fp8", "bf16".
        long_video: Enable chunked processing for videos > max_frames.
        block_swap_blocks: Number of transformer blocks to offload to CPU.

    Returns:
        Path to the edited video.

    Raises:
        ImportError: If diffusers is not installed.
        RuntimeError: If model download or inference fails.
    """
    video_path = validate_video_path(video_path)
    if output_path is not None:
        output_path = validate_output_file_path(output_path)

    if output_path is None:
        _fd, output_path = tempfile.mkstemp(suffix="_kiwi_edit.mp4", prefix="ffmpega_")
        os.close(_fd)

    # Build reference image list
    ref_images: list | None = None
    if ref_images_pil:
        ref_images = list(ref_images_pil)
    if ref_image_paths:
        from PIL import Image
        if ref_images is None:
            ref_images = []
        for p in ref_image_paths:
            if os.path.isfile(p):
                ref_images.append(Image.open(p).convert("RGB"))
                log.info("[KiwiEdit] Loaded reference image: %s", p)

    # Auto-select variant
    variant = auto_select_variant(prompt, ref_images, model_variant)
    log.info(
        "[KiwiEdit] Selected variant=%s (prompt=%s, ref=%s, manual=%s)",
        variant,
        bool(prompt and prompt.strip()),
        bool(ref_images),
        model_variant,
    )

    # Validate inputs for the selected variant
    if variant == "instruct" and not (prompt and prompt.strip()):
        raise RuntimeError(
            "Kiwi-Edit instruct mode requires a text prompt. "
            "Enter your editing instruction in the prompt field."
        )
    if variant == "reference" and not ref_images:
        raise RuntimeError(
            "Kiwi-Edit reference mode requires at least one reference image. "
            "Connect an image to the image_a input."
        )
    if variant == "instruct_reference" and not (prompt and prompt.strip()):
        raise RuntimeError(
            "Kiwi-Edit instruct+reference mode requires both a text prompt "
            "and a reference image."
        )

    # Enhance prompt with temporal stability hints
    enhanced_prompt = _enhance_prompt(prompt, task_type=task_type) if prompt and prompt.strip() else None

    try:
        # Load pipeline
        pipe = load_pipeline(model_variant=variant, precision=precision)

        # Set scheduler (can change between runs without reloading)
        _set_scheduler(pipe, scheduler, flow_shift)



        # Load video frames
        frames, fps = _load_video_frames(video_path, max_frames=max_frames * 2 if long_video else max_frames)

        # Resolve resolution
        h, w = _resolve_resolution(
            frames, resolution_preset, custom_width, custom_height,
            precision=precision, block_swap_blocks=block_swap_blocks,
        )

        # Resize frames to target resolution if needed
        if frames and (frames[0].size != (w, h)):
            from PIL import Image
            frames = [f.resize((w, h), Image.LANCZOS) for f in frames]  # type: ignore[attr-defined]

        log.info(
            "[KiwiEdit] Processing: %d frames at %dx%d, fps=%.1f",
            len(frames), w, h, fps,
        )

        # Run pipeline
        import torch
        with torch.no_grad():
            if long_video and len(frames) > max_frames:
                output_frames = _process_long_video(
                    pipe, frames, enhanced_prompt, ref_images,
                    h, w, max_frames, steps, guidance_scale, seed,
                    flow_shift=flow_shift,
                )
            else:
                output_frames = _run_pipeline(
                    pipe, frames, enhanced_prompt, ref_images,
                    h, w, min(max_frames, len(frames)), steps, guidance_scale, seed,
                    flow_shift=flow_shift,
                )

        _flush_vram()

        # Encode output
        _encode_output_video(output_frames, output_path, fps)

        # Mux audio from original
        _mux_audio(output_path, video_path, output_path)

        log.info("[KiwiEdit] Edit complete: %s (%d frames)", output_path, len(output_frames))
        return output_path

    finally:
        # Always free pipeline after use — Kiwi-Edit is very VRAM heavy
        cleanup()
