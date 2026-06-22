"""SAM3 (Segment Anything 3) integration for auto-masking in FFMPEGA.

Provides image and video segmentation using Meta's SAM3 model with
**text prompt** support (e.g. "the person", "license plate").

Model checkpoints are loaded from ComfyUI/models/SAM3/ if available,
otherwise auto-downloaded from AEmotionStudio/sam3 on HuggingFace.

License: SAM License (Meta) — redistribution permitted with license.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger("ffmpega.sam3")

# ---------------------------------------------------------------------------
#  Auto-patcher for sam3 package import bugs
# ---------------------------------------------------------------------------
#
#  The sam3 pip package has a bug: 3 model files import from training code
#  (sam3.train.*) which pulls in `decord` at module level. `decord` is not
#  in sam3's dependencies and isn't needed for inference. This patcher fixes
#  those imports in-place so that `import sam3` works without `decord`.
#
#  Patches (applied once, survives until sam3 is reinstalled):
#    sam3/model/sam3_image.py:
#      -from sam3.train.data.collator import BatchedDatapoint
#      +from sam3.model.data_misc import BatchedDatapoint
#    sam3/model/sam3_tracker_base.py:
#      -from sam3.train.data.collator import BatchedDatapoint
#      +from sam3.model.data_misc import BatchedDatapoint
#    sam3/model/sam3_video_base.py:
#      -from sam3.train.masks_ops import rle_encode
#      +from sam3.train.masks_ops import rle_encode  (lazy import)

_PATCHES = [
    # Legacy SAM 3 patches (older sam3 revisions). The 3.1-era revision no
    # longer has these top-level BatchedDatapoint imports; the patcher
    # silently skips when the old string isn't present.
    {
        "file": "model/sam3_image.py",
        "old": "from sam3.train.data.collator import BatchedDatapoint",
        "new": "from sam3.model.data_misc import BatchedDatapoint",
    },
    {
        "file": "model/sam3_tracker_base.py",
        "old": "from sam3.train.data.collator import BatchedDatapoint",
        "new": "from sam3.model.data_misc import BatchedDatapoint",
    },
    # SAM 3 / 3.1 — masks_ops module-level imports pull in pycocotools (not
    # in sam3's runtime deps). Wrap each in try/except so missing
    # pycocotools doesn't break model imports during inference.
    {
        "file": "model/sam3_video_base.py",
        "old": "from sam3.train.masks_ops import mask_iom, rle_encode",
        "new": (
            "try:\n"
            "    from sam3.train.masks_ops import mask_iom, rle_encode\n"
            "except ImportError:\n"
            "    mask_iom = None\n"
            "    rle_encode = None"
        ),
        "guard_absent": "except ImportError:",
    },
    {
        "file": "model/sam3_video_base.py",
        "old": "from sam3.train.masks_ops import rle_encode",
        "new": (
            "try:\n"
            "    from sam3.train.masks_ops import rle_encode\n"
            "except ImportError:\n"
            "    rle_encode = None"
        ),
        "guard_absent": "except ImportError:",
    },
    {
        "file": "model/sam3_multiplex_base.py",
        "old": "from sam3.train.masks_ops import rle_encode",
        "new": (
            "try:\n"
            "    from sam3.train.masks_ops import rle_encode\n"
            "except ImportError:\n"
            "    rle_encode = None"
        ),
        "guard_absent": "except ImportError:",
    },
    {
        "file": "model/sam3_multiplex_detector_utils.py",
        "old": "from sam3.train.masks_ops import mask_iom",
        "new": (
            "try:\n"
            "    from sam3.train.masks_ops import mask_iom\n"
            "except ImportError:\n"
            "    mask_iom = None"
        ),
        "guard_absent": "except ImportError:",
    },
    {
        "file": "agent/client_sam3.py",
        "old": "from sam3.train.masks_ops import rle_encode",
        "new": (
            "try:\n"
            "    from sam3.train.masks_ops import rle_encode\n"
            "except ImportError:\n"
            "    rle_encode = None"
        ),
        "guard_absent": "except ImportError:",
    },
]

_patched = False


def _find_sam3_package_dir() -> "Path | None":
    """Locate the sam3 package directory without importing it.

    importlib.util.find_spec hangs on Python 3.14 for packages with
    broken top-level imports, so we search site-packages directly.
    """
    import site
    import sys

    # Collect all site-packages directories
    user_sp = site.getusersitepackages()
    dirs = list(site.getsitepackages())
    if user_sp is not None:
        dirs.append(user_sp)
    # Also check sys.path for virtualenv site-packages
    dirs.extend(p for p in sys.path if "site-packages" in p)

    for d in dirs:
        candidate = Path(d) / "sam3" / "__init__.py"
        if candidate.is_file():
            return candidate.parent

    return None


def _patch_sam3_imports() -> None:
    """Patch sam3's broken training imports so inference works without decord.

    Must be called BEFORE any `import sam3` statement, because the broken
    imports execute at module-load time.

    The sam3 pip package has a bug: model files import from training code
    (sam3.train.*) at module level, pulling in `decord` and `pycocotools`
    which aren't needed for inference and aren't in sam3's dependencies.
    This patcher fixes those imports in-place.
    """
    global _patched
    if _patched:
        return
    _patched = True

    pkg_dir = _find_sam3_package_dir()
    if pkg_dir is None:
        return  # sam3 not installed

    applied = 0
    for patch in _PATCHES:
        fpath = pkg_dir / patch["file"]
        if not fpath.is_file():
            continue
        content = fpath.read_text()
        if patch["old"] not in content:
            continue  # Already patched or line changed

        # Skip if the SPECIFIC patched form is already present. Use a
        # signature line — "    " + patch["old"] — that's only there once
        # the import has been moved into a try block. Checking the entire
        # new string would miss whitespace drift, but the indented import
        # is a reliable fingerprint.
        signature = "    " + patch["old"]
        if signature in content:
            continue

        content = content.replace(patch["old"], patch["new"], 1)
        try:
            fpath.write_text(content)
            applied += 1
            log.debug("Patched %s", fpath)
        except PermissionError:
            log.warning(
                "Cannot patch %s (permission denied). "
                "Run once with write access to site-packages.", fpath
            )

    if applied:
        log.info("Patched %d sam3 import(s) to bypass decord/pycocotools", applied)


# ---------------------------------------------------------------------------
#  Cached model instances (lazy-loaded) — keyed by (device, version)
# ---------------------------------------------------------------------------

# Maps version -> (model, processor); device tracked separately.
_image_models: dict[str, object] = {}
_image_processors: dict[str, object] = {}
_image_model_devices: dict[str, str] = {}
_video_models: dict[str, object] = {}
_video_model_devices: dict[str, str] = {}

import threading
_image_model_lock = threading.Lock()

# Hard cap on the SAM3 video-tracking subprocess. A healthy run streams
# per-frame progress within seconds of start; if it produces nothing it has
# hung during load/init rather than processing slowly, so keep this tight
# enough to surface failures fast instead of blocking the workflow for ages.
_SAM3_SUBPROCESS_TIMEOUT = 450  # 7.5 min
_video_model_lock = threading.Lock()


# ---------------------------------------------------------------------------
#  Model directory & checkpoint discovery
# ---------------------------------------------------------------------------

DEFAULT_SAM_VERSION = "sam3.1"

# Per-version spec for checkpoint discovery, mirrors, and model directories.
# Keys:
#   model_key       — registry key in core.model_manager._MODEL_INFO
#   hf_repo_upstream — Meta's upstream HF repo id (final fallback)
#   safetensors     — preferred local filename
#   pt              — fallback local filename
#   dir_name        — subdirectory under ComfyUI/models/
#   env_var         — optional override for the model directory
_MODEL_SPEC: dict[str, dict] = {
    "sam3": {
        "model_key": "sam3",
        "hf_repo_upstream": "facebook/sam3",
        "safetensors": "sam3.safetensors",
        "pt": "sam3.pt",
        "dir_name": "SAM3",
        "env_var": "FFMPEGA_SAM3_MODEL_DIR",
    },
    "sam3.1": {
        "model_key": "sam3_1",
        "hf_repo_upstream": "facebook/sam3.1",
        "safetensors": "sam3.1_multiplex.safetensors",
        "pt": "sam3.1_multiplex.pt",
        "dir_name": "SAM3.1",
        "env_var": "FFMPEGA_SAM3_1_MODEL_DIR",
    },
}

# Back-compat constants — kept so existing tests (and any external readers
# of these names) continue to work. Always reflect the SAM 3 spec.
_HF_REPO = "AEmotionStudio/sam3"
_SAFETENSORS_NAME = _MODEL_SPEC["sam3"]["safetensors"]
_PT_NAME = _MODEL_SPEC["sam3"]["pt"]


def _normalize_version(version: str | None) -> str:
    """Resolve a user-supplied version string to a _MODEL_SPEC key."""
    if not version:
        return DEFAULT_SAM_VERSION
    v = version.strip().lower()
    # Accept "sam3.1", "sam3_1", "3.1", "sam3" etc.
    if v in _MODEL_SPEC:
        return v
    aliases = {
        "sam3_1": "sam3.1", "3.1": "sam3.1", "v3.1": "sam3.1",
        "sam-3.1": "sam3.1", "sam 3.1": "sam3.1",
        "3": "sam3", "v3": "sam3", "sam-3": "sam3", "sam 3": "sam3",
    }
    return aliases.get(v, DEFAULT_SAM_VERSION)


def _get_model_dir(version: str = DEFAULT_SAM_VERSION) -> Path:
    """Return the model directory for ``version``, creating it if needed.

    Checks (in order):
    1. ``<version>.env_var`` (set by subprocess wrapper, e.g. FFMPEGA_SAM3_MODEL_DIR)
    2. ``ComfyUI/models/<dir_name>/`` (standard ComfyUI convention)
    3. Extension's own ``models/<dir_name>/`` (fallback for testing)
    """
    spec = _MODEL_SPEC[_normalize_version(version)]
    env_dir = os.environ.get(spec["env_var"])
    if env_dir:
        model_dir = Path(env_dir)
    else:
        from .platform import get_models_dir
        model_dir = Path(get_models_dir(spec["dir_name"]))

    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir


def _find_checkpoint(version: str = DEFAULT_SAM_VERSION) -> str:
    """Find or download the checkpoint for ``version``.

    Priority:
    1. Local .safetensors in the version's model dir (safe format)
    2. Local .pt
    3. AEmotionStudio mirror via core.model_manager.try_mirror_download
    4. Direct download from Meta's upstream HF repo

    Returns:
        Path to the checkpoint file.
    """
    v = _normalize_version(version)
    spec = _MODEL_SPEC[v]
    model_dir = _get_model_dir(v)

    # Prefer .safetensors (safe format)
    local_safetensors = model_dir / spec["safetensors"]
    if local_safetensors.is_file():
        log.info("Found local %s checkpoint: %s", v, local_safetensors)
        return str(local_safetensors)

    # Fallback to .pt
    local_pt = model_dir / spec["pt"]
    if local_pt.is_file():
        log.info("Found local %s checkpoint: %s", v, local_pt)
        return str(local_pt)

    # Guard: raise if downloads are disabled
    try:
        from . import model_manager
    except ImportError:
        from core import model_manager  # type: ignore
    model_manager.require_downloads_allowed(spec["model_key"])

    # 1) Try the AEmotionStudio mirror first (registered in _MODEL_INFO).
    log.info(
        "%s checkpoint not found locally. Trying AEmotionStudio mirror first...",
        v,
    )
    mirror_path = model_manager.try_mirror_download(
        spec["model_key"],
        spec["safetensors"],
        str(model_dir),
        convert_safetensors=False,
    )
    if mirror_path and os.path.isfile(mirror_path):
        return mirror_path
    mirror_path = model_manager.try_mirror_download(
        spec["model_key"],
        spec["pt"],
        str(model_dir),
        convert_safetensors=False,
    )
    if mirror_path and os.path.isfile(mirror_path):
        return mirror_path

    # 2) Fall back to Meta's upstream HF repo.
    log.info("Falling back to upstream %s...", spec["hf_repo_upstream"])
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise ImportError(
            "huggingface_hub is required to auto-download SAM models. "
            "Install with: pip install huggingface_hub"
        )

    for filename, label in [
        (spec["safetensors"], "safetensors"),
        (spec["pt"], ".pt format"),
    ]:
        try:
            path = model_manager.download_with_progress(
                spec["model_key"],
                lambda fn=filename: hf_hub_download(
                    repo_id=spec["hf_repo_upstream"],
                    filename=fn,
                    local_dir=str(model_dir),
                ),
                extra=label,
            )
            return path
        except Exception as e:
            log.debug("Upstream %s download failed for %s: %s",
                      spec["hf_repo_upstream"], filename, e)
            continue

    raise RuntimeError(
        f"Failed to download {v} checkpoint from either mirror "
        f"({spec['hf_repo_upstream']} or AEmotionStudio mirror). "
        f"You can manually place the checkpoint in {model_dir}/"
    )


# ---------------------------------------------------------------------------
#  Accelerate integration for memory-efficient loading
# ---------------------------------------------------------------------------

try:
    from accelerate import init_empty_weights
    from accelerate.utils import set_module_tensor_to_device
    _HAS_ACCELERATE = True
except ImportError:
    _HAS_ACCELERATE = False


def _load_state_dict(path: str, device: str = "cpu") -> dict:
    """Load a state dict from .safetensors or .pt using best available loader.

    Delegates to ``platform.load_torch_file`` which tries
    ``comfy.utils.load_torch_file`` first, then falls back to
    ``safetensors.torch.load_file`` / ``torch.load``.
    """
    try:
        from .platform import load_torch_file
    except ImportError:
        from core.platform import load_torch_file  # type: ignore

    return load_torch_file(path, device=device, safe_load=False)


def _load_efficient(model, ckpt: dict, device: str = "cpu") -> None:
    """Load checkpoint into model, tensor-by-tensor if accelerate is available.

    With accelerate: uses set_module_tensor_to_device() to avoid the 2x memory
    spike of load_state_dict() (model weights + full state dict in RAM).
    Without: falls back to standard load_state_dict(strict=False).
    """
    if _HAS_ACCELERATE:
        loaded, skipped = 0, 0
        param_names = {n for n, _ in model.named_parameters()}
        buffer_names = {n for n, _ in model.named_buffers()}
        valid_names = param_names | buffer_names
        for key, tensor in ckpt.items():
            if key in valid_names:
                try:
                    set_module_tensor_to_device(
                        model, key, device, value=tensor,
                    )
                    loaded += 1
                except Exception:
                    skipped += 1
            else:
                skipped += 1
        log.info(
            "SAM3 efficient load: %d tensors loaded, %d skipped",
            loaded, skipped,
        )
    else:
        missing, unexpected = model.load_state_dict(ckpt, strict=False)
        if missing:
            log.debug("SAM3 loaded with missing keys: %s", missing[:5])


def _remap_image_keys(model, ckpt: dict) -> dict:
    """Remap a raw SAM3 checkpoint to image model key format.

    SAM3's _load_checkpoint extracts detector/tracker keys.
    """
    sam3_image_ckpt = {
        k.replace("detector.", ""): v for k, v in ckpt.items() if "detector" in k
    }
    if model.inst_interactive_predictor is not None:
        sam3_image_ckpt.update({
            k.replace("tracker.", "inst_interactive_predictor.model."): v
            for k, v in ckpt.items() if "tracker" in k
        })
    # If no detector keys found, try loading directly (already extracted)
    if not sam3_image_ckpt:
        sam3_image_ckpt = ckpt
    return sam3_image_ckpt


def _remap_video_keys(ckpt: dict, version: str = "sam3") -> dict:
    """Remap a raw SAM/SAM 3.1 checkpoint to video model key format.

    SAM 3: builder loads 'model' sub-dict if present, else flat.
    SAM 3.1 (multiplex): the .pt has flat ``detector.*`` and ``tracker.model.*``
        keys; ``Sam3VideoTrackingMultiplexDemo`` expects them un-prefixed. Map
        both prefixes to the bare key name, merging into one state dict.
    """
    if version == "sam3.1":
        out: dict = {}
        for k, v in ckpt.items():
            if k.startswith("detector."):
                out[k[len("detector."):]] = v
            elif k.startswith("tracker.model."):
                out[k[len("tracker.model."):]] = v
            elif k.startswith("tracker."):
                # Defensive: bare "tracker." prefix (no .model.)
                out[k[len("tracker."):]] = v
            else:
                # Already un-prefixed (e.g. already-remapped or future
                # checkpoint layouts) — pass through.
                out[k] = v
        return out
    if "model" in ckpt and isinstance(ckpt["model"], dict):
        return ckpt["model"]
    return ckpt


def _warn_if_bad_checkpoint(ckpt: dict, model, model_type: str = "image") -> None:
    """Warn if checkpoint format appears wrong (>50% missing keys)."""
    param_names = {n for n, _ in model.named_parameters()}
    buffer_names = {n for n, _ in model.named_buffers()}
    valid_names = param_names | buffer_names
    matched = sum(1 for k in ckpt if k in valid_names)
    if matched < len(ckpt) * 0.5 and len(ckpt) > 0:
        log.warning(
            "SAM3 %s checkpoint has only %d/%d matching keys — likely wrong "
            "format (e.g. HuggingFace Transformers vs original .pt). "
            "Reconvert from .pt with: safetensors.torch.save_file("
            "torch.load('sam3.pt'), 'sam3.safetensors')",
            model_type, matched, len(ckpt),
        )


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Free all GPU VRAM before loading SAM3.

    Delegates to the shared ``_vram_utils.free_for_module``.
    """
    try:
        from ._vram_utils import free_for_module
    except ImportError:
        from core._vram_utils import free_for_module  # type: ignore
    free_for_module(exclude="sam3_masker")


