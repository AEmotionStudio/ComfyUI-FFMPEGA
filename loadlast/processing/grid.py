"""
Grid layout compositor.

Arranges a list of image tensors into an NxM grid with configurable
columns, padding, border, and optional captions.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F


def compose_grid(
    images: list[torch.Tensor],
    columns: int = 2,
    padding: int = 4,
    border: int = 0,
    bg_color: tuple[int, int, int] = (26, 26, 26),
    captions: list[str] | None = None,
) -> torch.Tensor:
    """
    Arrange images into an NxM grid.

    All images are resized to match the first image's dimensions.
    Empty cells are filled with bg_color.

    Args:
        images: list of [H, W, 3] tensors (float32, [0, 1])
        columns: number of columns in the grid
        padding: pixel gap between cells
        border: outer border around the entire grid
        bg_color: RGB tuple (0-255) for padding/empty cell color
        captions: optional list of caption strings per cell (v1.1, not yet rendered)

    Returns:
        [1, grid_H, grid_W, 3] tensor
    """
    if not images:
        # Return a small black image if no images provided
        return torch.zeros(1, 64, 64, 3)

    # Target dimensions from the first image
    target_h, target_w = images[0].shape[0], images[0].shape[1]

    # Resize all images to match the first image
    resized = []
    for img in images:
        if img.shape[0] != target_h or img.shape[1] != target_w:
            # Use interpolate: expects [N, C, H, W]
            img_nchw = img.permute(2, 0, 1).unsqueeze(0)  # [1, 3, H, W]
            img_nchw = F.interpolate(
                img_nchw, size=(target_h, target_w), mode='bilinear', align_corners=False
            )
            img = img_nchw.squeeze(0).permute(1, 2, 0)  # [H, W, 3]
        resized.append(img)

    n_images = len(resized)
    columns = min(columns, n_images)
    rows = (n_images + columns - 1) // columns

    # Compute grid dimensions
    bg = torch.tensor([c / 255.0 for c in bg_color], dtype=torch.float32)

    grid_h = rows * target_h + (rows - 1) * padding + 2 * border
    grid_w = columns * target_w + (columns - 1) * padding + 2 * border

    # Create background
    grid = bg.view(1, 1, 3).expand(grid_h, grid_w, 3).clone()

    # Place images
    for idx, img in enumerate(resized):
        row = idx // columns
        col = idx % columns

        y = border + row * (target_h + padding)
        x = border + col * (target_w + padding)

        grid[y:y + target_h, x:x + target_w, :] = img

    return grid.unsqueeze(0)  # [1, grid_H, grid_W, 3]
