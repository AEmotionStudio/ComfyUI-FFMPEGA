"""AI-powered compositing: background removal, depth estimation, depth effects.

Provides FFmpeg filter builders for depth-based effects (bokeh blur, fog)
and orchestration helpers that call the existing rembg/depth infrastructure.
"""

from __future__ import annotations

import json
import logging
import math

log = logging.getLogger("ffmpega.videoeditor")


# ── Background Removal Settings ─────────────────────────────────────

REMBG_MODELS = [
    "bria-rmbg",
    "birefnet-general",
    "birefnet-general-lite",
    "isnet-general-use",
    "u2net",
    "silueta",
]

BACKGROUND_TYPES = ["transparent", "solid", "blur", "image", "video"]


def parse_bg_removal_settings(settings_json: str) -> dict:
    """Parse background removal settings JSON.

    Returns
    -------
    dict with keys: ``enabled``, ``model``, ``background_type``,
    ``background_color``, ``background_path``, ``edge_refine``.
    """
    defaults = {
        "enabled": False,
        "model": "bria-rmbg",
        "background_type": "transparent",
        "background_color": "#000000",
        "background_path": "",
        "edge_refine": 0.5,
        "blur_strength": 15,
    }
    if not settings_json or not settings_json.strip() or settings_json == "{}":
        return defaults
    try:
        data = json.loads(settings_json)
        if not isinstance(data, dict):
            return defaults
        result = {**defaults}
        for key in defaults:
            if key in data:
                result[key] = data[key]
        # Validate model
        if result["model"] not in REMBG_MODELS:
            result["model"] = "bria-rmbg"
        if result["background_type"] not in BACKGROUND_TYPES:
            result["background_type"] = "transparent"
        result["edge_refine"] = max(0.0, min(1.0, float(result["edge_refine"])))
        result["blur_strength"] = max(1, min(50, int(result["blur_strength"])))
        return result
    except (json.JSONDecodeError, TypeError, ValueError):
        return defaults


def has_bg_removal(settings_json: str) -> bool:
    """Quick check if background removal is enabled."""
    settings = parse_bg_removal_settings(settings_json)
    return settings.get("enabled", False)


# ── Depth Effect Settings ───────────────────────────────────────────

DEPTH_MODELS = ["video-depth-anything", "marigold"]

DEPTH_EFFECTS = ["bokeh", "fog", "tilt-shift"]


def parse_depth_settings(settings_json: str) -> dict:
    """Parse depth effect settings JSON.

    Returns
    -------
    dict with keys: ``enabled``, ``model``, ``effect``,
    ``focus_distance`` (0-1), ``blur_amount`` (1-30),
    ``fog_density`` (0-1), ``fog_color``.
    """
    defaults = {
        "enabled": False,
        "model": "video-depth-anything",
        "effect": "bokeh",
        "focus_distance": 0.5,
        "blur_amount": 10,
        "fog_density": 0.5,
        "fog_color": "#cccccc",
        "tilt_shift_center": 0.5,
        "tilt_shift_width": 0.3,
    }
    if not settings_json or not settings_json.strip() or settings_json == "{}":
        return defaults
    try:
        data = json.loads(settings_json)
        if not isinstance(data, dict):
            return defaults
        result = {**defaults}
        for key in defaults:
            if key in data:
                result[key] = data[key]
        if result["model"] not in DEPTH_MODELS:
            result["model"] = "video-depth-anything"
        if result["effect"] not in DEPTH_EFFECTS:
            result["effect"] = "bokeh"
        result["focus_distance"] = max(0.0, min(1.0, float(result["focus_distance"])))
        result["blur_amount"] = max(1, min(30, int(result["blur_amount"])))
        result["fog_density"] = max(0.0, min(1.0, float(result["fog_density"])))
        result["tilt_shift_center"] = max(0.0, min(1.0, float(result["tilt_shift_center"])))
        result["tilt_shift_width"] = max(0.05, min(1.0, float(result["tilt_shift_width"])))
        return result
    except (json.JSONDecodeError, TypeError, ValueError):
        return defaults


def has_depth_effect(settings_json: str) -> bool:
    """Quick check if any depth effect is enabled."""
    settings = parse_depth_settings(settings_json)
    return settings.get("enabled", False)


# ── FFmpeg Filter Builders ──────────────────────────────────────────

def build_bg_blur_filter(blur_strength: int = 15) -> list[str]:
    """Build a background blur composite filter.

    This creates a blurred version of the entire frame.  Actual compositing
    with the foreground mask is done as a separate step using ``alphamerge``
    or overlay.
    """
    strength = max(1, min(50, blur_strength))
    return [f"boxblur={strength}:{strength}"]


