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
    {
        "file": "model/sam3_video_base.py",
        "old": "from sam3.train.masks_ops import rle_encode",
        "new": (
            "try:\n"
            "    from sam3.train.masks_ops import rle_encode\n"
            "except ImportError:\n"
            "    rle_encode = None"
        ),
        # Don't patch if already wrapped in try/except
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

        # Skip if a guard string is present (already patched differently)
        guard = patch.get("guard_absent")
        if guard and guard in content:
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
#  Cached model instances (lazy-loaded)
# ---------------------------------------------------------------------------

_image_model = None
_image_processor = None
_image_model_device = None  # last device the image model was loaded on
_video_model = None
_video_model_device = None  # last device the video model was loaded on


# ---------------------------------------------------------------------------
#  Model directory & checkpoint discovery
# ---------------------------------------------------------------------------

_HF_REPO = "AEmotionStudio/sam3"
_SAFETENSORS_NAME = "sam3.safetensors"
_PT_NAME = "sam3.pt"


def _get_model_dir() -> Path:
    """Return the SAM3 model directory, creating it if needed.

    Checks (in order):
    1. FFMPEGA_SAM3_MODEL_DIR env var (set by subprocess wrapper)
    2. ComfyUI/models/SAM3/ (standard ComfyUI convention)
    3. Extension's own models/SAM3/ (fallback for testing)
    """
    env_dir = os.environ.get("FFMPEGA_SAM3_MODEL_DIR")
    if env_dir:
        sam3_dir = Path(env_dir)
    else:
        try:
            import folder_paths
            sam3_dir = Path(folder_paths.models_dir) / "SAM3"
        except (ImportError, AttributeError):
            # Running outside ComfyUI (tests, standalone)
            sam3_dir = Path(__file__).parent.parent / "models" / "SAM3"

    sam3_dir.mkdir(parents=True, exist_ok=True)
    return sam3_dir


def _find_checkpoint() -> str:
    """Find or download the SAM3 checkpoint.

    Priority:
    1. Local .safetensors in ComfyUI/models/SAM3/ (safe format)
    2. Local .pt in ComfyUI/models/SAM3/
    3. Auto-download sam3.safetensors from HuggingFace

    Returns:
        Path to the checkpoint file.
    """
    model_dir = _get_model_dir()

    # Prefer .safetensors (safe format)
    local_safetensors = model_dir / _SAFETENSORS_NAME
    if local_safetensors.is_file():
        log.info("Found local SAM3 checkpoint: %s", local_safetensors)
        return str(local_safetensors)

    # Fallback to .pt
    local_pt = model_dir / _PT_NAME
    if local_pt.is_file():
        log.info("Found local SAM3 checkpoint: %s", local_pt)
        return str(local_pt)

    # Auto-download from HuggingFace
    # Guard: raise if downloads are disabled
    try:
        from . import model_manager
    except ImportError:
        from core import model_manager  # type: ignore
    model_manager.require_downloads_allowed("sam3")

    log.info(
        "SAM3 checkpoint not found locally. "
        "Downloading from %s...", _HF_REPO
    )
    try:
        from huggingface_hub import hf_hub_download

        # Try safetensors first (safe format)
        try:
            path = hf_hub_download(
                repo_id=_HF_REPO,
                filename=_SAFETENSORS_NAME,
                local_dir=str(model_dir),
            )
            log.info("Downloaded SAM3 checkpoint: %s", path)
            return path
        except Exception:
            pass

        # Fall back to .pt
        path = hf_hub_download(
            repo_id=_HF_REPO,
            filename=_PT_NAME,
            local_dir=str(model_dir),
        )
        log.info("Downloaded SAM3 checkpoint: %s", path)
        return path

    except ImportError:
        raise ImportError(
            "huggingface_hub is required to auto-download SAM3. "
            "Install with: pip install huggingface_hub"
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to download SAM3 checkpoint from {_HF_REPO}: {e}. "
            f"You can manually place the checkpoint in {model_dir}/"
        )


def _load_safetensors(model, checkpoint_path: str) -> None:
    """Load a safetensors checkpoint into a SAM3 model."""
    from safetensors.torch import load_file

    ckpt = load_file(checkpoint_path)

    # SAM3's _load_checkpoint extracts detector keys
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

    missing_keys, unexpected_keys = model.load_state_dict(sam3_image_ckpt, strict=False)
    if missing_keys:
        log.debug("SAM3 loaded with missing keys: %s", missing_keys[:5])
    # Guard: if nearly all keys are missing, the checkpoint format is wrong
    if len(missing_keys) > len(sam3_image_ckpt) * 0.5:
        log.warning(
            "SAM3 image checkpoint has %d/%d missing keys — likely wrong "
            "format (e.g. HuggingFace Transformers vs original .pt). "
            "Reconvert from .pt with: safetensors.torch.save_file(torch.load('sam3.pt'), 'sam3.safetensors')",
            len(missing_keys), len(sam3_image_ckpt),
        )


def _load_safetensors_video(model, checkpoint_path: str) -> None:
    """Load a safetensors checkpoint into a SAM3 video model.

    The video model loads all keys directly (no detector/tracker split),
    matching build_sam3_video_model's internal loading.
    """
    from safetensors.torch import load_file

    ckpt = load_file(checkpoint_path)

    # Video model's builder loads "model" sub-dict if present,
    # otherwise loads all keys directly
    if "model" in ckpt and isinstance(ckpt["model"], dict):
        ckpt = ckpt["model"]

    missing_keys, unexpected_keys = model.load_state_dict(ckpt, strict=False)
    if missing_keys:
        log.debug("SAM3 video model missing keys: %s", missing_keys[:5])
    if unexpected_keys:
        log.debug("SAM3 video model unexpected keys: %s", unexpected_keys[:5])
    # Guard: if nearly all keys are missing, the checkpoint format is wrong
    if len(missing_keys) > len(ckpt) * 0.5:
        log.warning(
            "SAM3 video checkpoint has %d/%d missing keys — likely wrong "
            "format (e.g. HuggingFace Transformers vs original .pt). "
            "Reconvert from .pt with: safetensors.torch.save_file(torch.load('sam3.pt'), 'sam3.safetensors')",
            len(missing_keys), len(ckpt),
        )


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

def _free_vram() -> None:
    """Free ComfyUI VRAM before loading SAM3."""
    try:
        import comfy.model_management
        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()
        log.info("Freed ComfyUI VRAM for SAM3 loading")
    except ImportError:
        pass

    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


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

def load_image_model(device: str = "gpu"):
    """Load and cache the SAM3 image model + processor.

    Args:
        device: "gpu" (default) or "cpu". CPU avoids VRAM pressure but is slower.

    Returns:
        Tuple of (model, Sam3Processor).

    Raises:
        ImportError: If SAM3 is not installed.
    """
    global _image_model, _image_processor, _image_model_device

    use_cpu = device.lower() == "cpu"
    target_device = "cpu" if use_cpu else "cuda"
    # Guard: fall back to CPU if CUDA was requested but isn't available
    if target_device == "cuda":
        import torch as _torch_check
        if not _torch_check.cuda.is_available():
            log.warning("CUDA unavailable, loading SAM3 image model on CPU")
            target_device = "cpu"
            use_cpu = True

    if _image_model is not None and _image_processor is not None:
        # If device changed, move model to new device
        if _image_model_device != target_device:
            import torch
            actual_device = target_device
            if actual_device == "cuda" and not torch.cuda.is_available():
                log.warning("CUDA unavailable, keeping SAM3 image model on CPU")
                actual_device = "cpu"
            _image_model.to(torch.device(actual_device))
            _image_model_device = actual_device
        return _image_model, _image_processor

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
        log.info("SAM3 image model: CPU mode (avoids VRAM pressure, slower)")
    else:
        _free_vram()

    checkpoint_path = _find_checkpoint()

    # Determine loading strategy based on file extension
    if checkpoint_path.endswith(".safetensors"):
        log.info("Loading SAM3 image model from safetensors: %s", checkpoint_path)
        model = build_sam3_image_model(
            checkpoint_path=None,
            load_from_HF=False,
        )
        _load_safetensors(model, checkpoint_path)
    else:
        # .pt file — monkey-patch torch.load for weights_only compat
        log.info("Loading SAM3 image model from .pt: %s", checkpoint_path)
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
            )
        finally:
            torch.load = _orig_load

    # Note: SAM3 handles its own dtype management (bf16 autocast).
    # Do NOT call model.float() — it breaks mixed-precision inference.

    import torch
    if use_cpu:
        model.to(torch.device("cpu"))

    _image_model = model
    _image_model_device = target_device
    _image_processor = Sam3Processor(model)

    log.info("SAM3 image model loaded successfully on %s", target_device.upper())
    return _image_model, _image_processor


