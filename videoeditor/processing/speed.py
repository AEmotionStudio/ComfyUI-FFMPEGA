"""Per-segment speed change via FFmpeg setpts / atempo filters.

Video speed uses ``setpts=PTS/{speed}``.  Audio uses chained ``atempo``
filters since each instance only supports the range 0.5–2.0.
"""

from __future__ import annotations

import json
import logging
import math

log = logging.getLogger("ffmpega.videoeditor")

# atempo valid range per FFmpeg docs
_ATEMPO_MIN = 0.5
_ATEMPO_MAX = 2.0


def build_speed_filters(
    speed_map_json: str,
    segment_index: int,
) -> tuple[str | None, str | None]:
    """Return (video_filter, audio_filter) strings for a given segment.

    Parameters
    ----------
    speed_map_json:
        JSON ``{segmentIndex: speed}`` mapping.
    segment_index:
        Index of the current segment.

    Returns
    -------
    tuple
        ``(video_filter, audio_filter)`` — either may be ``None`` if
        speed is 1.0 (no change needed).
    """
    speed = _get_speed(speed_map_json, segment_index)
    if speed is None or abs(speed - 1.0) < 0.01:
        return None, None

    # Clamp to sane range
    speed = max(0.1, min(100.0, speed))

    video_filter = f"setpts=PTS/{speed}"
    audio_filter = _build_atempo_chain(speed)

    return video_filter, audio_filter


def _get_speed(speed_map_json: str, segment_index: int) -> float | None:
    """Extract speed for a segment from the JSON map."""
    if not speed_map_json or not speed_map_json.strip():
        return None
    try:
        data = json.loads(speed_map_json)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    # Keys may be strings or ints
    speed_val = data.get(str(segment_index)) or data.get(segment_index)
    if speed_val is None:
        return None

    try:
        return float(speed_val)
    except (ValueError, TypeError):
        return None


def _build_atempo_chain(speed: float) -> str:
    """Build a chained atempo filter for the given speed.

    Since ``atempo`` only supports 0.5–2.0, speeds outside that range
    require chaining multiple instances.

    Examples:
        0.25x → atempo=0.5,atempo=0.5
        4.0x  → atempo=2.0,atempo=2.0
        3.0x  → atempo=2.0,atempo=1.5
    """
    if speed <= 0:
        speed = 0.1

    filters: list[str] = []

    if speed < _ATEMPO_MIN:
        # Need to chain slowdowns
        remaining = speed
        while remaining < _ATEMPO_MIN - 0.001:
            filters.append(f"atempo={_ATEMPO_MIN}")
            remaining /= _ATEMPO_MIN
        filters.append(f"atempo={remaining:.4f}")
    elif speed > _ATEMPO_MAX:
        # Need to chain speedups
        remaining = speed
        while remaining > _ATEMPO_MAX + 0.001:
            filters.append(f"atempo={_ATEMPO_MAX}")
            remaining /= _ATEMPO_MAX
        filters.append(f"atempo={remaining:.4f}")
    else:
        filters.append(f"atempo={speed:.4f}")

    return ",".join(filters)
