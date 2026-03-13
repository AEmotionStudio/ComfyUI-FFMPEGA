"""Color grading filter builder for the Video Editor export pipeline.

Converts a JSON state object from ``ColorGradingPanel.ts`` into an FFmpeg
``-vf`` filter chain using ``eq``, ``colorbalance``, and ``colortemperature``
filters.

All parameters are checked against their defaults so that an unmodified
grading state returns an empty list (no re-encode needed).
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("ffmpega.videoeditor")

# Default values — must match ColorGradingPanel.ts defaults exactly
_DEFAULTS = {
    "brightness": 0.0,
    "contrast": 1.0,
    "saturation": 1.0,
    "exposure": 0.0,
    "gamma": 1.0,
    "shadows_r": 0.0,
    "shadows_g": 0.0,
    "shadows_b": 0.0,
    "midtones_r": 0.0,
    "midtones_g": 0.0,
    "midtones_b": 0.0,
    "temperature": 6500,
}

# Tolerance for floating-point comparison
_EPS = 0.01
_TEMP_EPS = 50  # Temperature tolerance in Kelvin


def build_color_grading_filters(grading_json: str) -> list[str]:
    """Parse *grading_json* and return a list of FFmpeg ``-vf`` filter strings.

    Returns an empty list when all values are at their defaults (skip
    the re-encode step).

    Parameters
    ----------
    grading_json:
        JSON string from the ``_color_grading`` hidden widget, e.g.
        ``{"brightness": 0.2, "contrast": 1.1, ...}``.

    Returns
    -------
    list[str]
        One or more FFmpeg video-filter strings, e.g.
        ``["eq=brightness=0.2:contrast=1.1:saturation=1.3:gamma=1.0",
          "colorbalance=rs=0.1:gs=0.0:bs=-0.1:rm=0.0:gm=0.0:bm=0.0"]``.
    """
    if not grading_json or not grading_json.strip() or grading_json == "{}":
        return []

    try:
        state = json.loads(grading_json)
    except (json.JSONDecodeError, TypeError):
        log.warning("[VideoEditor] Invalid color grading JSON: %.100s", grading_json)
        return []

    if not isinstance(state, dict):
        return []

    filters: list[str] = []

    # ── eq filter (brightness, contrast, saturation, gamma, exposure) ──
    eq_parts: list[str] = []

    brightness = float(state.get("brightness", _DEFAULTS["brightness"]))
    exposure = float(state.get("exposure", _DEFAULTS["exposure"]))
    # Exposure is mapped to eq brightness additively: total_brightness = brightness + exposure * 0.1
    total_brightness = brightness + exposure * 0.1
    if abs(total_brightness) > _EPS:
        eq_parts.append(f"brightness={total_brightness:.4f}")

    contrast = float(state.get("contrast", _DEFAULTS["contrast"]))
    if abs(contrast - 1.0) > _EPS:
        eq_parts.append(f"contrast={contrast:.4f}")

    saturation = float(state.get("saturation", _DEFAULTS["saturation"]))
    if abs(saturation - 1.0) > _EPS:
        eq_parts.append(f"saturation={saturation:.4f}")

    gamma = float(state.get("gamma", _DEFAULTS["gamma"]))
    if abs(gamma - 1.0) > _EPS:
        eq_parts.append(f"gamma={gamma:.4f}")

    if eq_parts:
        filters.append("eq=" + ":".join(eq_parts))

    # ── colorbalance filter (shadows R/G/B, midtones R/G/B) ──
    cb_parts: list[str] = []

    for key, ffmpeg_key in [
        ("shadows_r", "rs"),
        ("shadows_g", "gs"),
        ("shadows_b", "bs"),
        ("midtones_r", "rm"),
        ("midtones_g", "gm"),
        ("midtones_b", "bm"),
    ]:
        val = float(state.get(key, _DEFAULTS[key]))
        if abs(val) > _EPS:
            cb_parts.append(f"{ffmpeg_key}={val:.4f}")

    if cb_parts:
        filters.append("colorbalance=" + ":".join(cb_parts))

    # ── colortemperature filter ──
    temperature = int(state.get("temperature", _DEFAULTS["temperature"]))
    if abs(temperature - 6500) > _TEMP_EPS:
        filters.append(f"colortemperature=temperature={temperature}")

    return filters


def has_color_grading(grading_json: str) -> bool:
    """Quick check whether the grading JSON contains any non-default values."""
    return bool(build_color_grading_filters(grading_json))
