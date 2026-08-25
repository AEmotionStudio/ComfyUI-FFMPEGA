"""Handler for the normalcrafter skill (video normal map generation).

Runs NormalCrafter to produce temporally consistent surface normal maps
from input video.  For single-image normals, use the ``marigold`` skill
instead (with ``output_type=normals``).
"""

import logging
import os

log = logging.getLogger("ffmpega")


def _f_normalcrafter(p: dict) -> dict:
    """Execute the normalcrafter skill.

    Args:
        p: Skill parameters dict containing:
            - _input_path: Source video path (required)
            - max_res: Maximum processing resolution (default 1024)
            - window_size: Temporal window size (default 14)
            - process_length: Max frames to process (default -1 = all)
            - target_fps: Target FPS (default -1 = original)
            - seed: Random seed (default 42)

    Returns:
        HandlerResult-compatible dict with 'movie' key pointing to
        the output normal map video.
    """
    input_path = p.get("_input_path")
    max_res = int(p.get("max_res", 1024))
    window_size = int(p.get("window_size", 14))
    process_length = int(p.get("process_length", -1))
    target_fps = int(p.get("target_fps", -1))
    seed = int(p.get("seed", 42))

    # ── Validate inputs ──
    if not input_path or not os.path.isfile(input_path):
        return {
            "error": "normalcrafter requires a valid video input"
        }

    # Check it's a video (not an image)
    ext = os.path.splitext(input_path)[1].lower()
    _video_exts = {
        ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
        ".ts", ".m4v",
    }
    if ext not in _video_exts:
        return {
            "error": f"normalcrafter requires a video input (got '{ext}'). "
                     "For single-image normals, use the 'marigold' skill "
                     "with output_type='normals'."
        }

    # ── Dependency check ──
    try:
        try:
            from core.normalcrafter_synthesizer import run_normalcrafter
        except ImportError:
            from ...core.normalcrafter_synthesizer import run_normalcrafter
    except Exception as exc:
        return {
            "error": f"NormalCrafter is not available: {exc}. "
                     "Install with: pip install --no-deps "
                     "git+https://github.com/Binyr/NormalCrafter.git"
        }

    # ── Run inference ──
    log.info(
        "[normalcrafter] input=%s, max_res=%d, window=%d, seed=%d",
        input_path, max_res, window_size, seed,
    )

    try:
        output_path = run_normalcrafter(
            video_path=input_path,
            max_res=max_res,
            window_size=window_size,
            process_length=process_length,
            target_fps=target_fps,
            seed=seed,
        )
    except Exception as exc:
        log.error("[normalcrafter] Inference failed: %s", exc)
        return {"error": f"NormalCrafter inference failed: {exc}"}

    log.info("[normalcrafter] Output: %s", output_path)

    # Return as movie replacement (like marigold / video_depth)
    return {"movie": output_path}