# ---------------------------------------------------------------------------
#  Per-version compat shims for the video predictor
# ---------------------------------------------------------------------------
#
#  Both SAM 3 (Sam3VideoModel) and SAM 3.1's production multiplex tracker
#  (Sam3MultiplexTrackingWithInteractivity) expose roughly the same surface:
#
#    init_state(resource_path=..., offload_video_to_cpu=..., ...)
#    add_prompt(state, frame_idx, text_str=..., points=..., point_labels=...,
#               obj_id=..., rel_coordinates=...)
#    propagate_in_video(state, ...)  -> yields (frame_idx, outputs)
#    reset_state(state)
#
#  Differences absorbed here:
#    * SAM 3.1's add_prompt requires `clear_old_points` / `clear_old_boxes`
#      kwargs; SAM 3's call works without them.
#    * SAM 3.1 propagate_in_video output dict uses pred_masks_high_res +
#      object_score_logits; SAM 3 uses out_binary_masks + out_probs.

def _init_state_compat(video_model, *, resource_path: str, offload_video_to_cpu: bool = True):
    """Initialize the inference state, version-agnostic.

    SAM 3 signature:    init_state(resource_path, video_loader_type='cv2',
                                   offload_video_to_cpu=False)
    SAM 3.1 production: init_state(resource_path, offload_video_to_cpu=False,
                                   async_loading_frames=False, use_cv2=False,
                                   use_torchcodec=False, input_is_mp4=False)
    """
    import inspect
    try:
        sig = inspect.signature(video_model.init_state)
        params = sig.parameters
    except (ValueError, TypeError):
        params = {}

    kwargs: dict = {"resource_path": resource_path}
    if "offload_video_to_cpu" in params:
        kwargs["offload_video_to_cpu"] = offload_video_to_cpu
    # SAM 3.1 production uses use_cv2; SAM 3 uses video_loader_type.
    if "use_cv2" in params:
        kwargs["use_cv2"] = True
    elif "video_loader_type" in params:
        kwargs["video_loader_type"] = "cv2"
    return video_model.init_state(**kwargs)


def _add_text_prompt_compat(video_model, state, *, frame_idx: int, text: str):
    """Add a text prompt to the inference state, version-agnostic."""
    if not hasattr(video_model, "add_prompt"):
        raise NotImplementedError(
            "Video model has no add_prompt method — installed sam3 package "
            "may predate the SAM 3.1 production multiplex API."
        )
    try:
        # SAM 3.1 production signature (has clear_old_* kwargs)
        return video_model.add_prompt(
            state,
            frame_idx=frame_idx,
            text_str=text,
            clear_old_points=True,
            clear_old_boxes=True,
        )
    except TypeError:
        # SAM 3 signature (no clear_old_* kwargs)
        return video_model.add_prompt(state, frame_idx=frame_idx, text_str=text)


def _add_points_prompt_compat(
    video_model,
    state,
    *,
    frame_idx: int,
    obj_id: int,
    points: list,
    labels: list,
    rel_coordinates: bool = True,
):
    """Add point prompts to the inference state, version-agnostic."""
    if not hasattr(video_model, "add_prompt"):
        raise NotImplementedError(
            "Video model has no add_prompt method — installed sam3 package "
            "may predate the SAM 3.1 production multiplex API."
        )
    try:
        # SAM 3.1 production signature (has clear_old_* kwargs)
        return video_model.add_prompt(
            state,
            frame_idx=frame_idx,
            points=points,
            point_labels=labels,
            obj_id=obj_id,
            rel_coordinates=rel_coordinates,
            clear_old_points=True,
        )
    except TypeError:
        # SAM 3 signature
        return video_model.add_prompt(
            state,
            frame_idx=frame_idx,
            points=points,
            point_labels=labels,
            obj_id=obj_id,
            rel_coordinates=rel_coordinates,
        )


def _extract_propagate_masks_compat(outputs: dict):
    """Pull (binary_masks, out_probs) from a propagate_in_video output dict.

    SAM 3 returns ``out_binary_masks`` + ``out_probs``.
    SAM 3.1 multiplex production returns ``pred_masks_high_res`` /
    ``pred_masks`` + ``object_score_logits`` (sigmoid → probability).
    """
    if outputs is None:
        return None, None
    masks = outputs.get("out_binary_masks")
    probs = outputs.get("out_probs")
    if masks is not None:
        return masks, probs

    # SAM 3.1 multiplex keys — prefer high-res, sigmoid > 0 for binary.
    raw = outputs.get("pred_masks_high_res")
    if raw is None:
        raw = outputs.get("pred_masks")
    if raw is None:
        return None, None

    import torch as _t
    if _t.is_tensor(raw):
        masks = (raw > 0)
    elif isinstance(raw, list):
        masks = [(m > 0) if _t.is_tensor(m) else (m > 0) for m in raw]
    else:
        masks = raw

    logits = outputs.get("object_score_logits")
    if logits is not None and _t.is_tensor(logits):
        probs = _t.sigmoid(logits)
    else:
        probs = logits
    return masks, probs


def _offload_inference_state_to_cpu(
    inference_state: dict,
    flush_cuda: bool = False,
) -> None:
    """Move cached_frame_outputs GPU tensors to CPU.

    Called after each frame yield during propagation to keep VRAM bounded.
    Only sweeps ``cached_frame_outputs`` — other state (feature_cache,
    tracker_inference_states) is left on GPU as SAM3 reads them directly.
    """
    import torch

    _cfo = inference_state.get("cached_frame_outputs", {})
    for _cf_idx in list(_cfo.keys()):
        _cf_val = _cfo.get(_cf_idx)
        if _cf_val is None:
            continue
        if isinstance(_cf_val, dict):
            for _oid in list(_cf_val.keys()):
                t = _cf_val[_oid]
                if torch.is_tensor(t) and t.is_cuda:
                    _cf_val[_oid] = t.cpu()

    if flush_cuda and torch.cuda.is_available():
        torch.cuda.empty_cache()


# ---------------------------------------------------------------------------
#  Model loading
# ---------------------------------------------------------------------------

def load_image_model(device: str = "gpu", version: str = DEFAULT_SAM_VERSION):
    """Load and cache the SAM3 / SAM 3.1 image model + processor.

    Args:
        device: "gpu" (default) or "cpu". CPU avoids VRAM pressure but is slower.
        version: "sam3.1" (default) or "sam3". Cached separately per version
            so flipping between versions doesn't evict the other.

    Returns:
        Tuple of (model, Sam3Processor).

    Raises:
        ImportError: If SAM3 is not installed.
    """
    v = _normalize_version(version)

    use_cpu = device.lower() == "cpu"
    target_device = "cpu" if use_cpu else "cuda"

    # Fast path: model already cached (no lock needed for read)
    cached_model = _image_models.get(v)
    if cached_model is not None and _image_model_devices.get(v) == target_device:
        return cached_model, _image_processors.get(v)

    # Serialize loading to prevent duplicate copies on concurrent requests
    with _image_model_lock:
        # Double-check inside lock (another thread may have loaded while we waited)
        cached_model = _image_models.get(v)
        if cached_model is not None and _image_model_devices.get(v) == target_device:
            return cached_model, _image_processors.get(v)

        # Guard: fall back to CPU if CUDA was requested but isn't available
        if target_device == "cuda":
            import torch as _torch_check
            if not _torch_check.cuda.is_available():
                log.warning("CUDA unavailable, loading %s image model on CPU", v)
                target_device = "cpu"
                use_cpu = True

        if cached_model is not None and _image_processors.get(v) is not None:
            # If device changed, move model to new device
            if _image_model_devices.get(v) != target_device:
                import torch
                actual_device = target_device
                if actual_device == "cuda" and not torch.cuda.is_available():
                    log.warning("CUDA unavailable, keeping %s image model on CPU", v)
                    actual_device = "cpu"
                cached_model.to(torch.device(actual_device))  # type: ignore[attr-defined]
                _image_model_devices[v] = actual_device
            return cached_model, _image_processors.get(v)

        _patch_sam3_imports()

        try:
            from sam3.model_builder import build_sam3_image_model
            from sam3.model.sam3_image_processor import Sam3Processor
        except ImportError:
            raise ImportError(
                "SAM3 is not installed. Install with: "
                "pip install --no-deps git+https://github.com/facebookresearch/sam3.git"
            )

        if use_cpu:
            log.info("%s image model: CPU mode (avoids VRAM pressure, slower)", v)
        else:
            _free_vram()

        checkpoint_path = _find_checkpoint(v)

        # SAM 3.1's multiplex .pt has more tracker keys than the image
        # model's Sam3Model.inst_interactive_predictor expects — many will
        # be unmatched. The accelerate init_empty_weights path leaves those
        # tensors on the meta device, which then breaks model.to("cpu")
        # with "Cannot copy out of meta tensor". For sam3.1 specifically,
        # fall back to the standard load path which tolerates partial loads.
        _force_standard_load = (v == "sam3.1")

        # Determine loading strategy based on file extension
        if checkpoint_path.endswith(".safetensors"):
            log.info("Loading %s image model from safetensors: %s", v, checkpoint_path)

            # Try accelerate zero-copy init (allocates model with 0 bytes)
            _used_empty = False
            if _HAS_ACCELERATE and not _force_standard_load:
                try:
                    log.info("Using accelerate init_empty_weights for SAM3 image model")
                    with init_empty_weights():
                        model = build_sam3_image_model(
                            checkpoint_path=None,
                            load_from_HF=False,
                            enable_inst_interactivity=True,
                            device="cpu",
                        )
                    _used_empty = True
                except Exception as e:
                    log.info(
                        "init_empty_weights failed for SAM3 image model (%s), "
                        "falling back to standard init", e,
                    )
                    model = build_sam3_image_model(
                        checkpoint_path=None,
                        load_from_HF=False,
                        enable_inst_interactivity=True,
                        device="cpu",
                    )
            else:
                model = build_sam3_image_model(
                    checkpoint_path=None,
                    load_from_HF=False,
                    enable_inst_interactivity=True,
                    device="cpu",
                )

            ckpt = _load_state_dict(checkpoint_path, device="cpu")
            ckpt = _remap_image_keys(model, ckpt)
            _warn_if_bad_checkpoint(ckpt, model, "image")

            load_device = "cpu" if use_cpu else target_device
            if _used_empty:
                _load_efficient(model, ckpt, device=load_device)
            else:
                _load_efficient(model, ckpt, device="cpu")
                if not use_cpu:
                    import torch
                    model.to(torch.device(target_device))
        else:
            # .pt file — monkey-patch torch.load for weights_only compat
            log.info("Loading %s image model from .pt: %s", v, checkpoint_path)
            import torch
            _orig_load = torch.load
            def _patched_load(*args, **kwargs):
                kwargs["weights_only"] = False
                return _orig_load(*args, **kwargs)
            torch.load = _patched_load
            try:
                model = build_sam3_image_model(
                    checkpoint_path=checkpoint_path,
                    load_from_HF=False,
                    enable_inst_interactivity=True,
                )
            finally:
                torch.load = _orig_load

        # Note: SAM3 handles its own dtype management (bf16 autocast).
        # Do NOT call model.float() — it breaks mixed-precision inference.

        import torch
        if use_cpu:
            model.to(torch.device("cpu"))

        _image_models[v] = model
        _image_model_devices[v] = target_device
        _image_processors[v] = Sam3Processor(model)

        log.info("%s image model loaded successfully on %s",
                 v, target_device.upper())
        return _image_models[v], _image_processors[v]