def build_depth_bokeh_filter(
    focus_distance: float = 0.5,
    blur_amount: int = 10,
) -> str:
    """Build a depth-based bokeh blur filter.

    Uses ``lensfun`` or ``boxblur`` with a depth-map-based mask.
    Since true depth-aware blur requires per-pixel operations, this
    provides a simplified version using FFmpeg expressions.

    Parameters
    ----------
    focus_distance : float
        0..1 normalized depth, 0=near, 1=far.
    blur_amount : int
        Maximum blur radius.

    Returns
    -------
    str
        FFmpeg filter expression for depth-based blur.
    """
    fd = max(0.0, min(1.0, focus_distance))
    ba = max(1, min(30, blur_amount))
    # Simplified: use a band-pass on Y position to simulate focus plane
    return f"boxblur=luma_radius='if(gt(abs(Y/H-{fd:.2f}),0.15),{ba},0)':luma_power=1"


def build_fog_filter(
    density: float = 0.5,
    color: str = "#cccccc",
) -> list[str]:
    """Build atmospheric fog filter.

    Creates a fog effect by blending with a solid color based on depth.

    Parameters
    ----------
    density : float
        0..1, fog thickness.
    color : str
        Fog color in hex.
    """
    d = max(0.0, min(1.0, density))
    opacity = d * 0.7  # Max 70% fog
    c = _hex_to_rgb(color)
    return [
        f"colorbalance=rs={c[0] * opacity:.3f}:gs={c[1] * opacity:.3f}:bs={c[2] * opacity:.3f}",
    ]


def build_tilt_shift_filter(
    center: float = 0.5,
    width: float = 0.3,
    blur_amount: int = 10,
) -> str:
    """Build tilt-shift (miniature) effect.

    Sharp band at ``center`` with progressive blur above and below.

    Parameters
    ----------
    center : float
        0..1 vertical center of focus band.
    width : float
        0..1 width of sharp band relative to frame height.
    blur_amount : int
        Blur strength outside the band.
    """
    c = max(0.0, min(1.0, center))
    w = max(0.05, min(1.0, width)) / 2.0
    ba = max(1, min(30, blur_amount))

    top = max(0.0, c - w)
    bottom = min(1.0, c + w)

    return (
        f"boxblur=luma_radius="
        f"'if(lt(Y/H,{top:.2f}),{ba}*(1-Y/H/{top:.2f}),if(gt(Y/H,{bottom:.2f}),{ba}*(Y/H-{bottom:.2f})/(1-{bottom:.2f}),0))'"
        f":luma_power=1"
    )


# ── AI Compose State ────────────────────────────────────────────────

def has_ai_compose(ai_compose_json: str) -> bool:
    """Quick check if any AI compositing is configured."""
    if not ai_compose_json or not ai_compose_json.strip() or ai_compose_json == "{}":
        return False
    try:
        data = json.loads(ai_compose_json)
        if not isinstance(data, dict):
            return False
        bg = data.get("bg_removal")
        if isinstance(bg, dict) and bg.get("enabled"):
            return True
        depth = data.get("depth_effect")
        if isinstance(depth, dict) and depth.get("enabled"):
            return True
        return False
    except (json.JSONDecodeError, TypeError):
        return False


def parse_ai_compose(ai_compose_json: str) -> dict:
    """Parse AI compose JSON and return structured settings.

    Returns
    -------
    dict with keys:
        ``bg_removal``: dict (parsed bg removal settings)
        ``depth_effect``: dict (parsed depth effect settings)
    """
    result = {
        "bg_removal": parse_bg_removal_settings("{}"),
        "depth_effect": parse_depth_settings("{}"),
    }
    if not ai_compose_json or not ai_compose_json.strip() or ai_compose_json == "{}":
        return result
    try:
        data = json.loads(ai_compose_json)
        if not isinstance(data, dict):
            return result
        bg = data.get("bg_removal")
        if isinstance(bg, dict):
            result["bg_removal"] = parse_bg_removal_settings(json.dumps(bg))
        depth = data.get("depth_effect")
        if isinstance(depth, dict):
            result["depth_effect"] = parse_depth_settings(json.dumps(depth))
        return result
    except (json.JSONDecodeError, TypeError):
        return result


# ── Helpers ─────────────────────────────────────────────────────────

def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    """Convert hex color to normalized RGB floats (-1 to 1 range for colorbalance)."""
    c = color.strip().lstrip("#")
    if len(c) != 6:
        return (0.0, 0.0, 0.0)
    try:
        r = int(c[0:2], 16) / 255.0 * 2 - 1
        g = int(c[2:4], 16) / 255.0 * 2 - 1
        b = int(c[4:6], 16) / 255.0 * 2 - 1
        return (r, g, b)
    except ValueError:
        return (0.0, 0.0, 0.0)
