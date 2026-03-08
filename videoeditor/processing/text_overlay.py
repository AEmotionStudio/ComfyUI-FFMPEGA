"""Text overlay / watermark via FFmpeg drawtext filter.

Supports multiple text overlays, each with configurable content, position,
font size, color, and time range (start/end).
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("ffmpega.videoeditor")

# Default font — system sans-serif fallback
_DEFAULT_FONT = "/usr/share/fonts/TTF/DejaVuSans.ttf"


def build_drawtext_filters(overlays_json: str) -> list[str]:
    """Parse text overlay config and return a list of drawtext filter strings.

    Parameters
    ----------
    overlays_json:
        JSON array of overlay objects::

            [
                {
                    "text": "Hello World",
                    "x": "center",        // or pixel value
                    "y": "bottom",        // or pixel value
                    "font_size": 48,
                    "color": "white",
                    "start_time": 0.0,    // optional
                    "end_time": null,     // optional, null = end of video
                    "font": null          // optional, path to .ttf
                },
                ...
            ]

    Returns
    -------
    list[str]
        List of drawtext filter strings.  Empty if no valid overlays.
    """
    overlays = _parse_overlays(overlays_json)
    if not overlays:
        return []

    filters: list[str] = []
    for ov in overlays:
        f = _build_single_drawtext(ov)
        if f:
            filters.append(f)

    return filters


def _parse_overlays(overlays_json: str) -> list[dict]:
    """Parse the JSON overlay config."""
    if not overlays_json or not overlays_json.strip():
        return []
    try:
        data = json.loads(overlays_json)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(data, list):
        return []

    return [item for item in data if isinstance(item, dict) and item.get("text")]


def _escape_drawtext(text: str) -> str:
    """Escape special characters for FFmpeg drawtext."""
    # FFmpeg drawtext requires escaping: \, ', :, %
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "'\\\\\\''")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    return text


def _resolve_position(value, axis: str) -> str:
    """Convert a position value to an FFmpeg expression.

    Supports named positions (center, top, bottom, left, right) or
    raw pixel values.
    """
    if isinstance(value, (int, float)):
        return str(int(value))

    value = str(value).strip().lower()

    if axis == "x":
        if value in ("center", "middle"):
            return "(w-text_w)/2"
        if value in ("left",):
            return "20"
        if value in ("right",):
            return "w-text_w-20"
        try:
            return str(int(value))
        except ValueError:
            return "(w-text_w)/2"  # fallback center

    if axis == "y":
        if value in ("center", "middle"):
            return "(h-text_h)/2"
        if value in ("top",):
            return "20"
        if value in ("bottom",):
            return "h-text_h-20"
        try:
            return str(int(value))
        except ValueError:
            return "h-text_h-20"  # fallback bottom

    return "0"


def _build_single_drawtext(ov: dict) -> str | None:
    """Build a single drawtext filter string from an overlay dict."""
    text = ov.get("text", "").strip()
    if not text:
        return None

    escaped = _escape_drawtext(text)
    font_size = max(8, int(ov.get("font_size", 48)))
    color = ov.get("color", "white")
    font = ov.get("font") or _DEFAULT_FONT

    x_expr = _resolve_position(ov.get("x", "center"), "x")
    y_expr = _resolve_position(ov.get("y", "bottom"), "y")

    parts = [
        f"drawtext=text='{escaped}'",
        f"fontsize={font_size}",
        f"fontcolor={color}",
        f"x={x_expr}",
        f"y={y_expr}",
    ]

    # Optional font file
    if font and font != _DEFAULT_FONT:
        parts.append(f"fontfile='{font}'")

    # Time range (enable between start and end)
    start_time = ov.get("start_time")
    end_time = ov.get("end_time")

    if start_time is not None and end_time is not None:
        try:
            st = float(start_time)
            et = float(end_time)
            parts.append(
                f"enable='between(t,{st:.3f},{et:.3f})'"
            )
        except (ValueError, TypeError):
            pass
    elif start_time is not None:
        try:
            st = float(start_time)
            parts.append(f"enable='gte(t,{st:.3f})'")
        except (ValueError, TypeError):
            pass
    elif end_time is not None:
        try:
            et = float(end_time)
            parts.append(f"enable='lte(t,{et:.3f})'")
        except (ValueError, TypeError):
            pass

    # Add subtle shadow for readability
    parts.append("shadowcolor=black@0.5")
    parts.append("shadowx=2")
    parts.append("shadowy=2")

    return ":".join(parts)
