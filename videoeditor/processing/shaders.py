"""Shader support for the video editor export pipeline.

Bridges the core shader_support module into the video editor's
filter chain, parsing JSON state from the ShaderPanel UI.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger("ffmpega.videoeditor")


def has_shader(shader_json: str) -> bool:
    """Check if any shader effect is configured."""
    if not shader_json or not shader_json.strip() or shader_json == "{}":
        return False
    try:
        data = json.loads(shader_json)
        return data.get("preset", "none") != "none"
    except (json.JSONDecodeError, TypeError):
        return False


def get_depth_config(shader_json: str) -> dict:
    """Extract depth configuration from ShaderPanel state JSON.

    Returns:
        Dict with enable_vda, enable_normals, depth_encoder, depth_strength keys.
        All default to safe no-op values if not present.
    """
    try:
        data = json.loads(shader_json)
    except (json.JSONDecodeError, TypeError):
        return {"enable_vda": False, "enable_normals": False, "depth_encoder": "vits", "depth_strength": 1.0}

    return {
        "enable_vda": bool(data.get("enable_vda", False)),
        "enable_normals": bool(data.get("enable_normals", False)),
        "depth_encoder": data.get("depth_encoder", "vits"),
        "depth_strength": float(data.get("depth_strength", 1.0)),
    }


def build_shader_filter(shader_json: str) -> tuple[list[str], str]:
    """Build FFmpeg filters from ShaderPanel state JSON.

    Args:
        shader_json: JSON from the ``_shader`` hidden widget, e.g.
            ``{"preset": "crt", "intensity": 0.8}``

    Returns:
        Tuple of (vf_filters, filter_complex).
        For full intensity, vf_filters is populated.
        For partial intensity, filter_complex blends with original.
    """
    try:
        data = json.loads(shader_json)
    except (json.JSONDecodeError, TypeError):
        return [], ""

    preset = data.get("preset", "none")
    if preset == "none":
        return [], ""

    intensity = float(data.get("intensity", 1.0))
    intensity = max(0.0, min(1.0, intensity))

    if intensity <= 0.0:
        return [], ""

    try:
        from core.shader_support import (
            has_libplacebo,
            resolve_shader_path,
            build_shader_filter as _build_shader,
            get_fallback_filter,
        )
    except ImportError:
        log.warning(
            "[VideoEditor] shader_support module not available — "
            "shader effects require the core module."
        )
        return [], ""

    # Resolve preset to GLSL file
    shader_path = resolve_shader_path(preset)
    if shader_path is None:
        log.warning("[VideoEditor] shader preset '%s' not found.", preset)
        return [], ""

    if has_libplacebo():
        log.info("[VideoEditor] applying shader '%s' via libplacebo (GPU)", preset)
        return _build_shader(str(shader_path), intensity=intensity)
    else:
        # Fallback
        fallback = get_fallback_filter(preset)
        if not fallback:
            log.warning(
                "[VideoEditor] no fallback for shader '%s' and "
                "libplacebo unavailable.",
                preset,
            )
            return [], ""

        log.warning(
            "⚠️  [VideoEditor] libplacebo not available — using FFmpeg "
            "approximation for shader '%s'. Install FFmpeg with Vulkan "
            "support for GPU-accelerated shaders.",
            preset,
        )
        if intensity >= 1.0:
            return [fallback], ""
        else:
            fc = (
                f"[0:v]split[orig][fx];"
                f"[fx]{fallback}[effected];"
                f"[orig][effected]blend=all_mode=normal"
                f":all_opacity={intensity}"
            )
            return [], fc
