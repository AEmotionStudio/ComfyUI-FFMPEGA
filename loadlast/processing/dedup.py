"""
Duplicate detection via lightweight pixel-sampling hash.

Samples a deterministic grid of pixel positions from an image tensor
and computes a combined hash. Fast enough to run on every image push (<1ms).
"""

from __future__ import annotations

import torch


def compute_pixel_hash(tensor: torch.Tensor, sample_points: int = 64) -> int:
    """
    Compute a lightweight perceptual hash by sampling fixed pixel positions.

    Args:
        tensor: [H, W, 3] or [H, W, C] float32 image tensor in [0, 1] range
        sample_points: number of positions to sample (default 64)

    Returns:
        Integer hash value. Two identical images will produce the same hash.

    Note:
        Hashes are resolution-dependent — the same image at different
        resolutions will produce different hashes because the sampled
        grid positions map differently. This is fine for the current
        use case where dedup runs before any resizing.
    """
    if tensor.ndim != 3:
        raise ValueError(f"Expected 3D tensor [H, W, C], got shape {tensor.shape}")

    h, w = tensor.shape[0], tensor.shape[1]

    if h == 0 or w == 0:
        return 0

    # Generate deterministic sample positions in a grid pattern
    n_rows = int(sample_points ** 0.5)
    n_cols = (sample_points + n_rows - 1) // n_rows

    # Clamp to actual dimensions
    n_rows = min(n_rows, h)
    n_cols = min(n_cols, w)

    if n_rows == 0 or n_cols == 0:
        return 0

    row_step = max(1, h // n_rows)
    col_step = max(1, w // n_cols)

    # Vectorized sampling: generate index arrays and gather pixels in one op
    row_indices = torch.arange(0, min(h, n_rows * row_step), row_step)
    col_indices = torch.arange(0, min(w, n_cols * col_step), col_step)

    # Use advanced indexing to sample all pixels at once
    sampled = tensor[row_indices[:, None], col_indices[None, :], :3]  # [R, C, 3]
    quantized = (sampled * 255).to(torch.uint8)
    values = quantized.reshape(-1).tolist()

    return hash(tuple(values))


def is_duplicate(hash_a: int, hash_b: int) -> bool:
    """
    Exact hash comparison.

    Returns True if images are considered identical based on their pixel hashes.
    """
    return hash_a == hash_b