def _find_sam31_pt_checkpoint() -> str:
    """Locate the SAM 3.1 .pt checkpoint, downloading if necessary.

    The production multiplex predictor (``build_sam3_multiplex_video_predictor``)
    uses ``torch.load`` internally, so we must hand it a ``.pt`` file — not
    the ``.safetensors`` that ``_find_checkpoint`` would normally prefer.
    """
    model_dir = _get_model_dir("sam3.1")
    local_pt = model_dir / _MODEL_SPEC["sam3.1"]["pt"]
    if local_pt.is_file():
        return str(local_pt)

    # Need to download — guard, then try mirror, then upstream.
    try:
        from . import model_manager
    except ImportError:
        from core import model_manager  # type: ignore
    model_manager.require_downloads_allowed("sam3_1")

    mirror = model_manager.try_mirror_download(
        "sam3_1",
        _MODEL_SPEC["sam3.1"]["pt"],
        str(model_dir),
        convert_safetensors=False,
    )
    if mirror and os.path.isfile(mirror):
        return mirror

    from huggingface_hub import hf_hub_download
    return model_manager.download_with_progress(
        "sam3_1",
        lambda: hf_hub_download(
            repo_id=_MODEL_SPEC["sam3.1"]["hf_repo_upstream"],
            filename=_MODEL_SPEC["sam3.1"]["pt"],
            local_dir=str(model_dir),
        ),
        extra=".pt format",
    )


def _load_sam31_video_model(target_device: str, use_cpu: bool):
    """Build the SAM 3.1 production multiplex tracker.

    Returns ``Sam3MultiplexTrackingWithInteractivity`` — the class with the
    SAM 3-compatible inference API (``init_state(resource_path=...)``,
    ``add_prompt(state, frame_idx, text_str=..., points=..., point_labels=...,
    obj_id=..., clear_old_points=...)``, ``propagate_in_video(state, ...)``,
    ``reset_state(state)``). Despite the "Demo" naming inside the multiplex
    module hierarchy, this is the production inference path used by the
    high-level ``Sam3MultiplexVideoPredictor`` wrapper.

    Returning the inner model directly (instead of the predictor wrapper)
    lets ``mask_video`` reuse the same flow it uses for SAM 3 — the only
    differences are absorbed by the per-version compat shims.
    """
    import torch

    try:
        from sam3.model_builder import (  # type: ignore[attr-defined]
            build_sam3_multiplex_video_predictor,
        )
    except ImportError as e:
        raise ImportError(
            "SAM 3.1 multiplex predictor builder not found in installed "
            "sam3 package. Run: pip install --no-deps --upgrade "
            "--force-reinstall git+https://github.com/facebookresearch/sam3.git"
        ) from e

    checkpoint_path = _find_sam31_pt_checkpoint()
    log.info("Loading SAM 3.1 multiplex production model from: %s",
             checkpoint_path)

    # Monkey-patch torch.load for weights_only=True compatibility — the
    # builder calls torch.load(weights_only=True) which fails on PT 2.6+
    # for ckpts containing non-tensor metadata.
    _orig_load = torch.load

    def _patched_load(*args, **kwargs):
        kwargs["weights_only"] = False
        return _orig_load(*args, **kwargs)
    torch.load = _patched_load

    # The builder force-moves the model to CUDA via .cuda().eval(). If we
    # want CPU mode (or if CUDA is unavailable), temporarily hide CUDA so
    # the .cuda() call no-ops, then explicitly move to CPU afterward.
    if use_cpu:
        _orig_cuda_available = torch.cuda.is_available
        torch.cuda.is_available = lambda: False
        # Also stub Module.cuda so .cuda().eval() returns self instead of
        # raising "Torch not compiled with CUDA enabled" style errors.
        import torch.nn as _nn
        _orig_cuda_fn = _nn.Module.cuda

        def _cuda_noop(self, *a, **k):
            return self
        _nn.Module.cuda = _cuda_noop

    try:
        predictor = build_sam3_multiplex_video_predictor(
            checkpoint_path=checkpoint_path,
            bpe_path=None,  # uses sam3/assets/bpe_simple_vocab_16e6.txt.gz
            warm_up=False,
            async_loading_frames=False,  # we feed file-paths, no async loader
            # Disable FlashAttention 3 — it requires the optional
            # flash_attn_interface package which isn't a hard dep.
            use_fa3=False,
            # Use the complex-valued RoPE that the checkpoint actually
            # ships (use_rope_real=True introduces split real/imag buffers
            # the ckpt doesn't have).
            use_rope_real=False,
        )
    finally:
        torch.load = _orig_load
        if use_cpu:
            torch.cuda.is_available = _orig_cuda_available  # type: ignore[name-defined]
            _nn.Module.cuda = _orig_cuda_fn  # type: ignore[name-defined]

    # Extract the inner production model (Sam3MultiplexTrackingWithInteractivity)
    # which has the SAM 3-compatible add_prompt / init_state / propagate /
    # reset_state API our existing mask_video() flow already calls.
    model = predictor.model

    if use_cpu:
        model.to(torch.device("cpu"))
    elif target_device == "cuda":
        # Builder already moved to CUDA; ensure it's on the right device.
        model.to(torch.device("cuda"))

    return model


def load_video_model(device: str = "gpu", version: str = DEFAULT_SAM_VERSION):
    """Load and cache the SAM3 / SAM 3.1 video model.

    SAM 3 uses ``build_sam3_video_model`` (returns ``Sam3VideoModel``).
    SAM 3.1 uses ``build_sam3_multiplex_video_predictor`` then extracts the
    inner ``Sam3MultiplexTrackingWithInteractivity`` — the production
    multiplex tracker with the SAM 3-compatible inference API.

    Args:
        device: "gpu" (default) or "cpu". CPU mode avoids VRAM pressure by
            moving the model off-GPU before frame loading. Slower but necessary
            when VRAM is insufficient (~12 GB needed for long videos on GPU).
        version: "sam3.1" (default) or "sam3". Cached separately per version.

    Returns:
        Video model/predictor instance for the requested version.

    Raises:
        ImportError: If SAM3 is not installed.
        AttributeError: If ``version="sam3.1"`` is requested but the installed
            ``sam3`` package is older than the SAM 3.1 release (the multiplex
            builder will be missing). Run ``python install.py`` to upgrade.
    """
    v = _normalize_version(version)

    use_cpu = device.lower() == "cpu"
    target_device = "cpu" if use_cpu else "cuda"

    # Fast path: model already cached (no lock needed for read)
    cached_model = _video_models.get(v)
    if cached_model is not None and _video_model_devices.get(v) == target_device:
        return cached_model

    # Serialize loading to prevent duplicate copies on concurrent requests
    with _video_model_lock:
        # Double-check inside lock
        cached_model = _video_models.get(v)
        if cached_model is not None and _video_model_devices.get(v) == target_device:
            return cached_model

        # Guard: fall back to CPU if CUDA was requested but isn't available
        if target_device == "cuda":
            import torch as _torch_check
            if not _torch_check.cuda.is_available():
                log.warning("CUDA unavailable, loading %s video model on CPU", v)
                target_device = "cpu"
                use_cpu = True

        if cached_model is not None:
            # If device changed, move model to new device
            if _video_model_devices.get(v) != target_device:
                import torch
                actual_device = target_device
                if actual_device == "cuda" and not torch.cuda.is_available():
                    log.warning("CUDA unavailable, keeping %s video model on CPU", v)
                    actual_device = "cpu"
                cached_model.to(torch.device(actual_device))  # type: ignore[attr-defined]
                _video_model_devices[v] = actual_device
            return cached_model

        _patch_sam3_imports()

        # SAM 3.1: dedicated build path through the production predictor.
        # Returns Sam3MultiplexTrackingWithInteractivity which has the
        # SAM 3-compatible add_prompt / init_state / propagate_in_video /
        # reset_state API.
        if v == "sam3.1":
            if use_cpu:
                log.info("sam3.1 video model: CPU mode "
                         "(avoids VRAM frame-loading OOM, slower)")
            else:
                _free_vram()
            model = _load_sam31_video_model(target_device, use_cpu)
            _video_models[v] = model
            _video_model_devices[v] = target_device
            log.info("sam3.1 video model loaded successfully on %s",
                     target_device.upper())
            return model

        # SAM 3 path (unchanged below).
        try:
            from sam3.model_builder import (
                build_sam3_video_model as _build_video_model,
            )
        except ImportError as e:
            raise ImportError(
                "SAM3 is not installed. Install with: "
                "pip install --no-deps git+https://github.com/facebookresearch/sam3.git"
            ) from e

        if use_cpu:
            log.info("%s video model: CPU mode "
                     "(avoids VRAM frame-loading OOM, slower)", v)
        else:
            _free_vram()

        checkpoint_path = _find_checkpoint(v)
        log.info("Loading %s video model from: %s", v, checkpoint_path)

        # SAM 3.1's multiplex video model has many parameters not present
        # in SAM 3's tracker. Skip accelerate init_empty_weights for sam3.1
        # for the same meta-tensor reason as the image model.
        _force_standard_load = (v == "sam3.1")

        import torch

        if checkpoint_path.endswith(".safetensors"):
            # build_sam3_video_model uses torch.load internally which can't
            # handle safetensors. Build without checkpoint, then load manually.
            log.info("Loading SAM3 video model from safetensors: %s", checkpoint_path)

            # Try accelerate zero-copy init
            _used_empty = False
            if _HAS_ACCELERATE and not _force_standard_load:
                try:
                    log.info("Using accelerate init_empty_weights for SAM3 video model")
                    if use_cpu:
                        _orig_cuda_available = torch.cuda.is_available
                        torch.cuda.is_available = lambda: False
                    try:
                        with init_empty_weights():
                            model = _build_video_model(
                                checkpoint_path=None,
                                load_from_HF=False,
                                device="cpu",
                            )
                        _used_empty = True
                    finally:
                        if use_cpu:
                            torch.cuda.is_available = _orig_cuda_available
                except Exception as e:
                    log.info(
                        "init_empty_weights failed for SAM3 video model (%s), "
                        "falling back to standard init", e,
                    )
                    # Fall through to standard init below

            if not _used_empty:
                if use_cpu:
                    _orig_cuda_available = torch.cuda.is_available
                    torch.cuda.is_available = lambda: False
                    try:
                        model = _build_video_model(
                            checkpoint_path=None,
                            load_from_HF=False,
                            device="cpu",
                        )
                    finally:
                        torch.cuda.is_available = _orig_cuda_available
                else:
                    model = _build_video_model(
                        checkpoint_path=None,
                        load_from_HF=False,
                        device="cpu",
                    )

            ckpt = _load_state_dict(checkpoint_path, device="cpu")
            ckpt = _remap_video_keys(ckpt, version=v)
            _warn_if_bad_checkpoint(ckpt, model, "video")

            load_device = "cpu" if use_cpu else target_device
            if _used_empty:
                _load_efficient(model, ckpt, device=load_device)
            else:
                _load_efficient(model, ckpt, device="cpu")
                if not use_cpu:
                    model.to(torch.device(target_device))
        else:
            # .pt file — sam3's builder uses torch.load(weights_only=True)
            # which fails on PyTorch 2.6+ with some checkpoints.
            # Monkey-patch torch.load to use weights_only=False.
            _orig_load = torch.load
            def _patched_load(*args, **kwargs):
                kwargs["weights_only"] = False
                return _orig_load(*args, **kwargs)
            torch.load = _patched_load
            if use_cpu:
                _orig_cuda_available = torch.cuda.is_available
                torch.cuda.is_available = lambda: False
            try:
                model = _build_video_model(
                    checkpoint_path=checkpoint_path,
                    load_from_HF=False,
                )
            finally:
                torch.load = _orig_load
                if use_cpu:
                    torch.cuda.is_available = _orig_cuda_available

        # Note: SAM3's Sam3TrackerPredictor.__init__ enters a permanent bfloat16
        # autocast context. This is by design — SAM3 uses mixed-precision bf16
        # inference. Do NOT call model.float() or disable autocast; it breaks
        # the model's internal dtype expectations.

        if use_cpu:
            # Belt-and-suspenders: explicitly move any remaining CUDA tensors to CPU
            model.to(torch.device("cpu"))

        _video_models[v] = model
        _video_model_devices[v] = target_device
        log.info("%s video model loaded successfully on %s",
                 v, target_device.upper())
        return _video_models[v]


