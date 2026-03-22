"""Text overlay / watermark via FFmpeg drawtext filter.

Supports multiple text overlays, each with configurable content, position,
font size, color, and time range (start/end).
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("ffmpega.videoeditor")


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
        filters.extend(_build_single_drawtext(ov))

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
    """Escape special characters for FFmpeg drawtext.

    FFmpeg drawtext text values inside single quotes require escaping
    backslashes, single quotes, colons, and percent signs.  The correct
    way to embed a literal single quote is to end the quoted context,
    insert an escaped quote, and re-open the quoted context: ``'\\''``.
    """
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "'\\''")
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


def _build_single_drawtext(ov: dict) -> list[str]:
    """Build drawtext filter string(s) from an overlay dict.

    Multi-line text is split into separate drawtext filters (one per line)
    to avoid FFmpeg rendering ``\\n`` as rectangle glyphs.

    Returns a list of drawtext filter strings (one per line of text).
    """
    text = ov.get("text", "").strip()
    if not text:
        return []

    font_size = max(8, int(ov.get("font_size", 48)))
    color = ov.get("color", "white")
    font = ov.get("font")  # user-provided font name/path, or None

    x_expr = _resolve_position(ov.get("x", "center"), "x")
    raw_y = str(ov.get("y", "bottom")).strip().lower()
    base_y_expr = _resolve_position(ov.get("y", "bottom"), "y")

    # Time range enable expression
    enable_expr = ""
    start_time = ov.get("start_time")
    end_time = ov.get("end_time")

    if start_time is not None and end_time is not None:
        try:
            st, et = float(start_time), float(end_time)
            enable_expr = f":enable='between(t,{st:.3f},{et:.3f})'"
        except (ValueError, TypeError):
            pass
    elif start_time is not None:
        try:
            st = float(start_time)
            enable_expr = f":enable='gte(t,{st:.3f})'"
        except (ValueError, TypeError):
            pass
    elif end_time is not None:
        try:
            et = float(end_time)
            enable_expr = f":enable='lte(t,{et:.3f})'"
        except (ValueError, TypeError):
            pass

    # Split multi-line text into individual lines
    lines = text.split("\n")
    # Strip \r from each line (textarea \r\n endings)
    lines = [line.replace("\r", "").rstrip() for line in lines]
    # Remove empty trailing lines
    while lines and not lines[-1]:
        lines.pop()

    if not lines:
        return []

    # Font file — only for actual file paths (e.g. /usr/share/fonts/foo.ttf).
    # CSS generic names like 'sans-serif', 'serif', 'monospace' are ignored
    # since FFmpeg can't resolve them; it uses its default font instead.
    font_part = ""
    if font and ("/" in font or "\\" in font or font.endswith((".ttf", ".otf"))):
        font_part = f":fontfile='{_escape_drawtext(font)}'"

    filters: list[str] = []
    num_lines = len(lines)
    line_spacing = int(font_size * 1.3)  # ~130% line height

    for i, line in enumerate(lines):
        if not line.strip():
            continue  # skip blank lines but count them for spacing

        escaped = _escape_drawtext(line)

        # Compute y offset based on position mode:
        # - bottom/75%: stack upward (last line at base, earlier lines above)
        # - top: stack downward (first line at base, later lines below)
        # - center: center the block vertically
        if num_lines == 1:
            y_expr = base_y_expr
        elif raw_y in ("bottom",) or raw_y.endswith("%"):
            # Bottom-anchored: last line at base_y, earlier lines above
            offset = (num_lines - 1 - i) * line_spacing
            if offset == 0:
                y_expr = base_y_expr
            else:
                y_expr = f"({base_y_expr})-{offset}"
        elif raw_y in ("center", "middle"):
            # Center the block: shift up by half the block height
            half_block = (num_lines - 1) * line_spacing // 2
            offset = i * line_spacing - half_block
            if offset == 0:
                y_expr = base_y_expr
            elif offset > 0:
                y_expr = f"({base_y_expr})+{offset}"
            else:
                y_expr = f"({base_y_expr})-{-offset}"
        else:
            # Top-anchored (default): stack downward
            if i == 0:
                y_expr = base_y_expr
            else:
                y_expr = f"({base_y_expr})+{i * line_spacing}"

        parts = [
            f"drawtext=text='{escaped}'",
            f"fontsize={font_size}",
            f"fontcolor={color}",
            f"x={x_expr}",
            f"y={y_expr}",
        ]

        if font_part:
            parts.append(font_part.lstrip(":"))

        # Shadow for readability
        parts.extend([
            "shadowcolor=black@0.5",
            "shadowx=2",
            "shadowy=2",
        ])

        dt = ":".join(parts)
        if enable_expr:
            dt += enable_expr

        filters.append(dt)

    return filters