def load_video_model(device: str = "gpu"):
    """Load and cache the SAM3 video model.

    Args:
        device: "gpu" (default) or "cpu". CPU mode avoids VRAM pressure by
            moving the model off-GPU before frame loading. Slower but necessary
            when VRAM is insufficient (~12 GB needed for long videos on GPU).

    Returns:
        SAM3 video predictor instance.

    Raises:
        ImportError: If SAM3 is not installed.
    """
    global _video_model, _video_model_device

    use_cpu = device.lower() == "cpu"
    target_device = "cpu" if use_cpu else "cuda"
    # Guard: fall back to CPU if CUDA was requested but isn't available
    if target_device == "cuda":
        import torch as _torch_check
        if not _torch_check.cuda.is_available():
            log.warning("CUDA unavailable, loading SAM3 video model on CPU")
            target_device = "cpu"
            use_cpu = True

    if _video_model is not None:
        # If device changed, move model to new device
        if _video_model_device != target_device:
            import torch
            actual_device = target_device
            if actual_device == "cuda" and not torch.cuda.is_available():
                log.warning("CUDA unavailable, keeping SAM3 video model on CPU")
                actual_device = "cpu"
            _video_model.to(torch.device(actual_device))
            _video_model_device = actual_device
        return _video_model

    _patch_sam3_imports()

    try:
        from sam3.model_builder import build_sam3_video_model
    except ImportError:
        raise ImportError(
            "SAM3 is not installed. Install with: "
            "pip install --no-deps git+https://github.com/facebookresearch/sam3.git"
        )

    if use_cpu:
        log.info("SAM3 video model: CPU mode (avoids VRAM frame-loading OOM, slower)")
    else:
        _free_vram()

    checkpoint_path = _find_checkpoint()
    log.info("Loading SAM3 video model from: %s", checkpoint_path)

    import torch

    if checkpoint_path.endswith(".safetensors"):
        # build_sam3_video_model uses torch.load internally which can't
        # handle safetensors. Build without checkpoint, then load manually.
        if use_cpu:
            # Temporarily hide CUDA so build_sam3_video_model constructs the
            # model on CPU. Without this, it calls torch.device('cuda') internally
            # and OOMs before we even get to .to(cpu).
            _orig_cuda_available = torch.cuda.is_available
            torch.cuda.is_available = lambda: False
            try:
                model = build_sam3_video_model(
                    checkpoint_path=None,
                    load_from_HF=False,
                )
            finally:
                torch.cuda.is_available = _orig_cuda_available
        else:
            model = build_sam3_video_model(
                checkpoint_path=None,
                load_from_HF=False,
            )
        _load_safetensors_video(model, checkpoint_path)
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
            model = build_sam3_video_model(
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

    _video_model = model
    _video_model_device = target_device
    log.info("SAM3 video model loaded successfully on %s", target_device.upper())
    return _video_model


# ---------------------------------------------------------------------------
#  Image masking with text prompts
# ---------------------------------------------------------------------------

def mask_image_with_text(
    image_path: str,
    prompt: str,
    device: str = "gpu",
) -> np.ndarray:
    """Generate masks for objects described by a text prompt.

    Args:
        image_path: Path to the image file.
        prompt: Text description of what to segment (e.g. "the dog").
        device: "gpu" (default) or "cpu".

    Returns:
        Binary mask as numpy array (H, W) where 255=masked, 0=unmasked.
    """
    from PIL import Image

    model, processor = load_image_model(device=device)
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
                _mod.tqdm = _make_silent_tqdm(_orig)
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

        video_model = load_video_model(device=device)

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
        video_model.max_num_objects = max_objects
        log.info("SAM3 max_num_objects set to %d (was %s)", max_objects,
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

        # Suppress SAM3's noisy 'hitting max_num_objects' warnings.
        # These fire on every frame when the object limit is active,
        # producing hundreds of log lines.
        import logging as _logging
        _sam3_base_logger = _logging.getLogger("sam3.model.sam3_video_base")
        _sam3_inf_logger = _logging.getLogger("sam3.model.sam3_video_inference")
        _orig_level = _sam3_base_logger.level
        _orig_inf_level = _sam3_inf_logger.level
        _sam3_base_logger.setLevel(_logging.ERROR)
        _sam3_inf_logger.setLevel(_logging.ERROR)

        with torch.inference_mode(), autocast_ctx, _suppress_tqdm(), _patch_postprocess_keyerror():
            # init_state loads all frames
            try:
                inference_state = video_model.init_state(
                    resource_path=frames_dir,
                    video_loader_type="cv2",
                    offload_video_to_cpu=True,
                )
            except TypeError:
                # Older SAM3 versions may not support offload_video_to_cpu
                inference_state = video_model.init_state(
                    resource_path=frames_dir,
                    video_loader_type="cv2",
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
            _frame0_idx, _frame0_out = video_model.add_prompt(
                inference_state,
                frame_idx=0,
                text_str=text_prompt,
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
                video_model.add_prompt(
                    inference_state,
                    frame_idx=0,
                    text_str=text_prompt,
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
                for pt, lbl in zip(points, labels):
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
                        video_model.add_prompt(
                            inference_state,
                            frame_idx=0,
                            points=data["points"],
                            point_labels=data["labels"],
                            obj_id=oid,
                            rel_coordinates=True,
                        )
                    except Exception as _pt_err:
                        log.error("add_prompt(points) failed for obj_id=%d: %s (%s)",
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

                    binary_masks = outputs.get("out_binary_masks")
                    out_probs = outputs.get("out_probs")

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
                        mask_img = mask_img.resize((w, h), Image.NEAREST)
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
                    video_model.new_det_thresh = orig_det_thresh
                if orig_max_num_objects is not _UNSET:
                    video_model.max_num_objects = orig_max_num_objects
                if orig_hotstart is not _UNSET:
                    video_model.hotstart_delay = orig_hotstart

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
    [0, 200, 200],    # teal/cyan (primary — matches SAM3 repo screenshots)
    [255, 100, 100],  # coral red
    [100, 255, 100],  # lime green
    [100, 100, 255],  # periwinkle blue
    [255, 200, 50],   # amber
    [200, 100, 255],  # violet
    [255, 150, 200],  # pink
    [50, 255, 200],   # mint
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
    """Free GPU memory and clear cached models."""
    global _image_model, _image_processor, _video_model, _video_model_device

    _image_model = None
    _image_processor = None
    _video_model = None
    _video_model_device = None

    import gc
    gc.collect()

    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    log.info("SAM3 models unloaded and GPU memory freed")


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
    }

    # Inline script for the child process:
    # - Reads JSON args from stdin
    # - Loads sam3_masker.py directly by file path (bypasses core/__init__.py
    #   which imports ComfyUI-dependent modules that hang without the server)
    # - Calls mask_video()
    # - Prints the result path as "RESULT:<path>" to stdout
    child_script = """
import sys, json, importlib.util
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
        # Pass the model directory so the child doesn't fall back to
        # the extension's own models/ dir (folder_paths is unavailable
        # outside ComfyUI server).
        env["FFMPEGA_SAM3_MODEL_DIR"] = str(_get_model_dir())

        log.info("SAM3 subprocess: starting (device=%s, frames=%s)",
                 device, video_path)

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
        proc.stdin.write(json.dumps(args_dict))
        proc.stdin.close()

        # Stream stderr in real-time (SAM3 progress, VRAM diag, etc.)
        import threading

        def _stream_stderr():
            try:
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
                    proc.stderr.close()
                except OSError:
                    pass

        stderr_thread = threading.Thread(target=_stream_stderr, daemon=True)
        stderr_thread.start()

        # Wait for process to finish (with timeout) first so we don't block
        # forever reading stdout if the process hangs.
        try:
            proc.wait(timeout=900)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError("SAM3 subprocess timed out after 15 minutes")

        # Read stdout (contains RESULT: line) — don't use communicate()
        # because we already closed stdin and are reading stderr in a thread.
        try:
            stdout_data = proc.stdout.read()
        finally:
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