# ---------------------------------------------------------------------------
#  Image masking with text prompts
# ---------------------------------------------------------------------------

def mask_image_with_text(
    image_path: str,
    prompt: str,
    device: str = "gpu",
    version: str = DEFAULT_SAM_VERSION,
) -> np.ndarray:
    """Generate masks for objects described by a text prompt.

    Args:
        image_path: Path to the image file.
        prompt: Text description of what to segment (e.g. "the dog").
        device: "gpu" (default) or "cpu".
        version: "sam3.1" (default) or "sam3".

    Returns:
        Binary mask as numpy array (H, W) where 255=masked, 0=unmasked.
    """
    from PIL import Image

    model, processor = load_image_model(device=device, version=version)
    image = Image.open(image_path).convert("RGB")

    inference_state = processor.set_image(image)
    output = processor.set_text_prompt(state=inference_state, prompt=prompt)

    masks = output["masks"]  # (N, H, W) boolean
    scores = output["scores"]

    if len(masks) == 0:
        log.warning("SAM3 found no objects matching prompt: '%s'", prompt)
        img_np = np.array(image)
        return np.zeros(img_np.shape[:2], dtype=np.uint8)

    # Take the highest-scoring mask, or merge all
    if hasattr(masks, 'cpu'):
        masks = masks.cpu().numpy()
    if masks.ndim == 4:
        masks = masks.squeeze(1)

    combined = np.any(masks > 0, axis=0).astype(np.uint8) * 255
    return combined


def mask_image_with_points(
    image_path: str,
    points: list,
    labels: list,
    image_width: int = 0,
    image_height: int = 0,
    device: str = "gpu",
    min_score: float = 0.5,
    multi_object: bool = False,
    box: list | None = None,
    version: str = DEFAULT_SAM_VERSION,
) -> np.ndarray:
    """Generate mask from point prompts using SAM3's interactive predictor.

    Uses ``Sam3Processor.set_image()`` to prepare backbone features, then calls
    ``model.predict_inst()`` which properly routes features through SAM3's
    SAM2-based interactive predictor for point-prompted segmentation.

    Args:
        image_path: Path to the image file.
        points: List of [x, y] pixel coordinates on the image.
        labels: List of 1 (foreground) / 0 (background) for each point.
        image_width: Width of the image the points were drawn on (for scaling).
            If 0, uses the actual image width (no scaling).
        image_height: Height of the image the points were drawn on (for scaling).
            If 0, uses the actual image height (no scaling).
        device: "gpu" (default) or "cpu".
        min_score: Minimum confidence score to accept a mask (0.0–1.0).
            If no mask meets this threshold, returns empty mask.
        multi_object: If True, treat each positive point as a separate object.
            Generates independent masks per point and OR-combines them.
        box: Optional bounding box [x1, y1, x2, y2] for SAM3 box prompt.
            Coordinates are in the same space as points (image_width × image_height).
            Can be combined with point prompts for refinement.

    Returns:
        Binary mask as numpy array (H, W) where 255=masked, 0=unmasked.
    """
    import torch
    from PIL import Image

    if not points or not labels:
        log.warning("mask_image_with_points: no points provided")
        img = Image.open(image_path).convert("RGB")
        return np.zeros((img.height, img.width), dtype=np.uint8)

    # SAM 3.1's multiplex .pt stores the interactive predictor weights
    # under the multiplex tracker's key schema, which isn't bit-compatible
    # with Sam3Image.inst_interactive_predictor (the SAM 2-style tracker
    # SAM 3 uses). Loading the multiplex checkpoint into the image model
    # leaves the interactive predictor partially uninitialized, so point
    # prompts on still images fall back to sam3. (sam3.1 video tracking
    # works fine — it uses the multiplex tracker's own interactive head.)
    _v = _normalize_version(version)
    if _v == "sam3.1":
        log.warning(
            "Single-image point prompts fall back to sam3: SAM 3.1's "
            "image-model interactive head isn't bit-compatible yet. "
            "Text prompts on sam3.1 use the newer detector; sam3.1 video "
            "tracking (mask_video) uses the multiplex predictor directly."
        )
        _v = "sam3"

    model, processor = load_image_model(device=device, version=_v)

    # SAM3 runs mixed-precision bf16 inference. Sam3TrackerPredictor.__init__
    # enters a bfloat16 autocast context, but it can be popped off the
    # thread-local stack between runs (e.g. after the first predict_inst on a
    # worker thread), leaving the model with bf16 activations but float32
    # weights → "mat1 and mat2 must have the same dtype" in F.linear. Re-enter
    # the autocast explicitly so every conv/linear casts consistently, matching
    # the video tracking path.
    from contextlib import nullcontext
    _use_cpu = device.lower() == "cpu"
    autocast_ctx = (
        torch.autocast("cuda", dtype=torch.bfloat16)
        if (torch.cuda.is_available() and not _use_cpu)
        else nullcontext()
    )

    image = Image.open(image_path).convert("RGB")
    w, h = image.size

    # Scale points from source image dimensions to actual frame dimensions
    src_w = image_width if image_width > 0 else w
    src_h = image_height if image_height > 0 else h
    scale_x = w / src_w
    scale_y = h / src_h

    scaled_points = []
    valid_labels = []
    for pt, lbl in zip(points, labels):
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        try:
            px = float(pt[0]) * scale_x
            py = float(pt[1]) * scale_y
            # Clamp to image bounds
            px = max(0.0, min(float(w - 1), px))
            py = max(0.0, min(float(h - 1), py))
            scaled_points.append([px, py])
            valid_labels.append(int(lbl))
        except (TypeError, ValueError):
            continue

    if not scaled_points and not box:
        log.warning("mask_image_with_points: no valid points or box after scaling")
        return np.zeros((h, w), dtype=np.uint8)

    n_pos = sum(1 for l in valid_labels if l == 1)
    n_neg = sum(1 for l in valid_labels if l == 0)
    log.info(
        "mask_image_with_points: %d points (%d pos, %d neg) on %dx%d image "
        "(min_score=%.2f, multi_object=%s, box=%s)",
        len(scaled_points), n_pos, n_neg, w, h, min_score, multi_object,
        bool(box),
    )

    # --- Scale box coordinates if provided ---
    scaled_box = None
    if box and len(box) == 4:
        try:
            bx1 = max(0.0, min(float(w - 1), float(box[0]) * scale_x))
            by1 = max(0.0, min(float(h - 1), float(box[1]) * scale_y))
            bx2 = max(0.0, min(float(w - 1), float(box[2]) * scale_x))
            by2 = max(0.0, min(float(h - 1), float(box[3]) * scale_y))
            scaled_box = [bx1, by1, bx2, by2]
            log.info("mask_image_with_points: box [%.0f,%.0f,%.0f,%.0f]",
                     bx1, by1, bx2, by2)
        except (TypeError, ValueError):
            log.warning("mask_image_with_points: invalid box coords, ignoring")

    # --- Multi-object mode: one prediction per positive point ---
    if multi_object and n_pos > 1:
        # Separate positive and negative points
        neg_points = [p for p, l in zip(scaled_points, valid_labels) if l == 0]
        neg_labels = [0] * len(neg_points)

        combined_mask = np.zeros((h, w), dtype=np.uint8)
        per_object_masks = []  # list of (mask, score) per accepted object
        accepted = 0

        with torch.inference_mode(), autocast_ctx:
            state = processor.set_image(image)

            for i, (pt, lbl) in enumerate(zip(scaled_points, valid_labels)):
                if lbl != 1:
                    continue  # skip negative points

                # Each positive point + all negative points
                obj_pts = [pt] + neg_points
                obj_lbls = [1] + neg_labels

                pt_coords = np.array(obj_pts, dtype=np.float32)
                pt_labels_arr = np.array(obj_lbls, dtype=np.int32)

                masks, scores, _ = model.predict_inst(
                    inference_state=state,
                    point_coords=pt_coords,
                    point_labels=pt_labels_arr,
                    multimask_output=True,  # always get 3 candidates
                )

                if masks.ndim == 4:
                    masks = masks.squeeze(0)
                if masks.shape[0] == 0:
                    continue

                best_idx = np.argmax(scores)
                if float(scores[best_idx]) < min_score:
                    log.info(
                        "mask_image_with_points: object %d rejected "
                        "(score=%.3f < min_score=%.2f)",
                        i, float(scores[best_idx]), min_score,
                    )
                    continue

                best_mask = masks[best_idx]
                while best_mask.ndim > 2:
                    best_mask = best_mask.squeeze(0)

                obj_mask = (best_mask > 0).astype(np.uint8) * 255
                combined_mask = np.maximum(combined_mask, obj_mask)
                per_object_masks.append(obj_mask)
                accepted += 1
                log.info(
                    "mask_image_with_points: object %d accepted "
                    "(score=%.3f)",
                    i, float(scores[best_idx]),
                )

        if accepted == 0:
            log.warning(
                "mask_image_with_points: no objects passed threshold "
                "(min_score=%.2f)", min_score,
            )
            return np.zeros((h, w), dtype=np.uint8)

        coverage = 100.0 * np.count_nonzero(combined_mask) / combined_mask.size
        log.info(
            "mask_image_with_points: multi-object mask "
            "(%d objects, coverage=%.1f%%)",
            accepted, coverage,
        )
        # Return tuple: (combined_mask, per_object_masks_list)
        return combined_mask, per_object_masks

    # --- Standard single-object mode ---
    point_coords = np.array(scaled_points, dtype=np.float32)
    point_labels = np.array(valid_labels, dtype=np.int32)

    # Prepend box corners if box prompt was provided
    if scaled_box:
        box_pts = np.array([[scaled_box[0], scaled_box[1]],
                            [scaled_box[2], scaled_box[3]]], dtype=np.float32)
        box_lbls = np.array([2, 3], dtype=np.int32)  # SAM2: 2=TL, 3=BR
        point_coords = np.concatenate([box_pts, point_coords], axis=0)
        point_labels = np.concatenate([box_lbls, point_labels], axis=0)

    with torch.inference_mode(), autocast_ctx:
        # 1. Prepare backbone features via Sam3Processor (includes sam2_backbone_out)
        state = processor.set_image(image)

        # 2. Use model.predict_inst() which routes sam2_backbone_out through
        #    the interactive predictor with proper feature preparation.
        #    Single point → multimask_output=True for best of 3 masks
        #    Multiple points or box → multimask_output=False
        multi = (len(scaled_points) == 1 and not scaled_box)
        masks, scores, _ = model.predict_inst(
            inference_state=state,
            point_coords=point_coords,
            point_labels=point_labels,
            multimask_output=multi,
        )

    # masks shape: (C, H, W) where C=3 (multi) or C=1 (single)
    if masks.ndim == 4:
        masks = masks.squeeze(0)
    if masks.shape[0] == 0:
        log.warning("mask_image_with_points: SAM3 returned no masks")
        return np.zeros((h, w), dtype=np.uint8)

    # Pick the best mask by score
    best_idx = np.argmax(scores)

    # Check against minimum confidence threshold
    if float(scores[best_idx]) < min_score:
        log.warning(
            "mask_image_with_points: best mask rejected "
            "(score=%.3f < min_score=%.2f)",
            float(scores[best_idx]), min_score,
        )
        return np.zeros((h, w), dtype=np.uint8)

    best_mask = masks[best_idx]

    # Squeeze any extra dims
    while best_mask.ndim > 2:
        best_mask = best_mask.squeeze(0)

    result = (best_mask > 0).astype(np.uint8) * 255
    coverage = 100.0 * np.count_nonzero(result) / result.size
    log.info(
        "mask_image_with_points: mask generated (score=%.3f, coverage=%.1f%%)",
        float(scores[best_idx]), coverage,
    )
    return result


def refine_mask_grabcut(
    image_path: str,
    mask_np: np.ndarray,
    iterations: int = 5,
) -> np.ndarray:
    """Refine a binary mask using OpenCV's GrabCut algorithm.

    Uses the initial SAM3 mask to create a trimap (definite FG, probable FG,
    definite BG) and runs GrabCut to snap edges to actual image boundaries.

    Args:
        image_path: Path to the original RGB image.
        mask_np: Binary mask (H, W) uint8, 255=foreground, 0=background.
        iterations: Number of GrabCut iterations (default 5).

    Returns:
        Refined binary mask (H, W) uint8, 255=foreground, 0=background.
    """
    try:
        import cv2
    except ImportError:
        log.warning("refine_mask_grabcut: OpenCV not available, returning original mask")
        return mask_np

    try:
        img = cv2.imread(image_path)
        if img is None:
            log.warning("refine_mask_grabcut: could not read image")
            return mask_np

        h, w = mask_np.shape[:2]
        if img.shape[:2] != (h, w):
            img = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)

        # Build trimap from SAM3 mask
        gc_mask = np.full((h, w), cv2.GC_BGD, dtype=np.uint8)

        # Definite foreground: eroded mask (inner region)
        kernel_fg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        fg_eroded = cv2.erode(mask_np, kernel_fg, iterations=1)
        gc_mask[fg_eroded > 127] = cv2.GC_FGD

        # Probable foreground: mask border region (between eroded and dilated)
        kernel_border = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        fg_dilated = cv2.dilate(mask_np, kernel_border, iterations=1)
        prob_fg = (mask_np > 127) & (fg_eroded <= 127)
        gc_mask[prob_fg] = cv2.GC_PR_FGD

        # Probable background: the dilation border
        prob_bg = (fg_dilated > 127) & (mask_np <= 127)
        gc_mask[prob_bg] = cv2.GC_PR_BGD

        # Check we have enough FG/BG pixels for GrabCut to work
        n_fgd = np.count_nonzero(gc_mask == cv2.GC_FGD)
        n_bgd = np.count_nonzero(gc_mask == cv2.GC_BGD)
        if n_fgd < 10 or n_bgd < 10:
            log.info("refine_mask_grabcut: not enough FG/BG for GrabCut, skipping")
            return mask_np

        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)

        cv2.grabCut(img, gc_mask, None, bgd_model, fgd_model,
                    iterations, cv2.GC_INIT_WITH_MASK)

        # Extract refined mask
        refined = np.where(
            (gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD),
            np.uint8(255), np.uint8(0),
        )

        old_coverage = 100.0 * np.count_nonzero(mask_np) / mask_np.size
        new_coverage = 100.0 * np.count_nonzero(refined) / refined.size
        log.info(
            "refine_mask_grabcut: refined mask (%d iters, "
            "coverage %.1f%% → %.1f%%)",
            iterations, old_coverage, new_coverage,
        )
        return refined

    except Exception as e:
        log.warning("refine_mask_grabcut: failed: %s, returning original", e)
        return mask_np


