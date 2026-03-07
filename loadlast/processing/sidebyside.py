"""
Side-by-side image stitcher.

Horizontally stitches two images with a padding gap for
quick before/after comparison.
"""

from __future__ import annotations

from typing import Optional

import torch
import torch.nn.functional as F


def compose_side_by_side(
    image_a: torch.Tensor,
    image_b: Optional[torch.Tensor],
    padding: int = 4,
    bg_color: tuple[int, int, int] = (26, 26, 26),
) -> torch.Tensor:
    """
    Horizontally stitch two images with a padding gap.

    If image_b is None, the right panel is filled with bg_color.
    Both images are resized to match image_a's height.

    Args:
        image_a: [H, W, 3] tensor — most recent image (left panel)
        image_b: [H, W, 3] tensor — previous image (right panel), or None
        padding: pixel gap between the two panels
        bg_color: RGB tuple (0-255) for the gap/empty panel color

    Returns:
        [1, H, W*2+padding, 3] tensor
    """
    h, w_a = image_a.shape[0], image_a.shape[1]

    if image_b is not None:
        # Resize image_b to match image_a's height
        if image_b.shape[0] != h:
            img_nchw = image_b.permute(2, 0, 1).unsqueeze(0)
            # Scale width proportionally
            scale = h / image_b.shape[0]
            new_w = int(image_b.shape[1] * scale)
            img_nchw = F.interpolate(
                img_nchw, size=(h, new_w), mode='bilinear', align_corners=False
            )
            image_b = img_nchw.squeeze(0).permute(1, 2, 0)

        w_b = image_b.shape[1]
    else:
        w_b = w_a

    bg = torch.tensor([c / 255.0 for c in bg_color], dtype=torch.float32)

    total_w = w_a + padding + w_b
    result = bg.view(1, 1, 3).expand(h, total_w, 3).clone()

    # Place image_a (left)
    result[:h, :w_a, :] = image_a

    # Place image_b (right) if available
    if image_b is not None:
        result[:h, w_a + padding:w_a + padding + w_b, :] = image_b

    return result.unsqueeze(0)  # [1, H, total_W, 3]
