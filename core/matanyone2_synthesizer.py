"""MatAnyone2 video matting synthesizer for ComfyUI-FFMPEGA.

Provides production-quality alpha mattes and foreground extraction with
temporal coherence. Uses the MatAnyone2 model (CVPR 2026) for video matting.

⚠️ LICENSE NOTICE — NTU S-Lab License 1.0
=========================================
MatAnyone2 is released under the **NTU S-Lab License 1.0** which is strictly
**non-commercial**.  Commercial use requires explicit written permission from
the authors.  See: https://github.com/pq-yang/MatAnyone2/blob/main/LICENSE

If you are using this in a commercial product, you MUST obtain a separate
license from the original authors before distributing.
=========================================
"""

from __future__ import annotations

import gc
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from tqdm import tqdm

logger = logging.getLogger("ffmpega")

# ── Module-level model cache ────────────────────────────────────────────────
_model = None
_processor = None
_LICENSE_LOGGED = False

# HuggingFace mirror repo
_HF_REPO = "AEmotionStudio/matanyone2"
_MODEL_FILENAME = "matanyone2.safetensors"


# ── Paths ────────────────────────────────────────────────────────────────────

def _get_model_dir() -> Path:
    """Return the model directory, creating it if needed."""
    try:
        import folder_paths  # type: ignore[import-not-found]
        base = Path(folder_paths.models_dir)
    except ImportError:
        base = Path(__file__).resolve().parent.parent.parent / "models"
    model_dir = base / "matanyone2"
    model_dir.mkdir(parents=True, exist_ok=True)
    return model_dir


def _get_ffmpeg_bin() -> str:
    """Get the FFmpeg binary path."""
    try:
        from .bin_paths import get_ffmpeg_bin
        return get_ffmpeg_bin()
    except ImportError:
        return "ffmpeg"


# ── VRAM Management ─────────────────────────────────────────────────────────

def _free_vram() -> None:
    """Free VRAM from other synthesizer modules before loading MatAnyone2."""
    try:
        from ._vram_utils import free_for_module
        free_for_module(exclude="matanyone2_synthesizer")
    except ImportError:
        pass


def cleanup() -> None:
    """Release the cached model and free all GPU memory."""
    global _model, _processor

    if _model is not None:
        try:
            _model.cpu()
        except Exception:
            pass
        _model = None

    if _processor is not None:
        _processor = None

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

    try:
        import comfy.model_management  # type: ignore[import-not-found]
        comfy.model_management.soft_empty_cache()
    except Exception:
        pass

    logger.info("matanyone2: model released, VRAM freed")


# ── Model Loading ───────────────────────────────────────────────────────────

def _download_model(model_dir: Path) -> Path:
    """Download the MatAnyone2 checkpoint from AEmotionStudio HF mirror."""
    ckpt_path = model_dir / _MODEL_FILENAME
    if ckpt_path.exists():
        logger.info("matanyone2: checkpoint found: %s", ckpt_path)
        return ckpt_path

    # Check download permission
    try:
        from .model_manager import require_downloads_allowed, download_with_progress
        require_downloads_allowed("matanyone2")
    except ImportError:
        pass

    logger.info("matanyone2: downloading checkpoint from %s ...", _HF_REPO)
    try:
        from huggingface_hub import hf_hub_download
        from .model_manager import download_with_progress

        path = download_with_progress(
            "matanyone2",
            lambda: hf_hub_download(
                repo_id=_HF_REPO,
                filename=_MODEL_FILENAME,
                local_dir=str(model_dir),
            ),
        )
        logger.info("matanyone2: checkpoint downloaded: %s", path)
        return Path(path)
    except Exception as e:
        raise RuntimeError(
            f"matanyone2: failed to download model from {_HF_REPO}: {e}. "
            f"Download manually from https://huggingface.co/{_HF_REPO} "
            f"and place {_MODEL_FILENAME} in {model_dir}"
        ) from e


