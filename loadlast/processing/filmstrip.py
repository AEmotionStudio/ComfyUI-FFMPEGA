"""
Filmstrip compositor.

Creates a horizontal filmstrip of evenly-spaced video frames,
scaled down proportionally for compact visual summaries.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F

from .video_decode import VideoDecoder


def compose_filmstrip(
    frames: torch.Tensor,
    num_frames: int = 8,
    scale: float = 0.25,
    padding: int = 4,
    bg_color: tuple[int, int, int] = (26, 26, 26),
) -> torch.Tensor:
    """
    Create a horizontal filmstrip of evenly-spaced frames.

    Args:
        frames: [N, H, W, 3] full frame tensor
        num_frames: number of frames to show in the strip
        scale: scale factor for frame height (0.25 = quarter size)
        padding: pixel gap between frames
        bg_color: RGB tuple (0-255) for gap color

    Returns:
        [1, scaled_H, total_W, 3] tensor
    """
    n_total = frames.shape[0]

    if n_total == 0:
        return torch.zeros(1, 64, 64, 3)

    # Select evenly-spaced frame indices
    indices = VideoDecoder.subsample_indices(n_total, min(num_frames, n_total))
    selected = [frames[i] for i in indices]

    if not selected:
        return torch.zeros(1, 64, 64, 3)

    # Scale frames down
    h, w = selected[0].shape[0], selected[0].shape[1]
    new_h = max(1, int(h * scale))
    new_w = max(1, int(w * scale))

    scaled_frames = []
    for frame in selected:
        # Resize using interpolate: expects [N, C, H, W]
        frame_nchw = frame.permute(2, 0, 1).unsqueeze(0)  # [1, 3, H, W]
        frame_nchw = F.interpolate(
            frame_nchw, size=(new_h, new_w), mode='bilinear', align_corners=False
        )
        scaled = frame_nchw.squeeze(0).permute(1, 2, 0)  # [new_H, new_W, 3]
        scaled_frames.append(scaled)

    # Compose horizontal strip
    n_selected = len(scaled_frames)
    total_w = n_selected * new_w + (n_selected - 1) * padding

    bg = torch.tensor([c / 255.0 for c in bg_color], dtype=torch.float32)
    strip = bg.view(1, 1, 3).expand(new_h, total_w, 3).clone()

    for i, frame in enumerate(scaled_frames):
        x = i * (new_w + padding)
        strip[:new_h, x:x + new_w, :] = frame

    return strip.unsqueeze(0)  # [1, new_H, total_W, 3]
