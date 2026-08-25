"""Handler for the animate_portrait skill (LivePortrait).

Animates a face in the source video/image using motion from a driving video,
or using expression sliders alone (no driving video required).
"""

import logging
import os
import tempfile

log = logging.getLogger("ffmpega")

# Expression parameter names (for extraction from skill params dict)
_EXPR_PARAMS = (
    "rotate_pitch", "rotate_yaw", "rotate_roll",
    "blink", "eyebrow", "wink",
    "pupil_x", "pupil_y",
    "aaa", "eee", "woo", "smile",
)

# Retargeting + crop params
_EXTRA_PARAMS = ("retargeting_eyes", "retargeting_mouth", "crop_factor")


def _f_animate_portrait(p: dict) -> dict:
    """Execute the animate_portrait skill.

    Args:
        p: Skill parameters dict containing:
            - _input_path: Source image or video path
            - driving_video: Path to driving video (optional if expression sliders set)
            - driving_multiplier: Motion intensity scale (default 1.0)
            - relative_motion: Use relative motion transfer (default True)
            - rotate_pitch/yaw/roll: Head rotation overrides
            - blink, eyebrow, wink, pupil_x/y: Eye expression controls
            - aaa, eee, woo, smile: Mouth expression controls
            - retargeting_eyes/mouth: Retargeting intensity (0-1)
            - crop_factor: Face crop expansion factor

    Returns:
        HandlerResult-compatible dict with 'movie' key pointing to
        the animated output video.
    """
    input_path = p.get("_input_path")
    driving_video = p.get("driving_video", "")
    driving_multiplier = float(p.get("driving_multiplier", 1.0))
    relative_motion = p.get("relative_motion", True)
    if isinstance(relative_motion, str):
        relative_motion = relative_motion.lower() in ("true", "1", "yes")

    # Extract expression parameters
    expr_kwargs = {}
    for name in _EXPR_PARAMS:
        val = p.get(name, 0.0)
        try:
            expr_kwargs[name] = float(val)
        except (TypeError, ValueError):
            expr_kwargs[name] = 0.0

    # Extract retargeting + crop params
    retargeting_eyes = float(p.get("retargeting_eyes", 1.0))
    retargeting_mouth = float(p.get("retargeting_mouth", 1.0))
    crop_factor = float(p.get("crop_factor", 1.6))

    has_expr = any(v != 0.0 for v in expr_kwargs.values())
    has_driving = driving_video and os.path.isfile(driving_video)

    # ── Validate inputs ──
    if not input_path or not os.path.isfile(input_path):
        return {
            "error": "animate_portrait requires a valid source input "
                     "(image or video)"
        }

    if not has_driving and not has_expr:
        return {
            "error": "animate_portrait requires either a 'driving_video' "
                     "or at least one expression parameter to be set"
        }

    # ── Dependency check ──
    try:
        try:
            from core.liveportrait_synthesizer import (
                animate_portrait, animate_portrait_static,
            )
        except ImportError:
            from ..core_compat import get_core_module
            lp = get_core_module("liveportrait_synthesizer")
            animate_portrait = lp.animate_portrait
            animate_portrait_static = lp.animate_portrait_static
    except Exception as exc:
        return {
            "error": f"LivePortrait is not available: {exc}. "
                     "Ensure all dependencies are installed."
        }

    # ── Run inference ──
    try:
        if has_driving:
            # Driving video mode (with optional expression overrides)
            log.info("[animate_portrait] source=%s, driving=%s, "
                     "multiplier=%.2f, relative=%s, has_expr=%s",
                     input_path, driving_video, driving_multiplier,
                     relative_motion, has_expr)
            output_path = animate_portrait(
                source_path=input_path,
                driving_path=driving_video,
                driving_multiplier=driving_multiplier,
                relative_motion=relative_motion,
                retargeting_eyes=retargeting_eyes,
                retargeting_mouth=retargeting_mouth,
                crop_factor=crop_factor,
                **expr_kwargs,
            )
        else:
            # Static mode (expression sliders only, no driving video)
            log.info("[animate_portrait] source=%s, static mode "
                     "(expression sliders only)", input_path)
            output_path = animate_portrait_static(
                source_path=input_path,
                crop_factor=crop_factor,
                **expr_kwargs,
            )
    except Exception as exc:
        log.error("[animate_portrait] Inference failed: %s", exc)
        return {"error": f"LivePortrait inference failed: {exc}"}

    log.info("[animate_portrait] Output: %s", output_path)

    # Return as movie replacement (like lip_sync)
    return {"movie": output_path}