# ---------------------------------------------------------------------------
#  Video masking with text prompts
# ---------------------------------------------------------------------------


def _get_video_fps(video_path: str) -> float:
    """Extract FPS from a video file using ffprobe.

    Returns:
        Frame rate as a float, defaults to 30.0 if extraction fails.
    """
    probe = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "csv=p=0",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    fps_str = probe.stdout.strip()
    try:
        if "/" in fps_str:
            num, den = fps_str.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f != 0 else 30.0
        return float(fps_str) if fps_str else 30.0
    except (ValueError, ZeroDivisionError):
        return 30.0

# ── tqdm suppression ──────────────────────────────────────────────────
# SAM3's propagate_in_video uses tqdm bars internally.  In ComfyUI's
# non-TTY console every \r update prints as a new line, producing
# hundreds of duplicate progress lines.  We wrap SAM3's tqdm reference
# to force disable=True, preserving all tqdm internals while silencing
# the output.
import contextlib as _contextlib

def _make_silent_tqdm(real_tqdm):
    """Return a wrapper that forces disable=True on the real tqdm."""
    def _silent_tqdm(*args, **kwargs):
        kwargs["disable"] = True
        return real_tqdm(*args, **kwargs)
    return _silent_tqdm

@_contextlib.contextmanager
def _suppress_tqdm():
    """Monkey-patch SAM3's tqdm references to suppress progress bars."""
    _patches: list[tuple] = []  # (module, original_tqdm)
    _modules = [
        "sam3.model.sam3_video_inference",
        "sam3.model.io_utils",
        "sam3.model.utils.sam2_utils",
    ]
    for mod_name in _modules:
        try:
            import importlib
            _mod = importlib.import_module(mod_name)
            _orig = getattr(_mod, "tqdm", None)
            if _orig is not None:
                _patches.append((_mod, _orig))
                _mod.tqdm = _make_silent_tqdm(_orig)  # type: ignore[attr-defined]
        except (ImportError, AttributeError):
            pass
    try:
        yield
    finally:
        for _mod, _orig in _patches:
            _mod.tqdm = _orig

@_contextlib.contextmanager
def _patch_postprocess_keyerror():
    """Fix SAM3 KeyError in _postprocess_output.

    SAM3's ``_postprocess_output`` (sam3_video_inference.py:449) does a bare
    ``out["obj_id_to_score"][obj_id]`` for every obj in ``obj_id_to_mask``.
    When ``max_num_objects`` suppresses objects, some obj_ids exist in the
    mask dict but NOT in the score dict → KeyError.

    This context manager monkey-patches the class method to use ``.get()``
    with a 0.0 fallback, matching how ``obj_id_to_tracker_score`` is already
    handled (line 454-456 in the same file).
    """
    _patched = False
    _orig_method = None
    _cls = None
    try:
        import importlib
        _mod = importlib.import_module("sam3.model.sam3_video_inference")
        # Find the class that has _postprocess_output
        for _name in dir(_mod):
            _obj = getattr(_mod, _name)
            if isinstance(_obj, type) and hasattr(_obj, "_postprocess_output"):
                _cls = _obj
                break
        if _cls is not None:
            _orig_method = _cls._postprocess_output

            import functools
            @functools.wraps(_orig_method)
            def _safe_postprocess(self, inference_state, out, *args, **kwargs):
                # Wrap obj_id_to_score with a defaultdict-like fallback
                score_dict = out.get("obj_id_to_score", {})
                class _SafeScoreDict(dict):
                    """Dict that returns 0.0 for missing keys."""
                    def __missing__(self, key):
                        return 0.0
                out["obj_id_to_score"] = _SafeScoreDict(score_dict)
                return _orig_method(self, inference_state, out, *args, **kwargs)

            _cls._postprocess_output = _safe_postprocess
            _patched = True
    except (ImportError, AttributeError):
        pass
    try:
        yield
    finally:
        if _patched and _cls is not None and _orig_method is not None:
            _cls._postprocess_output = _orig_method

# ---------------------------------------------------------------------------
#  Native ComfyUI SAM 3.1 video path (in-process, ModelPatcher-managed)
# ---------------------------------------------------------------------------
#
#  ComfyUI ships native SAM 3 / 3.1 support (comfy_extras/nodes_sam3.py,
#  comfy/ldm/sam3/). It loads the multiplex checkpoint as a standard
#  ModelPatcher, so it participates in ComfyUI's VRAM lifecycle
#  (load_model_gpu / offloading / dtype casting) and has none of the
#  ~1.5 GB CUDA-context leak the upstream `sam3` pip package has. That lets
#  the SAM 3.1 *video* path run IN-PROCESS with no subprocess — and the
#  detector-driven OOM we hit through the upstream predictor disappears.
#
#  Gated behind FFMPEGA_SAM3_NATIVE (default on), used only for
#  version == "sam3.1" video masking. Any failure falls back to the legacy
#  subprocess + upstream-sam3 path. Image masks and plain SAM 3 are untouched.

# Cache: version -> (ModelPatcher, CLIP). CLIP is shared by text masking.
_native_models: dict[str, tuple] = {}
_native_model_lock = threading.Lock()

# SAM 3's CLIP text encoder sets return_projected_pooled=False, so its
# text_projection weight is never used at inference. Our mirror checkpoint
# stores it in facebook's [1024, 512] layout, which doesn't match the square
# [1024, 1024] tensor ComfyUI's CLIPTextModel builds — dropping the unused key
# lets the (strict=False) CLIP load succeed.
_NATIVE_UNUSED_CLIP_KEY = "detector.backbone.language_backbone.encoder.text_projection"


def _use_native_sam3_video(version: str = DEFAULT_SAM_VERSION) -> bool:
    """True when SAM 3.1 video masking should use ComfyUI's native model.

    Requires the flag on (FFMPEGA_SAM3_NATIVE != "0") and a usable ComfyUI
    runtime (comfy.sd / comfy.model_management importable).
    """
    if _normalize_version(version) != "sam3.1":
        return False
    if os.environ.get("FFMPEGA_SAM3_NATIVE", "1").strip() == "0":
        return False
    try:
        import comfy.sd  # noqa: F401
        import comfy.model_management  # noqa: F401
    except Exception:
        return False
    return True


def _load_native_sam31(version: str = DEFAULT_SAM_VERSION):
    """Load + cache the native SAM 3.1 ModelPatcher and CLIP (per version)."""
    v = _normalize_version(version)
    cached = _native_models.get(v)
    if cached is not None:
        return cached
    with _native_model_lock:
        cached = _native_models.get(v)
        if cached is not None:
            return cached
        import comfy.sd
        import comfy.utils

        ckpt = _find_checkpoint(v)
        log.info("Loading native ComfyUI SAM 3.1 model: %s", ckpt)
        sd = comfy.utils.load_torch_file(ckpt)
        sd.pop(_NATIVE_UNUSED_CLIP_KEY, None)
        out = comfy.sd.load_state_dict_guess_config(
            sd, output_vae=False, output_clip=True)
        if out is None or out[0] is None:
            raise RuntimeError(
                f"ComfyUI did not recognize {ckpt} as a SAM 3 checkpoint")
        model, clip = out[0], out[1]
        _native_models[v] = (model, clip)
        return model, clip


def _mask_video_native_sam31(
    video_path: str,
    prompt: str,
    output_dir: Optional[str],
    device: str,
    max_objects: int,
    det_threshold: float,
    points: Optional[list],
    labels: Optional[list],
    point_src_width: int,
    point_src_height: int,
    version: str = "sam3.1",
) -> str:
    """SAM 3.1 video masking via ComfyUI's native model (in-process).

    Mirrors mask_video()'s contract: returns a path to a grayscale mask.mp4
    (white = object). Point prompts segment frame 0 via forward_segment() and
    feed that as an initial mask to the memory tracker; text prompts go through
    SAM 3's CLIP as detection conditioning. Both run under ComfyUI's VRAM
    management, so the model offloads cleanly and the legacy OOM is avoided.
    """
    import torch
    import torch.nn.functional as F
    from PIL import Image
    import comfy.model_management
    from comfy.ldm.sam3.tracker import unpack_masks

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_sam3_")
    frames_dir = os.path.join(output_dir, "frames")
    masks_dir = os.path.join(output_dir, "masks")
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(masks_dir, exist_ok=True)

    model, clip = _load_native_sam31(version)

    try:
        # 1. Extract frames
        log.info("Native SAM 3.1: extracting frames from %s", video_path)
        subprocess.run(
            ["ffmpeg", "-i", video_path, "-q:v", "2",
             os.path.join(frames_dir, "%06d.jpg")],
            capture_output=True, check=True,
        )
        frame_files = sorted(Path(frames_dir).glob("*.jpg"))
        if not frame_files:
            raise RuntimeError(f"No frames extracted from {video_path}")
        fps = _get_video_fps(video_path)

        # 2. Load frames -> [N, H, W, 3] float32 0-1 (ComfyUI IMAGE layout)
        frames_np = [
            np.asarray(Image.open(fp).convert("RGB"), dtype=np.float32) / 255.0
            for fp in frame_files
        ]
        images = torch.from_numpy(np.stack(frames_np))  # [N,H,W,3]
        N, H, W, _ = images.shape
        log.info("Native SAM 3.1: %d frames @ %dx%d", N, W, H)

        # 3. Load model onto GPU under ComfyUI's VRAM management.
        #    inference_mode is essential: without it autograd retains every
        #    1008x1008 activation, pushing peak VRAM to ~10 GB (OOM on a 12 GB
        #    card). Under inference_mode the same run peaks at ~3 GB. ComfyUI's
        #    own node execution is inference-mode-wrapped; we must match it.
        comfy.model_management.load_model_gpu(model)
        dev = comfy.model_management.get_torch_device()
        dtype = model.model.get_dtype()
        sam3 = model.model.diffusion_model
        frames_in = images[..., :3].movedim(-1, 1)  # [N,3,H,W]

        with torch.inference_mode():
            # 4. Build prompt -> run tracker
            init_masks = None
            text_prompts = None
            if points:
                # First-frame mask from points, then track via the memory tracker.
                sw = point_src_width or W
                sh = point_src_height or H
                lbls = labels or [1] * len(points)
                coords = [[p[0] / sw * 1008, p[1] / sh * 1008] for p in points]
                point_inputs = {
                    "point_coords": torch.tensor([coords], dtype=dtype, device=dev),
                    "point_labels": torch.tensor([lbls], dtype=torch.int32, device=dev),
                }
                frame0 = F.interpolate(frames_in[0:1].to(dev, dtype), size=(1008, 1008),
                                       mode="bilinear", align_corners=False)
                mask_logit = sam3.forward_segment(frame0, point_inputs=point_inputs)
                m = F.interpolate(mask_logit, size=(H, W), mode="bilinear", align_corners=False)
                init_masks = (m[0] > 0).to(device=dev, dtype=dtype).unsqueeze(1)  # [1,1,H,W]
            else:
                tokens = clip.tokenize(prompt or "object")
                cond = clip.encode_from_tokens_scheduled(tokens)
                from comfy_extras.nodes_sam3 import _extract_text_prompts
                text_prompts = [(emb, msk) for emb, msk, _ in
                                _extract_text_prompts(cond, dev, dtype)]

            result = sam3.forward_video(
                frames_in, init_masks, pbar=None, text_prompts=text_prompts,
                new_det_thresh=det_threshold, max_objects=max(0, int(max_objects)),
                detect_interval=1, target_device=dev, target_dtype=dtype)

            # 5. Packed masks -> per-frame grayscale PNG (union of all objects)
            packed = result.get("packed_masks")
            n_obj = 0 if packed is None else packed.shape[1]
            if n_obj == 0:
                empty = np.zeros((H, W), np.uint8)
                for i in range(N):
                    Image.fromarray(empty, mode="L").save(
                        os.path.join(masks_dir, f"{i:06d}.png"))
            else:
                union = packed[:, 0].clone()
                for i in range(1, n_obj):
                    union |= packed[:, i]
                masks = unpack_masks(union).unsqueeze(1).float()  # [N,1,Hm,Wm]
                masks = F.interpolate(masks, size=(H, W), mode="bilinear",
                                      align_corners=False)[:, 0]   # [N,H,W]
                masks = (masks > 0.5).to(torch.uint8).mul_(255).cpu().numpy()
                for i in range(N):
                    Image.fromarray(masks[i], mode="L").save(
                        os.path.join(masks_dir, f"{i:06d}.png"))

        # 6. Encode mask frames into a grayscale video
        mask_video_path = os.path.join(output_dir, "mask.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-framerate", str(fps),
             "-i", os.path.join(masks_dir, "%06d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
             mask_video_path],
            capture_output=True, check=True,
        )
        log.info("Native SAM 3.1 mask video created: %s", mask_video_path)
        return mask_video_path
    finally:
        import shutil
        for d in (frames_dir, masks_dir):
            try:
                shutil.rmtree(d)
            except OSError:
                pass


