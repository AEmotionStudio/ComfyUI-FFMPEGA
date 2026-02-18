"""Shared helper for multi-clip output duration calculation.

Used by _f_fade and _f_fade_to_black to avoid code duplication.
"""

import os

_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}


def _calc_multiclip_duration(p: dict, clip_dur: float, n_extra: int) -> float:
    """Calculate total output duration for a multi-clip pipeline.

    Args:
        p: Skill parameters dict (may contain injected metadata).
        clip_dur: Duration of the primary clip in seconds.
        n_extra: Number of extra inputs (excluding primary).

    Returns:
        Total estimated output duration in seconds.
    """
    n_clips = 1 + n_extra
    xfade_dur = float(p.get("_xfade_duration", 0.0))
    # Use _still_duration (injected by composer) falling back to still_duration (user param)
    still_dur = float(p.get("_still_duration", p.get("still_duration", 4.0)))

    extra_paths = p.get("_extra_input_paths", [])
    if extra_paths and any(
        os.path.splitext(ep)[1].lower() in _VIDEO_EXTS for ep in extra_paths
    ):
        per_extra = clip_dur
    else:
        per_extra = still_dur

    return clip_dur + n_extra * per_extra - (n_clips - 1) * xfade_dur