def load_model(device: Optional[torch.device] = None) -> tuple:
    """Load and cache the MatAnyone2 model + inference processor.

    Returns (model, processor) tuple.
    """
    global _model, _processor, _LICENSE_LOGGED

    if not _LICENSE_LOGGED:
        logger.info(
            "matanyone2: ⚠️  MatAnyone2 is licensed under NTU S-Lab License 1.0 "
            "(NON-COMMERCIAL USE ONLY). Commercial use requires separate permission "
            "from the authors. See: https://github.com/pq-yang/MatAnyone2"
        )
        _LICENSE_LOGGED = True

    if _model is not None and _processor is not None:
        # Move model back to device if needed
        if device is not None:
            _model.to(device)
        return _model, _processor

    # Free VRAM from other modules first
    _free_vram()

    if device is None:
        if torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")

    model_dir = _get_model_dir()
    ckpt_path = _download_model(model_dir)

    logger.info("matanyone2: loading model on %s ...", device)

    from .matanyone2.utils.get_default_model import get_matanyone2_model
    from .matanyone2.inference.inference_core import InferenceCore

    model = get_matanyone2_model(str(ckpt_path), device=device)
    processor = InferenceCore(model, cfg=model.cfg, device=device)

    _model = model
    _processor = processor

    logger.info("matanyone2: model loaded successfully")
    return _model, _processor


# ── Background Color Helpers ────────────────────────────────────────────────

_BG_COLORS = {
    "green":  np.array([120, 255, 155], dtype=np.float32) / 255.0,
    "black":  np.array([0, 0, 0], dtype=np.float32),
    "white":  np.array([255, 255, 255], dtype=np.float32) / 255.0,
    "blue":   np.array([0, 0, 255], dtype=np.float32) / 255.0,
}


def _get_bg_color(name: str) -> np.ndarray:
    """Return a (1,1,3) float32 array for the named background color."""
    color = _BG_COLORS.get(name.lower(), _BG_COLORS["green"])
    return color.reshape(1, 1, 3)


# ── Video Processing ────────────────────────────────────────────────────────

