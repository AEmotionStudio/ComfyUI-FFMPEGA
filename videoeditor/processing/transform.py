"""Transform filters for position, scale, rotation, flip, opacity.

Builds FFmpeg ``-vf`` filter chains for spatial transforms.
"""

from __future__ import annotations

import json
import logging
import math

log = logging.getLogger("ffmpega.videoeditor")


def build_transform_filter(params: dict) -> list[str]:
    """Build FFmpeg filter chain for spatial transforms.

    Parameters
    ----------
    params : dict
        Keys: ``enabled``, ``position_x``, ``position_y``,
        ``scale`` (%), ``rotation`` (degrees), ``flip_h``, ``flip_v``,
        ``opacity`` (0-100).

    Returns
    -------
    list[str]
        Filter strings to chain.  Empty if disabled.
    """
    if not params.get("enabled"):
        return []

    filters: list[str] = []

    # Scale
    scale_pct = max(10, min(400, params.get("scale", 100)))
    if scale_pct != 100:
        factor = scale_pct / 100.0
        filters.append(f"scale=iw*{factor:.3f}:ih*{factor:.3f}")

    # Rotation
    rotation = params.get("rotation", 0)
    if rotation != 0:
        # FFmpeg rotate uses radians
        radians = rotation * math.pi / 180.0
        filters.append(
            f"rotate={radians:.4f}:ow=rotw({radians:.4f}):oh=roth({radians:.4f}):fillcolor=none"
        )

    # Flip
    if params.get("flip_h"):
        filters.append("hflip")
    if params.get("flip_v"):
        filters.append("vflip")

    # Position (pad + offset)
    pos_x = params.get("position_x", 0)
    pos_y = params.get("position_y", 0)
    if pos_x != 0 or pos_y != 0:
        # Use pad to create canvas, then crop to original size at offset
        # This effectively translates the content
        filters.append(
            f"pad=iw+abs({pos_x})*2:ih+abs({pos_y})*2:"
            f"{max(0, pos_x)}+abs({pos_x}):{max(0, pos_y)}+abs({pos_y}):"
            f"color=black@0"
        )

    # Opacity
    opacity = max(0, min(100, params.get("opacity", 100)))
    if opacity < 100:
        alpha = opacity / 100.0
        filters.append(f"format=rgba,colorchannelmixer=aa={alpha:.2f}")

    return filters


def has_transform(transform_json: str) -> bool:
    """Quick check if any transform is configured."""
    if not transform_json or not transform_json.strip() or transform_json == "{}":
        return False
    try:
        data = json.loads(transform_json)
        if not isinstance(data, dict):
            return False
        return bool(data.get("enabled"))
    except (json.JSONDecodeError, TypeError):
        return False


def parse_transform(transform_json: str) -> dict:
    """Parse transform JSON.

    Returns
    -------
    dict with all transform fields with defaults applied.
    """
    defaults = {
        "enabled": False,
        "position_x": 0,
        "position_y": 0,
        "scale": 100,
        "rotation": 0,
        "anchor_x": 50,
        "anchor_y": 50,
        "flip_h": False,
        "flip_v": False,
        "opacity": 100,
    }
    if not transform_json or not transform_json.strip() or transform_json == "{}":
        return defaults
    try:
        data = json.loads(transform_json)
        if not isinstance(data, dict):
            return defaults
        result = {**defaults}
        for key in defaults:
            if key in data:
                result[key] = data[key]
        result["scale"] = max(10, min(400, result["scale"]))
        result["rotation"] = max(-180, min(180, result["rotation"]))
        result["opacity"] = max(0, min(100, result["opacity"]))
        return result
    except (json.JSONDecodeError, TypeError):
        return defaults
