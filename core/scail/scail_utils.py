# coding: utf-8
# Copyright 2024-2025 The Alibaba Wan Team Authors. All rights reserved.
# Vendored and adapted for ComfyUI-FFMPEGA.
# MODIFIED: Replaced decord video loading with FFmpeg-based loading.
"""Image / video loading helpers for SCAIL inference."""

import logging
import os
import subprocess
import tempfile

import numpy as np
import torch
import torchvision.transforms as TT
from PIL import Image
from torchvision.transforms import InterpolationMode
from torchvision.transforms.functional import center_crop, resize

log = logging.getLogger("ffmpega")

__all__ = [
    "load_image_to_tensor_chw_normalized",
    "load_video_for_pose_sample",
    "resize_for_rectangle_crop",
]


def _get_ffmpeg_bin() -> str:
    """Get the FFmpeg binary path."""
    try:
        from ..bin_paths import get_ffmpeg_bin
        return get_ffmpeg_bin()
    except ImportError:
        try:
            from core.bin_paths import get_ffmpeg_bin  # type: ignore
            return get_ffmpeg_bin()
        except ImportError:
            return "ffmpeg"


def load_image_to_tensor_chw_normalized(image: Image.Image) -> torch.Tensor:
    """Load PIL image to tensor normalized to [-1, 1].

    Returns:
        Tensor of shape [1, C, H, W] in range [-1, 1].
    """
    transform = TT.Compose([TT.ToTensor()])
    image_tensor = transform(image)
    # Scale to [-1, 1]
    image_tensor = (image_tensor * 2 - 1).unsqueeze(0)  # 1 C H W
    return image_tensor


def load_video_for_pose_sample(
    video_path: str,
    max_frames: int = 0,
) -> torch.Tensor:
    """Load video frames using FFmpeg (no decord dependency).

    Returns:
        Tensor of shape [T, H, W, C] with uint8 values [0, 255].
    """
    ffmpeg = _get_ffmpeg_bin()
    tmpdir = tempfile.mkdtemp(prefix="scail_pose_")

    try:
        cmd = [
            ffmpeg, "-i", video_path,
            "-vsync", "0",
            "-q:v", "1",
            os.path.join(tmpdir, "%06d.png"),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg frame extraction failed: {result.stderr[-500:]}"
            )

        frame_files = sorted(
            f for f in os.listdir(tmpdir) if f.endswith(".png")
        )
        if not frame_files:
            raise RuntimeError(f"No frames extracted from {video_path}")

        if max_frames > 0:
            frame_files = frame_files[:max_frames]

        frames = []
        for fname in frame_files:
            img = Image.open(os.path.join(tmpdir, fname)).convert("RGB")
            frames.append(np.array(img, dtype=np.uint8))

        return torch.from_numpy(np.stack(frames))  # T H W C, uint8
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def resize_for_rectangle_crop(
    arr: torch.Tensor,
    image_size: tuple[int, int],
    reshape_mode: str = "random",
) -> torch.Tensor:
    """Resize and crop tensor to target size maintaining aspect ratio.

    Args:
        arr: Tensor of shape [T/1, C, H, W] or similar.
        image_size: (target_h, target_w).
        reshape_mode: "random", "center", or "none".
    """
    if arr.shape[3] / arr.shape[2] > image_size[1] / image_size[0]:
        arr = resize(
            arr,
            size=[
                image_size[0],
                int(arr.shape[3] * image_size[0] / arr.shape[2]),
            ],
            interpolation=InterpolationMode.BICUBIC,
        )
    else:
        arr = resize(
            arr,
            size=[
                int(arr.shape[2] * image_size[1] / arr.shape[3]),
                image_size[1],
            ],
            interpolation=InterpolationMode.BICUBIC,
        )

    h, w = arr.shape[2], arr.shape[3]
    delta_h = h - image_size[0]
    delta_w = w - image_size[1]

    if reshape_mode in ("random", "none"):
        top = np.random.randint(0, delta_h + 1)
        left = np.random.randint(0, delta_w + 1)
    elif reshape_mode == "center":
        top, left = delta_h // 2, delta_w // 2
    else:
        raise NotImplementedError(f"Unknown reshape_mode: {reshape_mode}")

    arr = TT.functional.crop(
        arr, top=top, left=left, height=image_size[0], width=image_size[1],
    )
    return arr