def _get_video_fps(video_path: str) -> float:
    """Get video FPS using OpenCV."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return fps if fps > 0 else 30.0


def _write_frames_to_video(
    frames: list[np.ndarray],
    output_path: str,
    fps: float,
    is_grayscale: bool = False,
) -> str:
    """Write frames to video using FFmpeg (replaces imageio.mimwrite)."""
    ffmpeg = _get_ffmpeg_bin()

    if not frames:
        raise RuntimeError("matanyone2: no frames to write")

    h, w = frames[0].shape[:2]

    if is_grayscale:
        pix_fmt_in = "gray"
        pix_fmt_out = "gray"
    else:
        pix_fmt_in = "rgb24"
        pix_fmt_out = "yuv420p"

    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo",
        "-pix_fmt", pix_fmt_in,
        "-s", f"{w}x{h}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "medium",
        "-pix_fmt", pix_fmt_out,
        output_path,
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    for frame in frames:
        if is_grayscale and frame.ndim == 3:
            frame = frame.squeeze(-1)
        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    _, stderr = proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(
            f"matanyone2: FFmpeg encoding failed:\n{stderr.decode()[-500:]}"
        )

    return output_path


@torch.inference_mode()
def process_video(
    video_path: str,
    mask_path: str,
    output_dir: str,
    output_type: str = "foreground",
    background_color: str = "green",
    max_size: int = -1,
    warmup: int = 10,
    erode_kernel: int = 10,
    dilate_kernel: int = 10,
) -> dict[str, str]:
    """Run MatAnyone2 video matting on the input video.

    Args:
        video_path: Path to the input video file.
        mask_path: Path to the first-frame segmentation mask (grayscale PNG).
        output_dir: Directory to write output files.
        output_type: One of "foreground", "alpha", "both", "green_screen".
        background_color: Background color for composite ("green", "black", "white", "blue").
        max_size: Resolution cap — downsamples if min(W,H) exceeds this. -1 = no limit.
        warmup: Number of warmup iterations for first-frame alpha prediction.
        erode_kernel: Erosion kernel size on the input mask.
        dilate_kernel: Dilation kernel size on the input mask.

    Returns:
        Dict with keys like "foreground", "alpha" mapping to output video paths.
    """
    try:
        # Determine device
        if torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")

        model, processor = load_model(device)

        from .matanyone2.utils.inference_utils import gen_dilate, gen_erosion, read_frame_from_videos

        # Reset processor state for fresh inference
        processor.clear_memory()

        # Load input frames
        vframes, fps, length, video_name = read_frame_from_videos(video_path)
        logger.info("matanyone2: loaded %d frames at %.1f FPS from %s", length, fps, video_path)

        # Add warmup frames (repeat first frame)
        warmup = int(warmup)
        repeated_frames = vframes[0].unsqueeze(0).repeat(warmup, 1, 1, 1)
        vframes = torch.cat([repeated_frames, vframes], dim=0).float()
        length += warmup

        # Resize if needed
        new_h, new_w = vframes.shape[-2:]
        if max_size > 0:
            h, w = new_h, new_w
            min_side = min(h, w)
            if min_side > max_size:
                new_h = int(h / min_side * max_size)
                new_w = int(w / min_side * max_size)
                vframes = F.interpolate(vframes, size=(new_h, new_w), mode="area")
                logger.info("matanyone2: resized to %dx%d for processing", new_w, new_h)

        # Load and process the first-frame mask
        mask = np.array(Image.open(mask_path).convert("L"))
        if dilate_kernel > 0:
            mask = gen_dilate(mask, dilate_kernel, dilate_kernel)
        if erode_kernel > 0:
            mask = gen_erosion(mask, erode_kernel, erode_kernel)
        mask = torch.from_numpy(mask).float().to(device)
        # Resize mask if it doesn't match video frame dimensions.
        # External masks (e.g. from image_path_a) may be at a different
        # resolution than the video being processed.
        mask_h, mask_w = mask.shape[-2:]
        if mask_h != new_h or mask_w != new_w:
            logger.info(
                "matanyone2: resizing mask from %dx%d to %dx%d to match frames",
                mask_w, mask_h, new_w, new_h,
            )
            mask = F.interpolate(
                mask.unsqueeze(0).unsqueeze(0), size=(new_h, new_w), mode="nearest"
            )[0, 0]
        elif max_size > 0:
            mask = F.interpolate(
                mask.unsqueeze(0).unsqueeze(0), size=(new_h, new_w), mode="nearest"
            )[0, 0]

        # Prepare background color
        bgr = _get_bg_color(background_color)
        objects = [1]

        # Run matting inference
        need_foreground = output_type in ("foreground", "both", "green_screen")
        need_alpha = output_type in ("alpha", "both")

        phas: list[np.ndarray] = []
        fgrs: list[np.ndarray] = []

        for ti in tqdm(range(length), desc="MatAnyone2 matting"):
            image = vframes[ti]
            image_np = np.array(image.permute(1, 2, 0))
            image = (image / 255.0).float().to(device)

            if ti == 0:
                output_prob = processor.step(image, mask, objects=objects)
                output_prob = processor.step(image, first_frame_pred=True)
            elif ti <= warmup:
                output_prob = processor.step(image, first_frame_pred=True)
            else:
                output_prob = processor.step(image)

            mask = processor.output_prob_to_mask(output_prob)
            pha = mask.unsqueeze(2).cpu().numpy()

            # Only collect frames after warmup
            if ti > (warmup - 1):
                if need_foreground:
                    com_np = image_np / 255.0 * pha + bgr * (1 - pha)
                    com_np = np.round(np.clip(com_np * 255.0, 0, 255)).astype(np.uint8)
                    fgrs.append(com_np)
                if need_alpha:
                    pha_u8 = np.round(np.clip(pha * 255.0, 0, 255)).astype(np.uint8)
                    phas.append(pha_u8)

        # Write output videos
        os.makedirs(output_dir, exist_ok=True)
        results: dict[str, str] = {}

        if need_foreground:
            fgr_path = os.path.join(output_dir, f"{video_name}_matted.mp4")
            _write_frames_to_video(fgrs, fgr_path, fps, is_grayscale=False)
            results["foreground"] = fgr_path
            logger.info("matanyone2: foreground video → %s", fgr_path)

        if need_alpha:
            alpha_path = os.path.join(output_dir, f"{video_name}_alpha.mp4")
            _write_frames_to_video(phas, alpha_path, fps, is_grayscale=True)
            results["alpha"] = alpha_path
            logger.info("matanyone2: alpha matte → %s", alpha_path)

        logger.info("matanyone2: processing complete — %d output frames", len(fgrs or phas))
        return results

    finally:
        # Always clean up VRAM
        cleanup()
