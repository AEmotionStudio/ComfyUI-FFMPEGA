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
    dirs = list(site.getsitepackages()) + [site.getusersitepackages()]
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
_video_model = None


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

    missing_keys, _ = model.load_state_dict(sam3_image_ckpt, strict=False)
    if missing_keys:
        log.debug("SAM3 loaded with missing keys: %s", missing_keys[:5])


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

def load_image_model():
    """Load and cache the SAM3 image model + processor.

    Returns:
        Tuple of (model, Sam3Processor).

    Raises:
        ImportError: If SAM3 is not installed.
    """
    global _image_model, _image_processor

    if _image_model is not None and _image_processor is not None:
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

    _image_model = model
    _image_processor = Sam3Processor(model)

    log.info("SAM3 image model loaded successfully")
    return _image_model, _image_processor


def load_video_model():
    """Load and cache the SAM3 video model.

    Returns:
        SAM3 video predictor instance.

    Raises:
        ImportError: If SAM3 is not installed.
    """
    global _video_model

    if _video_model is not None:
        return _video_model

    _patch_sam3_imports()

    try:
        from sam3.model_builder import build_sam3_video_model
    except ImportError:
        raise ImportError(
            "SAM3 is not installed. Install with: "
            "pip install --no-deps git+https://github.com/facebookresearch/sam3.git"
        )

    _free_vram()

    checkpoint_path = _find_checkpoint()
    log.info("Loading SAM3 video model from: %s", checkpoint_path)

    if checkpoint_path.endswith(".safetensors"):
        # build_sam3_video_model uses torch.load internally which can't
        # handle safetensors. Build without checkpoint, then load manually.
        model = build_sam3_video_model(
            checkpoint_path=None,
            load_from_HF=False,
        )
        _load_safetensors_video(model, checkpoint_path)
    else:
        # .pt file — sam3's builder uses torch.load(weights_only=True)
        # which fails on PyTorch 2.6+ with some checkpoints.
        # Monkey-patch torch.load to use weights_only=False.
        import torch
        _orig_load = torch.load
        def _patched_load(*args, **kwargs):
            kwargs["weights_only"] = False
            return _orig_load(*args, **kwargs)
        torch.load = _patched_load
        try:
            model = build_sam3_video_model(
                checkpoint_path=checkpoint_path,
                load_from_HF=False,
            )
        finally:
            torch.load = _orig_load

    # Note: SAM3's Sam3TrackerPredictor.__init__ enters a permanent bfloat16
    # autocast context. This is by design — SAM3 uses mixed-precision bf16
    # inference. Do NOT call model.float() or disable autocast; it breaks
    # the model's internal dtype expectations.

    _video_model = model
    log.info("SAM3 video model loaded successfully")
    return _video_model


# ---------------------------------------------------------------------------
#  Image masking with text prompts
# ---------------------------------------------------------------------------

def mask_image_with_text(
    image_path: str,
    prompt: str,
) -> np.ndarray:
    """Generate masks for objects described by a text prompt.

    Args:
        image_path: Path to the image file.
        prompt: Text description of what to segment (e.g. "the dog").

    Returns:
        Binary mask as numpy array (H, W) where 255=masked, 0=unmasked.
    """
    from PIL import Image

    model, processor = load_image_model()
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

def mask_video(
    video_path: str,
    prompt: str,
    output_dir: Optional[str] = None,
) -> str:
    """Generate a grayscale mask video for text-prompted objects.

    Extracts frames, runs SAM3 video predictor with text prompt,
    and outputs a grayscale mask video (white=target, black=background).

    Args:
        video_path: Path to input video.
        prompt: Text description of what to segment.
        output_dir: Directory for output files. Uses temp dir if None.

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

    # Get FPS from source video
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
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_str) if fps_str else 30.0

    # 2. Run SAM3 video predictor with text prompt
    log.info("Running SAM3 video tracking on %d frames (prompt: '%s')",
             len(frame_files), prompt)

    video_model = load_video_model()

    import torch
    # SAM3's tracker expects a bfloat16 autocast context (entered permanently
    # in Sam3TrackerPredictor.__init__). ComfyUI's operations between runs
    # can pop this off the thread-local autocast stack. Re-enter it here
    # to ensure consistent dtype handling on every run.
    with torch.inference_mode(), \
         torch.autocast("cuda", dtype=torch.bfloat16):
        # Initialize inference state from frames directory
        inference_state = video_model.init_state(
            resource_path=frames_dir,
            video_loader_type="cv2",
        )

        # Add text prompt on first frame
        video_model.add_prompt(
            inference_state,
            frame_idx=0,
            text_str=prompt,
        )

        # Get original video dimensions
        first_frame = np.array(Image.open(frame_files[0]))
        h, w = first_frame.shape[:2]

        # 3. Propagate and save mask frames
        log.info("Propagating SAM3 masks across %d frames", len(frame_files))
        mask_frames_saved = set()
        for frame_idx, outputs in video_model.propagate_in_video(inference_state):
            if outputs is None:
                continue

            binary_masks = outputs.get("out_binary_masks")
            if binary_masks is not None and len(binary_masks) > 0:
                # Combine all object masks into one
                if hasattr(binary_masks, 'numpy'):
                    binary_masks = binary_masks.cpu().numpy()
                combined = np.any(binary_masks, axis=0)
                mask = (combined > 0).astype(np.uint8) * 255
            else:
                mask = np.zeros((h, w), dtype=np.uint8)

            mask_img = Image.fromarray(mask, mode="L")
            if mask_img.size != (w, h):
                mask_img = mask_img.resize((w, h), Image.NEAREST)
            mask_img.save(os.path.join(masks_dir, f"{frame_idx:06d}.png"))
            mask_frames_saved.add(frame_idx)

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
    return mask_video_path


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
