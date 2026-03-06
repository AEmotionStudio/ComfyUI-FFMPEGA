"""Handler for the animate_portrait skill (LivePortrait).

Animates a face in the source video/image using motion from a driving video.
"""

import logging
import os
import tempfile

log = logging.getLogger("ffmpega")


def _f_animate_portrait(p: dict) -> dict:
    """Execute the animate_portrait skill.

    Args:
        p: Skill parameters dict containing:
            - _input_path: Source image or video path
            - driving_video: Path to driving video (required)
            - driving_multiplier: Motion intensity scale (default 1.0)
            - relative_motion: Use relative motion transfer (default True)

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

    # ── Validate inputs ──
    if not input_path or not os.path.isfile(input_path):
        return {
            "error": "animate_portrait requires a valid source input "
                     "(image or video)"
        }

    if not driving_video or not os.path.isfile(driving_video):
        return {
            "error": "animate_portrait requires a valid 'driving_video' "
                     "parameter pointing to an existing video file"
        }

    # ── Dependency check ──
    try:
        try:
            from core.liveportrait_synthesizer import animate_portrait
        except ImportError:
            from ..core_compat import get_core_module
            lp = get_core_module("liveportrait_synthesizer")
            animate_portrait = lp.animate_portrait
    except Exception as exc:
        return {
            "error": f"LivePortrait is not available: {exc}. "
                     "Ensure all dependencies are installed."
        }

    # ── Run inference ──
    log.info("[animate_portrait] source=%s, driving=%s, "
             "multiplier=%.2f, relative=%s",
             input_path, driving_video, driving_multiplier, relative_motion)

    try:
        output_path = animate_portrait(
            source_path=input_path,
            driving_path=driving_video,
            driving_multiplier=driving_multiplier,
            relative_motion=relative_motion,
        )
    except Exception as exc:
        log.error("[animate_portrait] Inference failed: %s", exc)
        return {"error": f"LivePortrait inference failed: {exc}"}

    log.info("[animate_portrait] Output: %s", output_path)

    # Return as movie replacement (like lip_sync)
    return {"movie": output_path}
