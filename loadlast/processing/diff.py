"""
Diff overlay compositor.

Computes per-pixel absolute difference between two images and creates
visual change-highlight outputs: heatmap, overlay, and side-by-side diff.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F


def compose_diff(
    image_a: torch.Tensor,
    image_b: torch.Tensor | None,
    mode: str = "heatmap",
    sensitivity: float = 1.0,
) -> torch.Tensor:
    """
    Compute change-highlighting diff between two images.

    Args:
        image_a: [H, W, 3] most recent image
        image_b: [H, W, 3] previous image (or None → black diff)
        mode: "heatmap", "overlay", or "side_by_side_diff"
        sensitivity: multiplier on raw diff values (>1 = more visible)

    Returns:
        [1, H, W, 3] diff visualization tensor
    """
    h, w = image_a.shape[0], image_a.shape[1]

    if image_b is None:
        # No previous image: return solid black
        return torch.zeros(1, h, w, 3)

    # Resize image_b to match image_a if needed
    if image_b.shape[0] != h or image_b.shape[1] != w:
        b_nchw = image_b.permute(2, 0, 1).unsqueeze(0)
        b_nchw = F.interpolate(b_nchw, size=(h, w), mode='bilinear', align_corners=False)
        image_b = b_nchw.squeeze(0).permute(1, 2, 0)

    # Raw per-pixel difference
    raw_diff = (image_a - image_b).abs()

    # Apply sensitivity multiplier
    if sensitivity != 1.0:
        raw_diff = (raw_diff * sensitivity).clamp(0, 1)

    # Grayscale diff magnitude
    diff_gray = raw_diff.mean(dim=2, keepdim=True)  # [H, W, 1]

    if mode == "heatmap":
        return _diff_to_heatmap(diff_gray).unsqueeze(0)

    elif mode == "overlay":
        # 50% blend of image_a with heatmap
        heatmap = _diff_to_heatmap(diff_gray)
        blended = image_a * 0.5 + heatmap * 0.5
        return blended.clamp(0, 1).unsqueeze(0)

    elif mode == "side_by_side_diff":
        # Three-panel: image_a | heatmap diff | image_b
        heatmap = _diff_to_heatmap(diff_gray)
        gap = 4
        total_w = w * 3 + gap * 2
        bg = torch.tensor([0.1, 0.1, 0.1], dtype=torch.float32)
        result = bg.view(1, 1, 3).expand(h, total_w, 3).clone()
        result[:, :w, :] = image_a
        result[:, w + gap:w * 2 + gap, :] = heatmap
        result[:, w * 2 + gap * 2:, :] = image_b
        return result.unsqueeze(0)

    else:
        # Unknown mode, return raw diff
        return raw_diff.unsqueeze(0)


def _diff_to_heatmap(diff_gray: torch.Tensor) -> torch.Tensor:
    """
    Convert grayscale diff [H, W, 1] to a blue→red heatmap [H, W, 3].

    Color mapping:
    - 0.0 (no change): dark blue
    - 0.5: yellow
    - 1.0 (max change): bright red
    """
    diff = diff_gray.squeeze(2)  # [H, W]

    r = (diff * 3.0).clamp(0, 1)
    g = ((diff - 0.33) * 3.0).clamp(0, 1) * (1.0 - ((diff - 0.67) * 3.0).clamp(0, 1))
    b = (1.0 - diff * 2.0).clamp(0, 1)

    return torch.stack([r, g, b], dim=2)  # [H, W, 3]
