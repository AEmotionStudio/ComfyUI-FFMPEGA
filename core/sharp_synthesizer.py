"""SHARP synthesizer — single-image 3D Gaussian view synthesis.

Wraps Apple's SHARP model (https://github.com/apple/ml-sharp) to:
1. Predict 3D Gaussian splat parameters from a single image (<1s)
2. Render a camera trajectory video via gsplat

⚠️ Model weights are Apple ML Research License (non-commercial / research only).

For licensing see accompanying LICENSE file.
Copyright (C) 2025 Apple Inc. All Rights Reserved (model code).
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import torch

logger = logging.getLogger("ffmpega")

# Default focal length in 35mm equivalent (used when EXIF is unavailable)
_DEFAULT_F35MM = 30.0

# Model checkpoint filename (safetensors on mirror, .pt from Apple CDN)
_CHECKPOINT_FILENAME_ST = "sharp.safetensors"
_CHECKPOINT_FILENAME_PT = "sharp_2572gikvuh.pt"
_APPLE_CDN_URL = "https://ml-site.cdn-apple.com/models/sharp/sharp_2572gikvuh.pt"

# Valid trajectory types
TRAJECTORY_TYPES = ("rotate_forward", "swipe", "shake", "rotate")


def _get_models_dir() -> Path:
    """Resolve ComfyUI models/sharp/ directory."""
    try:
        import folder_paths  # type: ignore[import-not-found]
        base = Path(folder_paths.models_dir)
    except (ImportError, AttributeError):
        base = Path.home() / "ComfyUI" / "models"
    sharp_dir = base / "sharp"
    sharp_dir.mkdir(parents=True, exist_ok=True)
    return sharp_dir


def _resolve_checkpoint() -> Path:
    """Find or download the SHARP checkpoint.

    Priority:
    1. ComfyUI/models/sharp/sharp.safetensors (mirror download)
    2. ComfyUI/models/sharp/sharp_2572gikvuh.pt (manual placement)
    3. Auto-download from Apple CDN or AEmotionStudio mirror
    """
    from .model_manager import (
        require_downloads_allowed,
        try_mirror_download,
        download_with_progress,
    )

    models_dir = _get_models_dir()

    # Check for existing checkpoint
    st_path = models_dir / _CHECKPOINT_FILENAME_ST
    if st_path.is_file():
        logger.debug("SHARP: found safetensors checkpoint: %s", st_path)
        return st_path

    pt_path = models_dir / _CHECKPOINT_FILENAME_PT
    if pt_path.is_file():
        logger.debug("SHARP: found .pt checkpoint: %s", pt_path)
        return pt_path

    # Try mirror download (safetensors)
    require_downloads_allowed("sharp")
    mirror_path = try_mirror_download(
        model_key="sharp",
        filename=_CHECKPOINT_FILENAME_ST,
        local_dir=str(models_dir),
    )
    if mirror_path and os.path.isfile(mirror_path):
        return Path(mirror_path)

    # Fallback: download from Apple CDN
    logger.info("SHARP: downloading from Apple CDN → %s", pt_path)
    result = download_with_progress(
        "sharp",
        lambda: torch.hub.load_state_dict_from_url(
            _APPLE_CDN_URL,
            model_dir=str(models_dir),
            file_name=_CHECKPOINT_FILENAME_PT,
            progress=True,
            map_location="cpu",
        ),
    )
    # torch.hub.load_state_dict_from_url returns the state dict, not a path.
    # The file is saved to models_dir by torch.hub.
    # But the default cache is ~/.cache/torch/hub/checkpoints/.
    # Let's check both locations.
    hub_cache = Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / _CHECKPOINT_FILENAME_PT
    if hub_cache.is_file() and not pt_path.is_file():
        import shutil
        shutil.copy2(hub_cache, pt_path)
        logger.info("SHARP: copied checkpoint from hub cache to %s", pt_path)

    if pt_path.is_file():
        return pt_path

    raise FileNotFoundError(
        f"SHARP: could not find or download checkpoint. "
        f"Place {_CHECKPOINT_FILENAME_ST} or {_CHECKPOINT_FILENAME_PT} "
        f"in {models_dir}/"
    )


def _load_state_dict(checkpoint_path: Path, device: str = "cpu") -> dict:
    """Load state dict from .safetensors or .pt checkpoint."""
    if checkpoint_path.suffix == ".safetensors":
        from safetensors.torch import load_file
        return load_file(str(checkpoint_path), device=device)
    else:
        return torch.load(checkpoint_path, map_location=device, weights_only=True)


def _convert_focal_length(width: float, height: float, f_mm: float = 30.0) -> float:
    """Convert 35mm-equivalent focal length to pixels (matches SHARP's formula)."""
    return f_mm * np.sqrt(width**2.0 + height**2.0) / np.sqrt(36**2 + 24**2)


@torch.no_grad()
def predict_gaussians(
    image_np: np.ndarray,
    device: str = "cuda",
    checkpoint_path: Optional[Path] = None,
) -> tuple:
    """Predict 3D Gaussians from a single image.

    Args:
        image_np: HWC uint8 RGB numpy array.
        device: Device to run inference on ("cuda", "cpu", "mps").
        checkpoint_path: Optional explicit checkpoint path.

    Returns:
        Tuple of (gaussians, metadata, f_px) where:
        - gaussians: Gaussians3D NamedTuple
        - metadata: SceneMetaData NamedTuple
        - f_px: focal length in pixels
    """
    from sharp.models import PredictorParams, create_predictor
    from sharp.utils.gaussians import (
        Gaussians3D,
        SceneMetaData,
        unproject_gaussians,
    )

    if checkpoint_path is None:
        checkpoint_path = _resolve_checkpoint()

    logger.info("SHARP: loading model from %s", checkpoint_path)
    state_dict = _load_state_dict(checkpoint_path)

    predictor = create_predictor(PredictorParams())
    predictor.load_state_dict(state_dict)
    predictor.eval()
    predictor.to(device)

    height, width = image_np.shape[:2]
    f_px = _convert_focal_length(width, height, _DEFAULT_F35MM)

    # Prepare input tensor
    internal_shape = (1536, 1536)
    image_pt = torch.from_numpy(image_np.copy()).float().to(device).permute(2, 0, 1) / 255.0
    disparity_factor = torch.tensor([f_px / width]).float().to(device)

    image_resized = torch.nn.functional.interpolate(
        image_pt[None],
        size=(internal_shape[1], internal_shape[0]),
        mode="bilinear",
        align_corners=True,
    )

    # Predict in NDC space
    logger.info("SHARP: running inference on %dx%d image...", width, height)
    gaussians_ndc = predictor(image_resized, disparity_factor)

    # Unproject to metric space
    intrinsics = torch.tensor(
        [
            [f_px, 0, width / 2, 0],
            [0, f_px, height / 2, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ],
        device=device,
        dtype=torch.float32,
    )
    intrinsics_resized = intrinsics.clone()
    intrinsics_resized[0] *= internal_shape[0] / width
    intrinsics_resized[1] *= internal_shape[1] / height

    gaussians = unproject_gaussians(
        gaussians_ndc, torch.eye(4).to(device), intrinsics_resized, internal_shape
    )

    metadata = SceneMetaData(
        focal_length_px=f_px,
        resolution_px=(width, height),
        color_space="linearRGB",
    )

    # Free model VRAM
    del predictor
    if device == "cuda":
        torch.cuda.empty_cache()

    logger.info("SHARP: prediction complete — %d Gaussians", gaussians.mean_vectors.shape[0])
    return gaussians, metadata, f_px


def render_trajectory_video(
    gaussians,
    metadata,
    output_path: str,
    trajectory_type: str = "rotate_forward",
    num_frames: int = 60,
    max_disparity: float = 0.08,
    max_zoom: float = 0.15,
) -> str:
    """Render a camera trajectory video from Gaussian splats.

    Requires CUDA GPU (gsplat limitation).

    Args:
        gaussians: Gaussians3D from predict_gaussians().
        metadata: SceneMetaData from predict_gaussians().
        output_path: Path for the output MP4 video.
        trajectory_type: One of "rotate_forward", "swipe", "shake", "rotate".
        num_frames: Number of frames to render.
        max_disparity: Controls lateral camera movement range.
        max_zoom: Controls zoom intensity.

    Returns:
        Path to the rendered video.
    """
    from sharp.utils.camera import TrajectoryParams, create_eye_trajectory, create_camera_model
    from sharp.utils.gsplat import GSplatRenderer

    if not torch.cuda.is_available():
        raise RuntimeError(
            "SHARP video rendering requires a CUDA GPU (gsplat limitation). "
            "Prediction works on CPU/MPS, but rendering needs CUDA."
        )

    device = torch.device("cuda")
    (width, height) = metadata.resolution_px
    f_px = metadata.focal_length_px

    intrinsics = torch.tensor(
        [
            [f_px, 0, (width - 1) / 2.0, 0],
            [0, f_px, (height - 1) / 2.0, 0],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ],
        device=device,
        dtype=torch.float32,
    )

    params = TrajectoryParams(
        type=trajectory_type,
        max_disparity=max_disparity,
        max_zoom=max_zoom,
        num_steps=num_frames,
    )

    camera_model = create_camera_model(
        gaussians, intrinsics, resolution_px=metadata.resolution_px,
    )
    trajectory = create_eye_trajectory(
        gaussians, params, resolution_px=metadata.resolution_px, f_px=f_px,
    )

    renderer = GSplatRenderer(color_space=metadata.color_space)

    logger.info(
        "SHARP: rendering %d frames (%s trajectory, disparity=%.3f, zoom=%.3f)",
        num_frames, trajectory_type, max_disparity, max_zoom,
    )

    # Render frames to a temp directory, then encode with ffmpeg
    frames_dir = tempfile.mkdtemp(prefix="sharp_frames_")
    try:
        for i, eye_position in enumerate(trajectory):
            camera_info = camera_model.compute(eye_position)
            rendering_output = renderer(
                gaussians.to(device),
                extrinsics=camera_info.extrinsics[None].to(device),
                intrinsics=camera_info.intrinsics[None].to(device),
                image_width=camera_info.width,
                image_height=camera_info.height,
            )
            color = (rendering_output.color[0].permute(1, 2, 0) * 255.0).to(
                dtype=torch.uint8
            ).cpu().numpy()

            frame_path = os.path.join(frames_dir, f"frame_{i:05d}.png")
            from PIL import Image
            Image.fromarray(color).save(frame_path)

        return frames_dir
    except Exception:
        import shutil
        shutil.rmtree(frames_dir, ignore_errors=True)
        raise


def save_ply(
    gaussians,
    f_px: float,
    image_shape: tuple[int, int],
    output_path: str,
) -> str:
    """Save Gaussian splat to PLY file.

    Args:
        gaussians: Gaussians3D from predict_gaussians().
        f_px: Focal length in pixels.
        image_shape: (height, width) of the source image.
        output_path: Path for the output .ply file.

    Returns:
        Path to the saved PLY file.
    """
    from sharp.utils.gaussians import save_ply as sharp_save_ply

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sharp_save_ply(gaussians, f_px, image_shape, out)
    logger.info("SHARP: saved PLY to %s", out)
    return str(out)


def run_sharp_pipeline(
    image_np: np.ndarray,
    output_video_path: str,
    *,
    trajectory_type: str = "rotate_forward",
    num_frames: int = 60,
    max_disparity: float = 0.08,
    max_zoom: float = 0.15,
    device: str = "auto",
    export_ply: bool = False,
    ply_output_path: Optional[str] = None,
    checkpoint_path: Optional[Path] = None,
) -> tuple[str, Optional[str]]:
    """Full SHARP pipeline: image → gaussians → video.

    Args:
        image_np: HWC uint8 RGB numpy array.
        output_video_path: Path for the output MP4 video.
        trajectory_type: Camera trajectory type.
        num_frames: Number of frames to render.
        max_disparity: Lateral camera movement range.
        max_zoom: Zoom intensity.
        device: Device for prediction ("auto", "cuda", "cpu", "mps").
        export_ply: Whether to also save the .ply file.
        ply_output_path: Path for the .ply file (required if export_ply=True).
        checkpoint_path: Optional explicit checkpoint path.

    Returns:
        Tuple of (frames_dir, ply_path) where:
        - frames_dir: Path to directory of rendered PNG frames
        - ply_path: Path to .ply file (or None if not exported)
    """
    # Resolve device
    if device == "auto":
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch, "mps") and torch.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

    logger.info("SHARP: using device '%s' for prediction", device)

    # 1. Predict Gaussians
    gaussians, metadata, f_px = predict_gaussians(
        image_np, device=device, checkpoint_path=checkpoint_path,
    )

    # 2. Export PLY (optional)
    ply_path = None
    if export_ply and ply_output_path:
        height, width = image_np.shape[:2]
        ply_path = save_ply(gaussians, f_px, (height, width), ply_output_path)

    # 3. Render trajectory video (requires CUDA)
    if not torch.cuda.is_available():
        logger.warning(
            "SHARP: CUDA not available — skipping video rendering. "
            "Only PLY export is available on CPU/MPS."
        )
        if ply_path:
            return "", ply_path
        raise RuntimeError(
            "SHARP requires a CUDA GPU for video rendering. "
            "Set sharp_save_ply=true to export only the PLY file on CPU/MPS."
        )

    frames_dir = render_trajectory_video(
        gaussians=gaussians,
        metadata=metadata,
        output_path=output_video_path,
        trajectory_type=trajectory_type,
        num_frames=num_frames,
        max_disparity=max_disparity,
        max_zoom=max_zoom,
    )

    return frames_dir, ply_path
