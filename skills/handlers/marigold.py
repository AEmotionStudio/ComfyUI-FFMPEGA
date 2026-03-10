"""Handler for the marigold skill (dense vision analysis).

Runs Marigold depth, normals, or intrinsic image decomposition on the
input image/video.
"""

import logging
import os

log = logging.getLogger("ffmpega")


def _f_marigold(p: dict) -> dict:
    """Execute the marigold skill.

    Args:
        p: Skill parameters dict containing:
            - _input_path: Source image or video path
            - output_type: One of depth/normals/appearance/lighting (required)
            - num_steps: Denoising steps (default 4)
            - ensemble_size: Ensemble predictions (default 1)

    Returns:
        HandlerResult-compatible dict with 'movie' key pointing to
        the output file.
    """
    input_path = p.get("_input_path")
    output_type = p.get("output_type", "depth")
    num_steps = int(p.get("num_steps", 4))
    ensemble_size = int(p.get("ensemble_size", 1))

    # ── Validate inputs ──
    if not input_path or not os.path.isfile(input_path):
        return {
            "error": "marigold requires a valid source input "
                     "(image or video)"
        }

    valid_types = ("depth", "normals", "appearance", "lighting")
    if output_type not in valid_types:
        return {
            "error": f"marigold output_type must be one of {valid_types}, "
                     f"got '{output_type}'"
        }

    # ── Dependency check ──
    try:
        try:
            from core.marigold_synthesizer import run_marigold
        except ImportError:
            from ...core.marigold_synthesizer import run_marigold
    except Exception as exc:
        return {
            "error": f"Marigold is not available: {exc}. "
                     "Ensure diffusers >= 0.28.0 is installed."
        }

    # ── Run inference ──
    log.info("[marigold] input=%s, type=%s, steps=%d, ensemble=%d",
             input_path, output_type, num_steps, ensemble_size)

    try:
        output_path = run_marigold(
            input_path=input_path,
            output_type=output_type,
            num_steps=num_steps,
            ensemble_size=ensemble_size,
        )
    except Exception as exc:
        log.error("[marigold] Inference failed: %s", exc)
        return {"error": f"Marigold inference failed: {exc}"}

    log.info("[marigold] Output: %s", output_path)

    # Return as movie replacement (like animate_portrait / lip_sync)
    return {"movie": output_path}
