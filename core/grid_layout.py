"""Shared grid-layout math for multi-panel comparison outputs.

Used by both ``core/video_compare.py`` (ffmpeg xstack offsets) and
``core/image_compare.py`` (tensor placement) so the Save Video and Save
Image nodes lay panels out identically.

Layout modes:
    auto        best-fit:  2 -> 2x1, 3 -> 3x1, 4 -> 2x2, else near-square grid
    horizontal  single row  (N x 1)
    vertical    single column (1 x N)
    grid        near-square grid (same as auto for N > 4)
"""

from __future__ import annotations

import math


def compute_grid(n: int, layout: str = "auto") -> tuple[int, int]:
    """Return ``(cols, rows)`` for ``n`` panels under ``layout``.

    ``cols * rows`` is always >= ``n`` (the last cells may be empty).
    """
    n = max(1, int(n))
    layout = (layout or "auto").lower()

    if layout == "horizontal":
        return n, 1
    if layout == "vertical":
        return 1, n
    if layout == "grid":
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        return cols, rows

    # auto
    if n <= 1:
        return 1, 1
    if n == 2:
        return 2, 1
    if n == 3:
        return 3, 1
    if n == 4:
        return 2, 2
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows


def cell_positions(
    cols: int,
    rows: int,
    cell_w: int,
    cell_h: int,
    gap: int = 0,
) -> list[tuple[int, int]]:
    """Top-left ``(x, y)`` of each uniform cell, row-major order.

    Returns ``cols * rows`` positions; callers use the first ``n``.
    """
    positions: list[tuple[int, int]] = []
    for r in range(rows):
        for c in range(cols):
            positions.append((c * (cell_w + gap), r * (cell_h + gap)))
    return positions
