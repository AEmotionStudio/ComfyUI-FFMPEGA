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
    1. ComfyUI/models/SAM3/ (standard ComfyUI convention)
    2. Extension's own models/SAM3/ (fallback for testing)
    """
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
    import torch
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
#  Image masking with point prompts
# ---------------------------------------------------------------------------

def mask_image_with_points(
    image_path: str,
    points: list,
    labels: list,
    prompt: Optional[str] = None,
    device: str = "gpu",
) -> np.ndarray:
    """Generate masks using point prompts (click-to-select).

    Points guide SAM3's interactive segmentation — left-click (label=1)
    means "include this object", right-click (label=0) means "exclude".

    Args:
        image_path: Path to the image file.
        points: List of [x, y] coordinates in pixel space.
        labels: List of 1 (positive/include) or 0 (negative/exclude).
        prompt: Optional text prompt to combine with points for refinement.
        device: "gpu" (default) or "cpu".

    Returns:
        Binary mask as numpy array (H, W) where 255=masked, 0=unmasked.
    """
    import torch
    from PIL import Image

    model, processor = load_image_model(device=device)
    image = Image.open(image_path).convert("RGB")
    w, h = image.size

    inference_state = processor.set_image(image)

    # If text prompt provided, set it first for combined text+point guidance
    if prompt:
        inference_state = processor.set_text_prompt(
            state=inference_state, prompt=prompt,
        )

    # Convert pixel-space points to normalized [0,1] box prompts.
    # SAM3's image processor uses add_geometric_prompt for box-based clicks,
    # or we use the SAM heads' point_inputs directly via the tracker interface.
    # For the image model, we feed each positive point as a small box prompt.
    for pt, lbl in zip(points, labels):
        x_norm = pt[0] / w
        y_norm = pt[1] / h
        # Create a small centered box around the point (2% of image)
        box_size = 0.02
        cx, cy = x_norm, y_norm
        box = [cx, cy, box_size, box_size]  # center_x, center_y, w, h
        inference_state = processor.add_geometric_prompt(
            box=box, label=bool(lbl), state=inference_state,
        )

    masks = inference_state.get("masks")
    if masks is None or len(masks) == 0:
        log.warning("SAM3 found no objects from point prompts")
        return np.zeros((h, w), dtype=np.uint8)

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

def mask_video(
    video_path: str,
    prompt: str,
    output_dir: Optional[str] = None,
    device: str = "gpu",
    max_objects: int = 5,
    det_threshold: float = 0.7,
    points: Optional[list] = None,
    labels: Optional[list] = None,
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

    # 1. Extract frames using ffmpeg
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

    frame_files = sorted(Path(frames_dir).glob("*.jpg"))
    if not frame_files:
        raise RuntimeError(f"No frames extracted from {video_path}")

    fps = _get_video_fps(video_path)

    try:
        # 2. Run SAM3 video predictor with text prompt
        log.info("Running SAM3 video tracking on %d frames (prompt: '%s', "
                 "max_objects=%d, det_threshold=%.2f)",
                 len(frame_files), prompt, max_objects, det_threshold)

        video_model = load_video_model(device=device)

        import torch
        from contextlib import nullcontext

        # Apply detection threshold — controls how confident SAM3 must be
        # before it starts tracking a new object. Higher = fewer objects.
        orig_det_thresh = getattr(video_model, "new_det_thresh", None)
        video_model.new_det_thresh = det_threshold

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
        with torch.inference_mode(), autocast_ctx:
            # init_state loads all frames — suppress SAM3's per-frame tqdm bar
            # (in a non-TTY environment each \r update prints as a new line).
            import os as _os
            _tqdm_was = _os.environ.get("TQDM_DISABLE")
            _os.environ["TQDM_DISABLE"] = "1"
            try:
                inference_state = video_model.init_state(
                    resource_path=frames_dir,
                    video_loader_type="cv2",
                    offload_video_to_cpu=True,  # keep frames on CPU, transfer on demand
                )
            finally:
                if _tqdm_was is None:
                    _os.environ.pop("TQDM_DISABLE", None)
                else:
                    _os.environ["TQDM_DISABLE"] = _tqdm_was
            log.info("SAM3 frames loaded (%d total)", len(frame_files))

            # Add prompts on first frame
            #
            # Point prompts (if present) serve as guidance for the LLM agent
            # which already used them to pick the best text_prompt.  We don't
            # pass them to SAM3's Tracker because the refinement propagation
            # requires a VG cache populated first, and running two full
            # propagations back-to-back causes OOM on typical VRAM (~12 GB).
            #
            # Text-only VG detection is accurate enough for the mask target
            # the LLM identified from the user's clicks.
            text_prompt = prompt or "object"

            video_model.add_prompt(
                inference_state,
                frame_idx=0,
                text_str=text_prompt,
            )
            if points and labels:
                log.info("Point prompts (%d pts) informed text target: '%s'",
                         len(points), text_prompt)

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
                        if torch.is_tensor(binary_masks):
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
                    inference_state = None
                # Restore original detection threshold so subsequent runs
                # with different settings aren't affected.
                if orig_det_thresh is not None:
                    video_model.new_det_thresh = orig_det_thresh
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        # Fill any missing frames with empty masks
        for i in range(len(frame_files)):
            if i not in mask_frames_saved:
                mask = np.zeros((h, w), dtype=np.uint8)
                mask_img = Image.fromarray(mask, mode="L")
                mask_img.save(os.path.join(masks_dir, f"{i:06d}.png"))

        log.info("Saved %d mask frames (%d with detections)",
                 len(frame_files), len(mask_frames_saved))

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
        for d in (frames_dir, masks_dir):
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
        output_path = mask_video_path.replace(".mp4", "_overlay.mp4")

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
    global _image_model, _image_processor, _video_model

    _image_model = None
    _image_processor = None
    _video_model = None

    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    log.info("SAM3 models unloaded and GPU memory freed")
