"""
Caption overlay rendering.

Burns text captions onto image tensors using PIL ImageDraw.
Supports configurable format tokens, semi-transparent bars,
and monospace font rendering.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Default caption height in pixels
CAPTION_HEIGHT = 24
CAPTION_BG_ALPHA = 0.65  # Semi-transparent black


def render_caption(
    image: torch.Tensor,
    text: str,
    font_size: int = 14,
    bar_height: int = CAPTION_HEIGHT,
    bar_alpha: float = CAPTION_BG_ALPHA,
    position: str = "bottom",
) -> torch.Tensor:
    """
    Burn a caption bar onto an image tensor.

    Args:
        image: [H, W, 3] float32 tensor in [0, 1]
        text: caption text to render
        font_size: text size in pixels
        bar_height: height of the semi-transparent bar
        bar_alpha: opacity of the bar background (0=transparent, 1=opaque)
        position: "top" or "bottom"

    Returns:
        [H, W, 3] tensor with caption burned in
    """
    if not text.strip():
        return image

    h, w = image.shape[0], image.shape[1]
    result = image.clone()

    # Determine bar position
    if position == "top":
        y_start = 0
    else:
        y_start = max(0, h - bar_height)

    y_end = min(h, y_start + bar_height)

    # Apply semi-transparent black bar
    bar_region = result[y_start:y_end, :, :]
    result[y_start:y_end, :, :] = bar_region * (1.0 - bar_alpha)

    # Render text using PIL
    try:
        text_img = _render_text_pil(text, w, bar_height, font_size)
        # Convert numpy array to tensor
        text_tensor = torch.from_numpy(text_img).float() / 255.0

        # Composite text (white text on darkened bar)
        mask = text_tensor.mean(dim=2, keepdim=True)  # Brightness as alpha
        actual_h = min(text_tensor.shape[0], y_end - y_start)
        actual_w = min(text_tensor.shape[1], w)
        result[y_start:y_start + actual_h, :actual_w, :] += (
            text_tensor[:actual_h, :actual_w, :] * mask[:actual_h, :actual_w, :]
        )
        result = result.clamp(0, 1)
    except Exception as e:
        logger.debug("[LoadLast] Caption rendering failed: %s", e)

    return result


def format_caption(
    template: str,
    iteration: int = 0,
    timestamp: str = "",
    seed: str = "",
    index: int = 0,
    filename: str = "",
) -> str:
    """
    Format a caption template with available tokens.

    Available tokens:
        {iteration} — monotonic iteration counter
        {timestamp} — ISO timestamp or empty
        {seed}      — seed value or empty
        {index}     — batch index (0-based)
        {filename}  — source filename

    Args:
        template: format string with {token} placeholders
        iteration: current iteration number
        timestamp: formatted timestamp string
        seed: seed value
        index: batch/frame index
        filename: source filename

    Returns:
        Formatted caption string
    """
    try:
        return template.format(
            iteration=iteration,
            timestamp=timestamp,
            seed=seed,
            index=index,
            filename=filename,
        )
    except (KeyError, IndexError, ValueError):
        return template


def render_captions_on_grid(
    grid_image: torch.Tensor,
    captions: list[str],
    cell_width: int,
    cell_height: int,
    columns: int,
    padding: int,
    border: int = 0,
    font_size: int = 12,
    bar_height: int = 20,
) -> torch.Tensor:
    """
    Render captions on individual cells of a grid image.

    Args:
        grid_image: [1, grid_H, grid_W, 3] grid tensor
        captions: list of caption strings per cell
        cell_width: width of each cell in the grid
        cell_height: height of each cell
        columns: number of columns in the grid
        padding: gap between cells
        border: outer border width
        font_size: caption text size
        bar_height: caption bar height

    Returns:
        [1, grid_H, grid_W, 3] tensor with captions burned in
    """
    result = grid_image.squeeze(0).clone()

    for idx, caption in enumerate(captions):
        if not caption:
            continue

        row = idx // columns
        col = idx % columns

        y = border + row * (cell_height + padding)
        x = border + col * (cell_width + padding)

        # Extract cell region
        cell = result[y:y + cell_height, x:x + cell_width, :]
        if cell.numel() == 0:
            continue

        # Render caption on cell
        cell_with_caption = render_caption(
            cell, caption, font_size=font_size,
            bar_height=bar_height, position="bottom"
        )
        result[y:y + cell_height, x:x + cell_width, :] = cell_with_caption

    return result.unsqueeze(0)


def _render_text_pil(text: str, width: int, height: int, font_size: int) -> np.ndarray:
    """
    Render white text on a transparent background using PIL.

    Returns:
        numpy array [H, W, 3] uint8
    """
    img = Image.new('RGB', (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Try to load a monospace font
    font = _get_monospace_font(font_size)

    # Center text vertically, left-aligned with small padding
    x_offset = 6
    y_offset = max(0, (height - font_size) // 2)

    draw.text((x_offset, y_offset), text, fill=(255, 255, 255), font=font)

    return np.array(img)


def _get_monospace_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a monospace font, falling back to PIL default."""
    # Common monospace font paths on Linux
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
        "/usr/share/fonts/noto/NotoSansMono-Regular.ttf",
    ]

    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue

    # Fallback to default
    try:
        return ImageFont.truetype("DejaVuSansMono.ttf", size)
    except (IOError, OSError):
        return ImageFont.load_default()
