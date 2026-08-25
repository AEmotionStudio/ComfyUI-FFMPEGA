"""FFMPEGA Shader skill handler.

Applies GPU shaders via FFmpeg's libplacebo filter, with automatic
fallback to FFmpeg-only filters when libplacebo is unavailable.
"""

from __future__ import annotations

import logging

try:
    from ...core.shader_support import (
        has_libplacebo,
        resolve_shader_path,
        get_fallback_filter,
        build_shader_filter,
        escape_shader_path,
        ALLOWED_SHADER_EXTENSIONS,
    )
    from ...core.sanitize import sanitize_text_param, validate_path
except ImportError:
    from core.shader_support import (
        has_libplacebo,
        resolve_shader_path,
        get_fallback_filter,
        build_shader_filter,
        escape_shader_path,
        ALLOWED_SHADER_EXTENSIONS,
    )
    from core.sanitize import sanitize_text_param, validate_path

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

log = logging.getLogger("ffmpega")


def _f_shader(p: dict) -> object:
    """Apply a GPU shader preset or custom GLSL shader to video.

    Params:
        preset (str):      Built-in preset name (crt, vhs, holographic, etc.)
        custom_path (str): Optional path to a user-provided .glsl file
        intensity (float): Effect intensity 0.0–1.0 (default 1.0)

    When libplacebo is available, uses GPU-accelerated GLSL shaders.
    When unavailable, logs a clear warning and falls back to FFmpeg
    filters that approximate the effect.
    """
    preset = str(p.get("preset", "crt")).lower().strip()
    custom_path = str(p.get("custom_path", "")).strip()
    intensity = float(p.get("intensity", 1.0))
    intensity = max(0.0, min(1.0, intensity))

    if intensity <= 0.0:
        return make_result()

    # ── Resolve shader path ──
    if custom_path:
        # User-provided shader: validate path for security
        try:
            validate_path(custom_path, ALLOWED_SHADER_EXTENSIONS, must_exist=True)
        except Exception as exc:
            log.error("shader: invalid custom_path: %s", exc)
            return make_result()
        shader_path = custom_path
        is_custom = True
    else:
        # Built-in preset
        resolved = resolve_shader_path(preset)
        if resolved is None:
            log.warning(
                "shader: preset '%s' not found — check shaders/ directory. "
                "Available presets can be listed with the shader skill.",
                preset,
            )
            return make_result()
        shader_path = str(resolved)
        is_custom = False

    # ── Check libplacebo capability ──
    if has_libplacebo():
        log.info("shader: applying '%s' via libplacebo (GPU)", preset)
        vf_filters, fc = build_shader_filter(
            shader_path, intensity=intensity,
        )
        if fc:
            return make_result(fc=fc)
        return make_result(vf=vf_filters)
    else:
        # ── Fallback path — clear warning ──
        log.warning(
            "⚠️  shader: libplacebo is NOT available in your FFmpeg build. "
            "GPU shaders require FFmpeg compiled with --enable-libplacebo "
            "--enable-vulkan --enable-libglslang. "
            "Using an FFmpeg-only approximation for '%s'. "
            "The result will be visually similar but not identical. "
            "To enable GPU shaders, install FFmpeg with Vulkan support.",
            preset,
        )

        # Try to get the fallback filter
        if not is_custom:
            fallback = get_fallback_filter(preset)
            if fallback:
                if intensity >= 1.0:
                    return make_result(vf=[fallback])
                else:
                    # Blend fallback with original
                    fc = (
                        f"[0:v]split[orig][fx];"
                        f"[fx]{fallback}[effected];"
                        f"[orig][effected]blend=all_mode=normal"
                        f":all_opacity={intensity}"
                    )
                    return make_result(fc=fc)

        # No fallback for custom shaders
        log.error(
            "shader: no FFmpeg fallback available for custom shader '%s'. "
            "GPU shaders require libplacebo. Install FFmpeg with Vulkan "
            "support to use custom GLSL shaders.",
            custom_path or preset,
        )
        return make_result()


def get_shader_vf_for_mask(preset: str, intensity: float = 1.0) -> str | None:
    """Get a single-string video filter for use in masked compositing.

    Used by auto_mask to apply shader effects via maskedmerge.
    Returns just the filter string (not a HandlerResult).

    Args:
        preset: Shader preset name.
        intensity: Effect intensity (ignored for mask — full effect applied,
                   intensity is controlled by the mask blend).

    Returns:
        FFmpeg video filter string, or None if unavailable.
    """
    resolved = resolve_shader_path(preset)
    if resolved is None:
        return None

    if has_libplacebo():
        escaped = escape_shader_path(str(resolved))
        return f"libplacebo=custom_shader_path={escaped}"
    else:
        # Use fallback for masking
        fallback = get_fallback_filter(preset)
        if fallback:
            log.warning(
                "⚠️  shader '%s' using FFmpeg approximation for masked "
                "overlay (libplacebo unavailable).",
                preset,
            )
            return fallback
        return None