def mask_video(
    video_path: str,
    prompt: str,
    output_dir: Optional[str] = None,
    device: str = "gpu",
    max_objects: int = 5,
    det_threshold: float = 0.7,
    points: Optional[list] = None,
    labels: Optional[list] = None,
    point_src_width: int = 0,
    point_src_height: int = 0,
    version: str = DEFAULT_SAM_VERSION,
) -> str:
    """Generate a grayscale mask video for text-prompted objects.

    Extracts frames, runs SAM3 video predictor with text prompt,
    and outputs a grayscale mask video (white=target, black=background).

    Args:
        video_path: Path to input video.
        prompt: Text description of what to segment.
        output_dir: Directory for output files. Uses temp dir if None.
        device: "gpu" (default) or "cpu". CPU avoids VRAM OOM on long
            videos — SAM3 pre-loads all frames into device memory during
            init_state(), which can easily consume 5+ GB on 720p clips.
        max_objects: Maximum number of objects to track per frame (1-20).
            Lowest-confidence detections are dropped when exceeded.
        det_threshold: Minimum detection confidence for tracking new
            objects (0.0-1.0). Higher = fewer objects = less VRAM.
        points: Optional list of [x, y] pixel-space points on frame 0.
            When provided, these guide SAM3's segmentation (click-to-select).
        labels: Optional list of 1/0 labels for each point (positive/negative).
        point_src_width: Original image width the points were drawn on.
            If 0, uses the video frame width for normalization.
        point_src_height: Original image height the points were drawn on.
            If 0, uses the video frame height for normalization.

    Returns:
        Path to the generated grayscale mask video (MP4).
    """
    from PIL import Image

    _v = _normalize_version(version)

    # SAM 3.1 video: prefer ComfyUI's native in-process model (VRAM-managed,
    # no CUDA-context leak, no OOM). On any failure, fall through to the
    # legacy upstream-sam3 in-process path below.
    if _use_native_sam3_video(_v):
        try:
            return _mask_video_native_sam31(
                video_path, prompt, output_dir, device, max_objects,
                det_threshold, points, labels, point_src_width,
                point_src_height, version=_v)
        except Exception as e:
            log.warning("Native SAM 3.1 video path failed (%s); falling back "
                        "to upstream sam3", e, exc_info=True)

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_sam3_")

    frames_dir = os.path.join(output_dir, "frames")
    masks_dir = os.path.join(output_dir, "masks")
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(masks_dir, exist_ok=True)

    # 1. Extract ALL frames using ffmpeg
    log.info("Extracting frames from %s", video_path)
    subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-q:v", "2",
            os.path.join(frames_dir, "%06d.jpg"),
        ],
        capture_output=True,
        check=True,
    )

    all_frame_files = sorted(Path(frames_dir).glob("*.jpg"))
    if not all_frame_files:
        raise RuntimeError(f"No frames extracted from {video_path}")

    fps = _get_video_fps(video_path)
    total_frames = len(all_frame_files)

    # ── Auto frame stride ──────────────────────────────────────────
    # SAM3's Tracker accumulates ~10 MB of internal memory per frame.
    # On limited VRAM, processing all frames causes OOM.  We auto-
    # calculate a stride so SAM3 sees fewer frames, then duplicate
    # masks for the skipped in-between frames.
    import torch as _torch_stride
    _TRACKER_MB_PER_FRAME = 10  # empirical: ~100 MB per 10 frames
    # SAM 3.1 ships a combined detector+tracker (~7 GB) vs SAM 3's split
    # design (~3.5 GB). Working memory is also higher because the
    # multiplex tracker keeps more per-object state on-GPU.
    if _v == "sam3.1":
        _MODEL_BASE_MB = 7000
        _WORKING_MB = 4500
    else:
        _MODEL_BASE_MB = 3500       # SAM3 model weights ~3.5 GB
        _WORKING_MB = 3200          # working memory for one frame ~3.2 GB
    _SAFETY_MB = 500            # safety margin

    stride = 1
    if _torch_stride.cuda.is_available():
        _total_mb = _torch_stride.cuda.get_device_properties(0).total_memory / (1024**2)
        _usable_mb = _total_mb - _MODEL_BASE_MB - _WORKING_MB - _SAFETY_MB
        _max_frames = max(10, int(_usable_mb / _TRACKER_MB_PER_FRAME))
        if total_frames > _max_frames:
            stride = max(1, total_frames // _max_frames)
            log.info("Auto frame stride: %d (processing %d/%d frames to fit %.0f MB VRAM)",
                     stride, total_frames // stride, total_frames, _total_mb)

    # Build the list of frames SAM3 will process
    if stride > 1:
        # Create a sparse frames directory with only the strided frames
        sparse_dir = os.path.join(output_dir, "sparse_frames")
        os.makedirs(sparse_dir, exist_ok=True)
        import shutil
        strided_indices = list(range(0, total_frames, stride))
        # Always include the last frame for better tracking
        if strided_indices[-1] != total_frames - 1:
            strided_indices.append(total_frames - 1)
        for new_idx, orig_idx in enumerate(strided_indices):
            src = all_frame_files[orig_idx]
            dst = os.path.join(sparse_dir, f"{new_idx+1:06d}.jpg")
            shutil.copy2(str(src), dst)
        frame_files = sorted(Path(sparse_dir).glob("*.jpg"))
        log.info("Sparse frames: %d frames (stride=%d) in %s",
                 len(frame_files), stride, sparse_dir)
    else:
        frame_files = all_frame_files

    try:
        # 2. Run SAM3 video predictor with text prompt
        log.info("Running SAM3 video tracking on %d frames (prompt: '%s', "
                 "max_objects=%d, det_threshold=%.2f)",
                 len(frame_files), prompt, max_objects, det_threshold)
        # Diagnostic: track VRAM before any SAM3 work
        import torch
        if torch.cuda.is_available():
            _pre = torch.cuda.memory_allocated() / (1024**3)
            log.info("VRAM before load_video_model: %.2f GB", _pre)

        # Suppress SAM3's noisy 'setting max_num_objects' and 'hitting
        # max_num_objects' log lines.  These fire during build_sam3_video_model(),
        # init_state(), and on every frame when the object limit is active.
        # Must be set BEFORE load_video_model() to catch the build-time message.
        import logging as _logging
        _sam3_base_logger = _logging.getLogger("sam3.model.sam3_video_base")
        _sam3_inf_logger = _logging.getLogger("sam3.model.sam3_video_inference")
        _orig_level = _sam3_base_logger.level
        _orig_inf_level = _sam3_inf_logger.level
        _sam3_base_logger.setLevel(_logging.ERROR)
        _sam3_inf_logger.setLevel(_logging.ERROR)

        video_model = load_video_model(device=device, version=version)

        import torch
        from contextlib import nullcontext

        # Apply detection threshold — controls how confident SAM3 must be
        # before it starts tracking a new object. Higher = fewer objects.
        _UNSET = object()  # sentinel distinct from None
        orig_det_thresh = getattr(video_model, "new_det_thresh", _UNSET)
        video_model.new_det_thresh = det_threshold

        # ── Enforce object limit at detection time ──────────────────
        # SAM3 defaults to max_num_objects=10000 (effectively unlimited).
        # Without a hard cap the VG detector finds dozens of objects
        # (e.g. each individual balloon), and EVERY tracked object gets
        # its own set of Tracker memory banks.  Setting this to the
        # user's max_objects prevents SAM3 from ever allocating Tracker
        # memory for excess objects — the single biggest VRAM saving.
        orig_max_num_objects = getattr(video_model, "max_num_objects", _UNSET)
        effective_max_objects = 2 if points else max_objects
        video_model.max_num_objects = effective_max_objects
        log.info("SAM3 max_num_objects set to %d (was %s)", effective_max_objects,
                 orig_max_num_objects if orig_max_num_objects is not _UNSET else "unset")

        # ── Disable hotstart buffering ──────────────────────────────
        # Hotstart buffers ~15 frames on GPU before yielding the first
        # result.  Our inline offloading runs after each yield, so with
        # hotstart active the first 15 frames accumulate on GPU and OOM.
        # Disabling it lets frames yield immediately for offloading.
        orig_hotstart = getattr(video_model, "hotstart_delay", _UNSET)
        video_model.hotstart_delay = 0

        # Flush VRAM again right before inference (GPU mode only).
        # ComfyUI may have reloaded its models between load_video_model() and here.
        use_cpu = device.lower() == "cpu"
        if not use_cpu:
            _free_vram()
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3
                free = (torch.cuda.get_device_properties(0).total_memory
                        - torch.cuda.memory_allocated()) / 1024**3
                log.info("VRAM before SAM3 inference: %.2f GB allocated, %.2f GB free",
                         allocated, free)

        # SAM3's tracker expects a bfloat16 autocast context (entered permanently
        # in Sam3TrackerPredictor.__init__). ComfyUI's operations between runs
        # can pop this off the thread-local autocast stack. Re-enter it here
        # to ensure consistent dtype handling on every run.
        # Get original video dimensions (before with block so h/w are always defined)
        first_frame = np.array(Image.open(frame_files[0]))
        h, w = first_frame.shape[:2]

        autocast_ctx = (
            torch.autocast("cuda", dtype=torch.bfloat16)
            if (torch.cuda.is_available() and not use_cpu)
            else nullcontext()
        )
        inference_state = None  # declared here so finally block can always reach it

        with torch.inference_mode(), autocast_ctx, _suppress_tqdm(), _patch_postprocess_keyerror():
            # init_state loads all frames. Use compat shim because SAM 3
            # and SAM 3.1 production use different keyword names.
            try:
                inference_state = _init_state_compat(
                    video_model,
                    resource_path=frames_dir,
                    offload_video_to_cpu=True,
                )
            except TypeError:
                # Last-ditch fallback for very old SAM 3 revisions
                inference_state = _init_state_compat(
                    video_model,
                    resource_path=frames_dir,
                    offload_video_to_cpu=False,
                )
            log.info("SAM3 frames loaded (%d total)", len(frame_files))

            # ── Offload img_batch to CPU immediately ────────────────
            # init_state puts all 192 preprocessed frames on GPU as a
            # single tensor (~500 MB at 720p).  Offloading to a list of
            # CPU tensors frees that VRAM before any propagation begins.
            # SAM3 natively re-loads frames to GPU one at a time on access
            # (sam3_image.py:151: "img_batch might be fp16 and offloaded").
            _ib = inference_state.get("input_batch")
            if _ib is not None and torch.is_tensor(_ib.img_batch) and _ib.img_batch.is_cuda:
                _n_frames = _ib.img_batch.shape[0]
                _cpu_frames = [_ib.img_batch[i].cpu() for i in range(_n_frames)]

                class _LazyGPUFrames:
                    """List-like wrapper keeping frames on CPU until indexed."""
                    __slots__ = ("_frames",)
                    def __init__(self, frames):
                        self._frames = frames
                    def __len__(self):
                        return len(self._frames)
                    def __getitem__(self, idx):
                        return self._frames[idx]

                _ib.img_batch = _LazyGPUFrames(_cpu_frames)
                del _cpu_frames
                import gc as _gc_ib
                _gc_ib.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                log.info("Offloaded %d input frames to CPU (early)", _n_frames)

            # ── Set text prompt (always needed) ──────────────────────
            text_prompt = prompt or "object"
            _frame0_idx, _frame0_out = _add_text_prompt_compat(  # type: ignore[misc]
                video_model,
                inference_state,
                frame_idx=0,
                text=text_prompt,
            )
            log.info("Text VG: detected objects on frame 0 for '%s'",
                     text_prompt)

            # ── Point prompts ─────────────────────────────────────────
            # SAM3's point/interactivity refinement path requires
            # cached_frame_outputs to be pre-populated for every frame.
            # This means we MUST run a VG propagation pass first when
            # points are provided, then add the point prompts and let
            # Phase 3's propagation handle the combined output.
            has_points = bool(points and labels and w > 0 and h > 0)

            if has_points:
                # ── Pass 1: VG propagation to populate cache ──────────
                log.info("Running VG propagation to populate cache for point refinement...")
                for _vg_fidx, _vg_out in video_model.propagate_in_video(
                    inference_state
                ):
                    # Offload cached_frame_outputs to CPU
                    _offload_inference_state_to_cpu(inference_state)
                    # Evict feature_cache and previous_stages_out for processed frame
                    _fc = inference_state.get("feature_cache", {})
                    if _vg_fidx in _fc:
                        del _fc[_vg_fidx]
                    _pso = inference_state.get("previous_stages_out", {})
                    if isinstance(_pso, dict) and _vg_fidx in _pso:
                        _pso[_vg_fidx] = None
                    # Flush every frame
                    import gc as _gc
                    _gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                log.info("VG propagation complete — cache populated")

                # ── Full state reset between Phase 1 and Phase 2 ─────
                # reset_state() clears ALL GPU state (tracker memory banks,
                # feature_cache, per_frame_* dicts, previous_stages_out,
                # visual_prompt_embed, etc.).  We backup cached_frame_outputs
                # first (needed by Phase 3's _build_tracker_output) and
                # re-add the text prompt after reset.
                import gc as _gc

                # 1) Move cached_frame_outputs to CPU & copy to new dict
                _offload_inference_state_to_cpu(inference_state)
                _saved_cfo = dict(inference_state["cached_frame_outputs"])

                # 2) Full reset — frees all GPU state
                video_model.reset_state(inference_state)

                # 3) Flush GPU
                _gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

                _vram_after = torch.cuda.memory_allocated() / (1024**3)
                log.info("VRAM after full reset: %.2f GB", _vram_after)

                # 4) Re-add text prompt FIRST (add_prompt calls reset_state
                #    internally, which would clear cached_frame_outputs again)
                _add_text_prompt_compat(
                    video_model,
                    inference_state,
                    frame_idx=0,
                    text=text_prompt,
                )

                # 5) Now restore cached outputs — AFTER add_prompt's reset
                _gpu_dev = torch.device("cuda:0")

                class _LazyGPUDict(dict):
                    """Dict wrapper — moves tensor values to GPU on read."""
                    def _ensure_gpu(self, val):
                        if isinstance(val, dict):
                            for k in list(val.keys()):
                                t = val[k]
                                if torch.is_tensor(t) and not t.is_cuda:
                                    val[k] = t.to(_gpu_dev)
                        return val

                    def __getitem__(self, key):
                        return self._ensure_gpu(super().__getitem__(key))

                    def get(self, key, default=None):
                        try:
                            return self.__getitem__(key)
                        except KeyError:
                            return default

                inference_state["cached_frame_outputs"] = _LazyGPUDict(_saved_cfo)
                log.info("Cached outputs restored (%d entries on CPU, lazy GPU reload)",
                         len(_saved_cfo))

                # ── Add point prompts ─────────────────────────────────
                norm_w = point_src_width if point_src_width > 0 else w
                norm_h = point_src_height if point_src_height > 0 else h
                pos_pts = []
                neg_pts = []
                for pt, lbl in zip(points or [], labels or []):
                    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                        continue
                    try:
                        nx = max(0.0, min(1.0, float(pt[0]) / norm_w))
                        ny = max(0.0, min(1.0, float(pt[1]) / norm_h))
                        lbl_int = int(lbl)
                    except (TypeError, ValueError):
                        continue
                    if lbl_int == 1:
                        pos_pts.append((nx, ny))
                    else:
                        neg_pts.append((nx, ny))

                log.info("Point prompts: %d positive, %d negative clicks",
                         len(pos_pts), len(neg_pts))

                # Group all positive clicks into a single object
                grouped_pts: dict[int, dict] = {}
                if pos_pts:
                    grouped_pts[1] = {
                        "points": [[nx, ny] for (nx, ny) in pos_pts],
                        "labels": [1] * len(pos_pts),
                    }

                # Attach negative clicks to every group
                if neg_pts and grouped_pts:
                    neg_list = [[nx, ny] for (nx, ny) in neg_pts]
                    neg_labels = [0] * len(neg_pts)
                    for oid in grouped_pts:
                        grouped_pts[oid]["points"].extend(neg_list)
                        grouped_pts[oid]["labels"].extend(neg_labels)

                for oid, data in grouped_pts.items():
                    try:
                        _add_points_prompt_compat(
                            video_model,
                            inference_state,
                            frame_idx=0,
                            obj_id=oid,
                            points=data["points"],
                            labels=data["labels"],
                            rel_coordinates=True,
                        )
                    except Exception as _pt_err:
                        log.error("add_points_prompt failed for obj_id=%d: %s (%s)",
                                  oid, _pt_err, type(_pt_err).__name__)
                        import traceback
                        log.error("Traceback:\n%s", traceback.format_exc())
                        raise
                    n_pos = sum(1 for l in data["labels"] if l == 1)
                    n_neg = sum(1 for l in data["labels"] if l == 0)
                    log.info("  obj_id=%d: %d positive + %d negative point prompts",
                             oid, n_pos, n_neg)


            # 3. Propagate masks — drive the iterator ourselves so we control
            # progress reporting (no tqdm bar spam in ComfyUI's non-TTY console).
            log.info("Propagating SAM3 masks across %d frames", len(frame_files))
            mask_frames_saved = set()
            _total = len(frame_files)
            _report_every = max(1, _total // 10)  # log roughly every 10%
            try:
                for frame_idx, outputs in video_model.propagate_in_video(inference_state):
                    if outputs is None:
                        continue

                    binary_masks, out_probs = _extract_propagate_masks_compat(outputs)

                    if binary_masks is not None and len(binary_masks) > 0:
                        if isinstance(binary_masks, list):
                            binary_masks = np.array([m.cpu().numpy() if torch.is_tensor(m) else m
                                                     for m in binary_masks])
                        elif torch.is_tensor(binary_masks):
                            binary_masks = binary_masks.cpu().numpy()
                        if out_probs is not None:
                            if torch.is_tensor(out_probs):
                                out_probs = out_probs.cpu().numpy()
                            out_probs = np.ravel(out_probs)  # ensure 1-D

                        # --- Cap objects by confidence ---
                        n_objects = len(binary_masks)
                        if n_objects > max_objects:
                            if out_probs is not None and len(out_probs) >= n_objects:
                                # Keep only the top-N highest-confidence objects
                                top_indices = np.argsort(out_probs[:n_objects])[::-1][:max_objects]
                                binary_masks = binary_masks[top_indices]
                                log.debug(
                                    "Frame %d: capped %d objects → %d (kept probs: %s)",
                                    frame_idx, n_objects, max_objects,
                                    out_probs[top_indices].tolist(),
                                )
                            else:
                                # No probs or length mismatch — just take first N
                                binary_masks = binary_masks[:max_objects]
                                log.debug(
                                    "Frame %d: capped %d objects → %d (no probs)",
                                    frame_idx, n_objects, max_objects,
                                )

                        # Combine all object masks into one
                        combined = np.any(binary_masks, axis=0)
                        # Squeeze extra dims: (1, H, W) → (H, W) for mode="L"
                        while combined.ndim > 2:
                            combined = combined.squeeze(0)
                        mask = (combined > 0).astype(np.uint8) * 255
                    else:
                        mask = np.zeros((h, w), dtype=np.uint8)

                    mask_img = Image.fromarray(mask, mode="L")
                    if mask_img.size != (w, h):
                        mask_img = mask_img.resize((w, h), Image.NEAREST)  # type: ignore[attr-defined]
                    mask_img.save(os.path.join(masks_dir, f"{frame_idx:06d}.png"))
                    mask_frames_saved.add(frame_idx)

                    # ── Phase 3 cleanup: evict processed state ──────────
                    # Once a frame is saved to disk we no longer need its
                    # cached_frame_outputs, feature_cache, or previous_stages_out.
                    _cfo = inference_state.get("cached_frame_outputs", {})
                    if frame_idx in _cfo:
                        del _cfo[frame_idx]
                    _fc = inference_state.get("feature_cache", {})
                    if frame_idx in _fc:
                        del _fc[frame_idx]
                    _pso = inference_state.get("previous_stages_out", {})
                    if isinstance(_pso, dict) and frame_idx in _pso:
                        _pso[frame_idx] = None

                    # Move any remaining GPU tensors in cached_frame_outputs
                    # to CPU (covers the entry SAM3 just wrote for this frame).
                    _offload_inference_state_to_cpu(inference_state)

                    # Flush CUDA + gc every frame to keep VRAM bounded
                    import gc as _gc
                    _gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

                    # Diagnostic: track VRAM and cache sizes (every 10 frames)
                    if frame_idx % 10 == 0:
                        _alloc_gb = torch.cuda.memory_allocated() / (1024**3)
                        _cfo_diag = inference_state.get("cached_frame_outputs", {})
                        _cfo_count = len(_cfo_diag)
                        _gpu_tensors = 0
                        _sample_entry = None
                        for _fidx, _fval in _cfo_diag.items():
                            if _sample_entry is None:
                                _sample_entry = f"key={_fidx} type={type(_fval).__name__}"
                                if isinstance(_fval, dict):
                                    for _oid, _oval in _fval.items():
                                        _sample_entry += f" sub_key={_oid} sub_type={type(_oval).__name__}"
                                        if torch.is_tensor(_oval):
                                            _sample_entry += f" device={_oval.device} shape={list(_oval.shape)}"
                                        break
                                elif torch.is_tensor(_fval):
                                    _sample_entry += f" device={_fval.device} shape={list(_fval.shape)}"
                            if isinstance(_fval, dict):
                                for _oval in _fval.values():
                                    if torch.is_tensor(_oval) and _oval.is_cuda:
                                        _gpu_tensors += 1
                            elif torch.is_tensor(_fval) and _fval.is_cuda:
                                _gpu_tensors += 1
                        log.info(
                            "  [VRAM diag] frame=%d alloc=%.2f GB, "
                            "cfo=%d entries (%d GPU tensors), sample=[%s]",
                            frame_idx, _alloc_gb, _cfo_count, _gpu_tensors,
                            _sample_entry,
                        )

                    # Log progress at ~10% intervals
                    if (frame_idx + 1) % _report_every == 0 or frame_idx + 1 == _total:
                        log.info("SAM3 propagation: %d/%d frames (%.0f%%)",
                                 frame_idx + 1, _total,
                                 100.0 * (frame_idx + 1) / _total)
            finally:
                # Release the frame cache ALWAYS — even if propagation hits OOM
                # mid-way. Without this, each failed run leaves ~5 GB of frame
                # tensors stranded in VRAM, making every subsequent retry worse.
                if inference_state is not None:
                    try:
                        video_model.reset_state(inference_state)
                    except Exception:
                        pass
                    # Clear all inference state dicts to break circular refs
                    for _k in list(inference_state.keys()):
                        v = inference_state[_k]
                        if isinstance(v, dict):
                            v.clear()
                        elif isinstance(v, list):
                            v.clear()
                    inference_state = None
                # Clear SAM3's internal backbone/feature caches that accumulate
                # during propagation and survive across runs on the cached model.
                for _cache_attr in (
                    "_bb_feat_cache", "backbone_feature_cache",
                    "_features", "_bb_feat_sizes",
                ):
                    cache = getattr(video_model, _cache_attr, None)
                    if isinstance(cache, dict):
                        cache.clear()
                # Restore original detection threshold so subsequent runs
                # with different settings aren't affected.
                if orig_det_thresh is not _UNSET:
                    video_model.new_det_thresh = orig_det_thresh  # type: ignore[attr-defined]
                if orig_max_num_objects is not _UNSET:
                    video_model.max_num_objects = orig_max_num_objects  # type: ignore[attr-defined]
                if orig_hotstart is not _UNSET:
                    video_model.hotstart_delay = orig_hotstart  # type: ignore[attr-defined]

                # ── Cleanup ──────────────────────────────────────────
                # When running via subprocess, this process will exit right
                # after and all CUDA memory is reclaimed by the OS.  For the
                # in-process fallback path, do a basic cleanup.
                try:
                    video_model.to("cpu")
                except Exception:
                    pass
                del video_model
                try:
                    cleanup()
                except Exception:
                    pass
                import gc
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                # Restore SAM3 logger levels
                _sam3_base_logger.setLevel(_orig_level)
                _sam3_inf_logger.setLevel(_orig_inf_level)

        # ── Expand masks for strided frames ────────────────────────────
        if stride > 1:
            # SAM3 generated masks with sparse indices (0, 1, 2, ...).
            # Remap them to original frame positions, then fill gaps by
            # copying the nearest processed mask.
            import shutil as _shutil_masks

            # Rename sparse masks to their real frame indices
            sparse_mask_files = sorted(Path(masks_dir).glob("*.png"))
            _real_masks = {}  # orig_frame_idx -> mask path
            for sparse_idx, orig_idx in enumerate(strided_indices):
                sparse_path = os.path.join(masks_dir, f"{sparse_idx:06d}.png")
                real_path = os.path.join(masks_dir, f"real_{orig_idx:06d}.png")
                if os.path.exists(sparse_path):
                    os.rename(sparse_path, real_path)
                    _real_masks[orig_idx] = real_path

            # Now generate masks for ALL original frames
            _sorted_real = sorted(_real_masks.keys())
            for orig_idx in range(total_frames):
                final_path = os.path.join(masks_dir, f"{orig_idx:06d}.png")
                if orig_idx in _real_masks:
                    # Just rename the real mask to the final name
                    os.rename(_real_masks[orig_idx], final_path)
                else:
                    # Find nearest processed frame via binary search
                    import bisect
                    pos = bisect.bisect_left(_sorted_real, orig_idx)
                    if pos == 0:
                        nearest = _sorted_real[0]
                    elif pos >= len(_sorted_real):
                        nearest = _sorted_real[-1]
                    else:
                        before = _sorted_real[pos - 1]
                        after = _sorted_real[pos]
                        nearest = before if (orig_idx - before) <= (after - orig_idx) else after
                    # Copy the nearest mask
                    nearest_path = os.path.join(masks_dir, f"{nearest:06d}.png")
                    if os.path.exists(nearest_path):
                        _shutil_masks.copy2(nearest_path, final_path)
                    else:
                        # Fallback: empty mask
                        mask = np.zeros((h, w), dtype=np.uint8)
                        Image.fromarray(mask, mode="L").save(final_path)
            log.info("Expanded %d sparse masks → %d total frames (stride=%d)",
                     len(_real_masks), total_frames, stride)
            # Update frame_files to reflect all original frames for video assembly
            frame_files = all_frame_files
        else:
            # Fill any missing frames with empty masks
            for i in range(len(frame_files)):
                if i not in mask_frames_saved:
                    mask = np.zeros((h, w), dtype=np.uint8)
                    mask_img = Image.fromarray(mask, mode="L")
                    mask_img.save(os.path.join(masks_dir, f"{i:06d}.png"))

        log.info("Saved %d mask frames (%d with detections)",
                 total_frames if stride > 1 else len(frame_files),
                 len(mask_frames_saved))

        # 4. Encode mask frames into a video
        mask_video_path = os.path.join(output_dir, "mask.mp4")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", os.path.join(masks_dir, "%06d.png"),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                mask_video_path,
            ],
            capture_output=True,
            check=True,
        )

        log.info("Mask video created: %s", mask_video_path)
    finally:
        # Clean up intermediate frame/mask images (even on failure)
        import shutil
        _cleanup_dirs = [frames_dir, masks_dir]
        if stride > 1:
            _cleanup_dirs.append(os.path.join(output_dir, "sparse_frames"))
        for d in _cleanup_dirs:
            try:
                shutil.rmtree(d)
            except OSError:
                pass

    return mask_video_path


# ---------------------------------------------------------------------------
#  Mask overlay generation (SAM3-style colored contours)
# ---------------------------------------------------------------------------

# Default overlay palette — perceptually distinct colors (RGB, 0-255).
# Matches the style from SAM3's visualization_utils.draw_masks_to_frame().
_OVERLAY_PALETTE = np.array([
    [0, 212, 170],    # teal (primary — matches SAM3 repo screenshots)
    [220, 60, 180],   # magenta
    [255, 160, 40],   # orange
    [40, 180, 255],   # cyan
    [120, 220, 40],   # lime
    [160, 80, 255],   # violet
    [255, 100, 100],  # coral
    [50, 255, 200],   # mint
    [255, 200, 50],   # amber
    [255, 150, 200],  # pink
    [80, 100, 255],   # indigo
    [180, 255, 50],   # chartreuse
], dtype=np.uint8)

# OpenCV operates in BGR, so convert the RGB palette once
_OVERLAY_PALETTE_BGR = _OVERLAY_PALETTE[:, ::-1].copy()


def _draw_masks_to_frame(
    frame: np.ndarray,
    masks: np.ndarray,
    obj_ids: Optional[list] = None,
) -> np.ndarray:
    """Composite colored masks onto a frame with triple-contour outlines.

    Replicates the SAM3 repo's visual style:
    - Semi-transparent fill (75% original + 25% color)
    - Triple contour: white outer (7px) → black middle (5px) → color inner (3px)
    - No bounding boxes

    Args:
        frame: BGR uint8 image (H, W, 3).
        masks: Boolean masks (N, H, W) or list of (H, W) masks.
        obj_ids: Optional per-object IDs for consistent coloring.

    Returns:
        Composited BGR uint8 image (H, W, 3).
    """
    import cv2

    result = frame.copy()

    for i, mask in enumerate(masks):
        if mask.ndim > 2:
            mask = mask.squeeze()
        mask_u8 = (mask > 0).astype(np.uint8)
        if mask_u8.sum() == 0:
            continue

        color_idx = (obj_ids[i] if obj_ids else i) % len(_OVERLAY_PALETTE_BGR)
        color = _OVERLAY_PALETTE_BGR[color_idx]

        # Semi-transparent fill
        colored = np.where(mask_u8[..., None], color, result)
        result = cv2.addWeighted(result, 0.75, colored, 0.25, 0)

        # Triple contour: white → black → color
        contours, _ = cv2.findContours(
            mask_u8.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE,
        )
        cv2.drawContours(result, contours, -1, (255, 255, 255), 7)  # white outer
        cv2.drawContours(result, contours, -1, (0, 0, 0), 5)        # black middle
        cv2.drawContours(result, contours, -1, color.tolist(), 3)    # color inner

    return result


def generate_mask_overlay(
    video_path: str,
    mask_video_path: str,
    output_path: Optional[str] = None,
) -> str:
    """Composite colored mask overlay onto the original video.

    Produces a preview video with SAM3-style colored regions + contour
    outlines so users can verify what was detected before final render.

    Args:
        video_path: Path to the original video.
        mask_video_path: Path to the grayscale mask video (white=target).
        output_path: Where to write the overlay video. Auto-generated if None.

    Returns:
        Path to the overlay video (MP4).
    """
    import cv2

    if output_path is None:
        p = Path(mask_video_path)
        output_path = str(p.with_name(p.stem + "_overlay.mp4"))

    cap_orig = cv2.VideoCapture(video_path)
    cap_mask = cv2.VideoCapture(mask_video_path)
    writer = None
    tmp_path = output_path + ".tmp.mp4"

    try:
        if not cap_orig.isOpened():
            raise RuntimeError(f"Cannot open original video: {video_path}")
        if not cap_mask.isOpened():
            raise RuntimeError(f"Cannot open mask video: {mask_video_path}")

        fps = cap_orig.get(cv2.CAP_PROP_FPS) or 30.0
        w = int(cap_orig.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap_orig.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Write to a temp file, then re-encode with ffmpeg for compatibility
        fourcc = cv2.VideoWriter.fourcc(*"mp4v")
        writer = cv2.VideoWriter(tmp_path, fourcc, fps, (w, h))

        frame_count = 0
        while True:
            ret_o, frame_orig = cap_orig.read()
            ret_m, frame_mask = cap_mask.read()
            if not ret_o or not ret_m:
                break

            # Convert mask to grayscale → binary
            if frame_mask.ndim == 3:
                gray = cv2.cvtColor(frame_mask, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame_mask

            # Resize mask to match original if needed
            if gray.shape[:2] != frame_orig.shape[:2]:
                gray = cv2.resize(gray, (w, h), interpolation=cv2.INTER_NEAREST)

            # Label connected components as separate objects
            _, labels_map = cv2.connectedComponents((gray > 127).astype(np.uint8))
            n_objects = labels_map.max()

            if n_objects > 0:
                masks = []
                obj_ids = []
                for oid in range(1, n_objects + 1):
                    masks.append((labels_map == oid).astype(np.uint8))
                    obj_ids.append(oid - 1)

                overlay = _draw_masks_to_frame(
                    frame_orig, np.array(masks), obj_ids,
                )
            else:
                overlay = frame_orig

            writer.write(overlay)
            frame_count += 1

    finally:
        if writer is not None:
            writer.release()
        cap_orig.release()
        cap_mask.release()

    # Re-encode for broad compatibility
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", tmp_path,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            output_path,
        ],
        capture_output=True,
        check=True,
    )
    try:
        os.unlink(tmp_path)
    except OSError:
        pass

    log.info("Mask overlay video created: %s (%d frames)", output_path, frame_count)
    return output_path


# ---------------------------------------------------------------------------
#  Cleanup
# ---------------------------------------------------------------------------

def cleanup() -> None:
    """Free GPU memory and clear all cached models across versions."""
    _image_models.clear()
    _image_processors.clear()
    _image_model_devices.clear()
    _video_models.clear()
    _video_model_devices.clear()
    # Native ComfyUI SAM 3.1 model+clip cache. These are ModelPatchers; ComfyUI
    # manages their VRAM, but drop our references so they can be collected.
    _native_models.clear()

    import gc
    gc.collect()

    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    log.info("SAM models unloaded and GPU memory freed (all versions)")


def mask_video_subprocess(
    video_path: str,
    prompt: str,
    output_dir: Optional[str] = None,
    device: str = "gpu",
    max_objects: int = 5,
    det_threshold: float = 0.7,
    points: Optional[list] = None,
    labels: Optional[list] = None,
    point_src_width: int = 0,
    point_src_height: int = 0,
    version: str = DEFAULT_SAM_VERSION,
) -> str:
    """Run mask_video() in a subprocess to avoid CUDA memory leaks.

    SAM3 leaks ~1.5 GB of CUDA driver context memory per run that
    cannot be freed within the process (confirmed invisible to Python gc,
    nn.Parameter storage, register_buffer, and all PyTorch cleanup APIs).
    Running in a subprocess ensures all CUDA state is reclaimed by the OS
    when the child process exits.

    Same interface as mask_video() — all args are JSON-serialized to the
    child process via stdin, and the mask video path is returned via stdout.
    Falls back to in-process mask_video() if the subprocess fails.
    """
    import json
    import sys

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_sam3_")

    _v = _normalize_version(version)

    # SAM 3.1 video: run ComfyUI's native model in-process (VRAM-managed, no
    # CUDA-context leak — so no subprocess needed) when enabled. On any
    # failure, fall through to the legacy subprocess + upstream-sam3 path.
    if _use_native_sam3_video(_v):
        try:
            return _mask_video_native_sam31(
                video_path, prompt, output_dir, device, max_objects,
                det_threshold, points, labels, point_src_width,
                point_src_height, version=_v)
        except Exception as e:
            log.warning("Native SAM 3.1 video path failed (%s); falling back "
                        "to subprocess + upstream sam3", e, exc_info=True)

    args_dict = {
        "video_path": video_path,
        "prompt": prompt,
        "output_dir": output_dir,
        "device": device,
        "max_objects": max_objects,
        "det_threshold": det_threshold,
        "points": points,
        "labels": labels,
        "point_src_width": point_src_width,
        "point_src_height": point_src_height,
        "version": _v,
    }

    # Inline script for the child process:
    # - Reads JSON args from stdin
    # - Loads sam3_masker.py directly by file path (bypasses core/__init__.py
    #   which imports ComfyUI-dependent modules that hang without the server)
    # - Calls mask_video()
    # - Prints the result path as "RESULT:<path>" to stdout
    child_script = """
import sys, json, importlib.util, logging
# Route INFO logs to stderr so the parent's _stream_stderr can surface SAM3
# progress (model load, frames loaded, per-frame propagation, offload). Without
# this, Python's last-resort handler only emits WARNING+, leaving the parent
# blind to whether the run is progressing or genuinely hung.
logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
args = json.loads(sys.stdin.read())
mod_path = args.pop("_module_path")
spec = importlib.util.spec_from_file_location("sam3_masker", mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.mask_video(**args)
print("RESULT:" + result, flush=True)
"""

    try:
        # Determine the project root (parent of 'core/')
        _this_dir = os.path.dirname(os.path.abspath(__file__))
        _project_root = os.path.dirname(_this_dir)
        _module_path = os.path.abspath(__file__)

        # Pass _module_path so the child can load this file directly
        args_dict["_module_path"] = _module_path

        env = os.environ.copy()
        # Keep parent's PYTHONPATH so SAM3, torch, etc. can be found
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = _project_root + (
            os.pathsep + existing_pp if existing_pp else ""
        )
        # Override the CUDA allocator for the child. ComfyUI runs the
        # cudaMallocAsync backend, which (a) the child inherits via the env
        # and (b) retries on allocation failure — turning a sam3.1 multiplex
        # OOM during VG propagation into a multi-minute hang instead of a
        # fast error. Force the native caching allocator with
        # expandable_segments: it serves allocations from one growable
        # segment, reclaiming the fragmentation overhead (~1 GB on a 12 GB
        # card — often enough to clear the borderline OOM) and lets any
        # genuine OOM surface immediately. expandable_segments is
        # incompatible with cudaMallocAsync, so we set it exclusively.
        env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        # Pass model directories for both versions so the child doesn't
        # fall back to the extension's own models/ dir (folder_paths is
        # unavailable outside ComfyUI server).
        env["FFMPEGA_SAM3_MODEL_DIR"] = str(_get_model_dir("sam3"))
        env["FFMPEGA_SAM3_1_MODEL_DIR"] = str(_get_model_dir("sam3.1"))
        env["FFMPEGA_SAM_VERSION"] = _v
        # This subprocess IS the fallback for the native path, so force the
        # child's mask_video() to use the upstream sam3 predictor (never
        # re-attempt native in-process inside the child).
        env["FFMPEGA_SAM3_NATIVE"] = "0"

        log.info("SAM3 subprocess: starting (device=%s, version=%s, frames=%s)",
                 device, _v, video_path)

        # Force unbuffered output so stderr lines arrive in real-time
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", child_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=_project_root,
            env=env,
        )

        # Send args via stdin then close it
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(args_dict))
        proc.stdin.close()

        # Stream stderr in real-time (SAM3 progress, VRAM diag, etc.)
        import threading

        def _stream_stderr():
            try:
                assert proc.stderr is not None
                for line in proc.stderr:
                    line = line.rstrip()
                    if not line:
                        continue
                    # Filter out noisy pkg_resources deprecation warnings
                    if "pkg_resources" in line or "slated for removal" in line:
                        continue
                    log.info("[SAM3] %s", line)
            except ValueError:
                pass  # stderr closed
            finally:
                try:
                    if proc.stderr is not None:
                        proc.stderr.close()
                except OSError:
                    pass

        stderr_thread = threading.Thread(target=_stream_stderr, daemon=True)
        stderr_thread.start()

        # Wait for process to finish (with timeout) first so we don't block
        # forever reading stdout if the process hangs.
        try:
            proc.wait(timeout=_SAM3_SUBPROCESS_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError(
                f"SAM3 subprocess timed out after "
                f"{_SAM3_SUBPROCESS_TIMEOUT / 60:g} minutes"
            )

        # Read stdout (contains RESULT: line) — don't use communicate()
        # because we already closed stdin and are reading stderr in a thread.
        try:
            assert proc.stdout is not None
            stdout_data = proc.stdout.read()
        finally:
            if proc.stdout is not None:
                proc.stdout.close()

        stderr_thread.join(timeout=5)

        if proc.returncode != 0:
            raise RuntimeError(
                f"SAM3 subprocess exited with code {proc.returncode}"
            )

        # Parse result path from stdout
        mask_path = None
        for line in (stdout_data or "").strip().splitlines():
            if line.startswith("RESULT:"):
                mask_path = line[len("RESULT:"):]
                break

        if mask_path is None:
            raise RuntimeError(
                "SAM3 subprocess did not return a result path"
            )

        if not os.path.isfile(mask_path):
            raise RuntimeError(
                f"SAM3 subprocess returned non-existent path: {mask_path}"
            )

        log.info("SAM3 subprocess: completed — mask at %s", mask_path)
        return mask_path

    except Exception as e:
        # Do NOT fall back to in-process execution — that would re-introduce
        # the 1.49 GB CUDA leak we're trying to avoid. Let the error
        # propagate to the caller (visual.py) which has its own fallback.
        log.error("SAM3 subprocess failed: %s", e)
        raise
