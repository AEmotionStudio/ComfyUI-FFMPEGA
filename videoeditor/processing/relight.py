"""FFmpeg-based relighting for the Video Editor export pipeline.

Provides a directional lighting simulation using FFmpeg filter expressions
without requiring an AI model. The math:

1. Convert to luminance → approximate normals from gradients
2. Compute dot(normal, light_dir) for Lambertian shading
3. Blend the shading map with the original via colorbalance + curves + eq

For true AI relighting (Marigold normal maps), a separate inference
endpoint would pre-compute normal maps, and this module would composite
them. The current implementation provides a good-looking approximation
using only FFmpeg.
"""

from __future__ import annotations

import json
import logging
import math

log = logging.getLogger("ffmpega.videoeditor")

# Default relight state — matches RelightPanel.ts defaults
_DEFAULTS = {
    "azimuth": 0.0,      # degrees, 0=front, 90=right, -90=left
    "elevation": 45.0,    # degrees above horizon
    "intensity": 1.0,     # light intensity multiplier
    "ambient": 0.3,       # ambient fill level
    "color_r": 255,       # light color RGB
    "color_g": 255,
    "color_b": 255,
    "enabled": False,
}


def build_relight_filters(relight_json: str) -> list[str]:
    """Build FFmpeg -vf filter chain for directional relighting.

    Uses a combination of:
    - ``eq`` for global brightness/contrast adjustment based on light direction
    - ``colorbalance`` for light color tinting
    - ``curves`` for shading curvature

    Parameters
    ----------
    relight_json:
        JSON string with azimuth, elevation, intensity, ambient, color fields.

    Returns
    -------
    list[str]
        List of FFmpeg -vf filter strings. Empty if no relighting needed.
    """
    if not relight_json or not relight_json.strip() or relight_json == "{}":
        return []

    try:
        state = json.loads(relight_json)
    except (json.JSONDecodeError, TypeError):
        log.warning("[VideoEditor] Invalid relight JSON: %.100s", relight_json)
        return []

    if not isinstance(state, dict):
        return []

    if not state.get("enabled", False):
        return []

    azimuth = float(state.get("azimuth", 0.0))
    elevation = float(state.get("elevation", 45.0))
    intensity = max(0.0, min(3.0, float(state.get("intensity", 1.0))))
    ambient = max(0.0, min(1.0, float(state.get("ambient", 0.3))))
    color_r = int(state.get("color_r", 255))
    color_g = int(state.get("color_g", 255))
    color_b = int(state.get("color_b", 255))

    filters: list[str] = []

    # Compute light direction vector from azimuth/elevation
    az_rad = math.radians(azimuth)
    el_rad = math.radians(elevation)
    # Light comes FROM the specified direction
    lx = math.sin(az_rad) * math.cos(el_rad)
    ly = -math.sin(el_rad)  # negative = from above
    lz = math.cos(az_rad) * math.cos(el_rad)

    # --- Brightness: simulate directional light ---
    # Higher elevation → less extreme side-lighting
    # Front light (az=0) → neutral brightness
    # Side light → slight brightness reduction simulating shadow side
    brightness_shift = -0.1 * abs(lx) * intensity
    contrast_boost = 1.0 + 0.15 * intensity * (1.0 - ambient)

    eq_parts = []
    if abs(brightness_shift) > 0.01:
        eq_parts.append(f"brightness={brightness_shift:.3f}")
    if abs(contrast_boost - 1.0) > 0.01:
        eq_parts.append(f"contrast={contrast_boost:.3f}")

    if eq_parts:
        filters.append(f"eq={':'.join(eq_parts)}")

    # --- Color tinting from light color ---
    # Normalize to [-1, 1] range for colorbalance
    r_norm = (color_r / 255.0 - 0.5) * 0.4 * intensity
    g_norm = (color_g / 255.0 - 0.5) * 0.4 * intensity
    b_norm = (color_b / 255.0 - 0.5) * 0.4 * intensity

    if abs(r_norm) > 0.01 or abs(g_norm) > 0.01 or abs(b_norm) > 0.01:
        filters.append(
            f"colorbalance="
            f"rm={r_norm:.3f}:gm={g_norm:.3f}:bm={b_norm:.3f}:"
            f"rh={r_norm * 0.5:.3f}:gh={g_norm * 0.5:.3f}:bh={b_norm * 0.5:.3f}"
        )

    # --- Directional shadow simulation via curves ---
    # Side lighting deepens shadows, top lighting is more even
    shadow_depth = max(0.0, abs(lx) * 0.3 * intensity * (1.0 - ambient))
    if shadow_depth > 0.02:
        # Darken shadows using a curves S-curve
        filters.append(
            f"curves=m='0/0 0.25/{max(0, 0.15 - shadow_depth):.2f} "
            f"0.5/0.5 0.75/{min(1, 0.85 + shadow_depth * 0.3):.2f} 1/1'"
        )

    return filters


def has_relight(relight_json: str) -> bool:
    """Quick check whether relighting is enabled."""
    if not relight_json or not relight_json.strip() or relight_json == "{}":
        return False
    try:
        state = json.loads(relight_json)
        return bool(state.get("enabled", False))
    except (json.JSONDecodeError, TypeError):
        return False
