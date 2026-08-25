"""Combine multiple images into one side-by-side / grid comparison image.

Tensor-only counterpart to ``core/video_compare.py`` — no ffmpeg needed.
Used by ``SaveImageNode`` when more than one source is connected.  Each
source is either an IMAGE tensor (its first frame is used) or an image
file path.  Panels are scaled to a common size and laid out with offsets
from ``core.grid_layout`` (shared with the video path).

Returns a single IMAGE tensor ``(1, H, W, 3)`` float32 in ``[0, 1]``.
"""

from __future__ import annotations

import logging

import numpy as np
import torch
import torch.nn.functional as F

try:
    from .grid_layout import cell_positions, compute_grid
except ImportError:  # pragma: no cover - script/standalone import
    from core.grid_layout import cell_positions, compute_grid  # type: ignore

logger = logging.getLogger("FFMPEGA")

_DEFAULT_BG = (26, 26, 26)


def _load_path(path: str) -> torch.Tensor | None:
    """Load an image file as an ``(H, W, 3)`` float32 tensor in ``[0, 1]``."""
    try:
        from PIL import Image

        img = Image.open(path)
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        else:
            img = img.convert("RGB")
        arr = np.array(img, dtype=np.float32) / 255.0
        return torch.from_numpy(arr)
    except Exception as e:
        logger.warning("image_compare: load failed for %s: %s", path, e)
        return None


def _to_hwc(src) -> torch.Tensor | None:
    """Normalize a source (tensor batch or path) to an ``(H, W, 3)`` tensor."""
    if isinstance(src, str):
        return _load_path(src) if src else None
    if hasattr(src, "shape") and getattr(src, "shape", [0])[0] > 0:
        t = src[0] if src.dim() == 4 else src
        if t.dim() == 2:  # grayscale (H, W) -> (H, W, 3)
            t = t.unsqueeze(-1).repeat(1, 1, 3)
        return t.detach().to(torch.float32).cpu()
    return None


def _scale(img: torch.Tensor, h: int, w: int) -> torch.Tensor:
    """Bilinear resize an ``(H, W, 3)`` tensor to ``(h, w)``."""
    nchw = img.permute(2, 0, 1).unsqueeze(0)
    nchw = F.interpolate(nchw, size=(h, w), mode="bilinear", align_corners=False)
    return nchw.squeeze(0).permute(1, 2, 0).clamp(0, 1)


def _letterbox(img: torch.Tensor, ch: int, cw: int, bg: torch.Tensor) -> torch.Tensor:
    """Fit ``img`` into a ``ch x cw`` cell, preserving aspect, padding with bg."""
    h, w = img.shape[0], img.shape[1]
    scale = min(ch / h, cw / w)
    nh, nw = max(1, int(round(h * scale))), max(1, int(round(w * scale)))
    scaled = _scale(img, nh, nw)
    cell = bg.view(1, 1, 3).expand(ch, cw, 3).clone()
    y0 = (ch - nh) // 2
    x0 = (cw - nw) // 2
    cell[y0:y0 + nh, x0:x0 + nw, :] = scaled
    return cell


def _draw_label(img: torch.Tensor, text: str) -> torch.Tensor:
    """Draw a top-center caption onto an ``(H, W, 3)`` tensor via PIL."""
    text = (text or "").strip()
    if not text:
        return img
    try:
        from PIL import Image, ImageDraw, ImageFont

        h, w = img.shape[0], img.shape[1]
        pil = Image.fromarray(
            (img.clamp(0, 1).numpy() * 255).astype(np.uint8), mode="RGB"
        )
        draw = ImageDraw.Draw(pil, "RGBA")
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", max(12, h // 22))
        except Exception:
            font = ImageFont.load_default()
        try:
            l, t, r, b = draw.textbbox((0, 0), text, font=font)
            tw, th = r - l, b - t
        except Exception:
            tw, th = draw.textsize(text, font=font)
        pad = max(3, th // 3)
        x = (w - tw) // 2
        y = pad
        draw.rectangle(
            [x - pad, y - pad, x + tw + pad, y + th + pad], fill=(0, 0, 0, 128)
        )
        draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)
        arr = np.array(pil, dtype=np.float32) / 255.0
        return torch.from_numpy(arr)
    except Exception as e:
        logger.warning("image_compare: label draw failed: %s", e)
        return img


def combine_images(
    sources: list,
    layout: str = "auto",
    labels: list[str] | None = None,
    gap: int = 4,
    bg_color: tuple[int, int, int] = _DEFAULT_BG,
) -> torch.Tensor | None:
    """Stack ``sources`` into one comparison image tensor ``(1, H, W, 3)``.

    Args mirror :func:`core.video_compare.combine_videos`.  Returns ``None``
    when fewer than 2 valid panels are available.
    """
    gap = max(0, int(gap))
    bg = torch.tensor([c / 255.0 for c in bg_color], dtype=torch.float32)

    panels = [p for p in (_to_hwc(s) for s in sources) if p is not None]
    n = len(panels)
    if n < 2:
        return panels[0].unsqueeze(0) if n == 1 else None

    if labels:
        panels = [
            _draw_label(p, labels[i]) if i < len(labels) else p
            for i, p in enumerate(panels)
        ]

    cols, rows = compute_grid(n, layout)

    if rows == 1:  # single row: scale to common height, edge-to-edge
        common_h = max(p.shape[0] for p in panels)
        scaled = [
            _scale(p, common_h, max(1, int(round(p.shape[1] * common_h / p.shape[0]))))
            for p in panels
        ]
        total_w = sum(p.shape[1] for p in scaled) + gap * (n - 1)
        canvas = bg.view(1, 1, 3).expand(common_h, total_w, 3).clone()
        x = 0
        for p in scaled:
            pw = p.shape[1]
            canvas[:, x:x + pw, :] = p
            x += pw + gap
        return canvas.unsqueeze(0)

    if cols == 1:  # single column: scale to common width
        common_w = max(p.shape[1] for p in panels)
        scaled = [
            _scale(p, max(1, int(round(p.shape[0] * common_w / p.shape[1]))), common_w)
            for p in panels
        ]
        total_h = sum(p.shape[0] for p in scaled) + gap * (n - 1)
        canvas = bg.view(1, 1, 3).expand(total_h, common_w, 3).clone()
        y = 0
        for p in scaled:
            ph = p.shape[0]
            canvas[y:y + ph, :, :] = p
            y += ph + gap
        return canvas.unsqueeze(0)

    # grid: uniform letterboxed cells
    cell_h = max(p.shape[0] for p in panels)
    cell_w = max(p.shape[1] for p in panels)
    positions = cell_positions(cols, rows, cell_w, cell_h, gap)
    total_w = cols * cell_w + gap * (cols - 1)
    total_h = rows * cell_h + gap * (rows - 1)
    canvas = bg.view(1, 1, 3).expand(total_h, total_w, 3).clone()
    for i, p in enumerate(panels):
        x, y = positions[i]
        canvas[y:y + cell_h, x:x + cell_w, :] = _letterbox(p, cell_h, cell_w, bg)
    return canvas.unsqueeze(0)
