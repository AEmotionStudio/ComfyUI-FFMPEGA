"""Volume adjustment and mute via FFmpeg audio filters.

Applies the ``volume`` filter for level adjustment or strips audio
entirely with ``-an`` for mute.
"""

from __future__ import annotations

import logging

log = logging.getLogger("ffmpega.videoeditor")


def build_audio_filter(volume: float) -> tuple[str | None, bool]:
    """Return an audio filter string and mute flag for the given volume.

    Parameters
    ----------
    volume:
        Volume multiplier (0.0–2.0).  0.0 means mute.

    Returns
    -------
    tuple
        ``(filter_string, is_muted)`` — filter_string is ``None`` if
        volume is 1.0 (no change needed).
    """
    # Clamp
    volume = max(0.0, min(2.0, volume))

    if volume < 0.001:
        return None, True  # mute — caller should use -an

    if abs(volume - 1.0) < 0.01:
        return None, False  # no change

    return f"volume={volume:.3f}", False


def get_audio_args(volume: float) -> list[str]:
    """Return FFmpeg CLI args for the given volume level.

    Examples:
        volume=1.0 → ["-c:a", "copy"]        (passthrough)
        volume=0.0 → ["-an"]                  (mute)
        volume=0.5 → ["-af", "volume=0.500", "-c:a", "aac", "-b:a", "192k"]
    """
    filt, muted = build_audio_filter(volume)

    if muted:
        return ["-an"]

    if filt is None:
        return ["-c:a", "copy"]

    return ["-af", filt, "-c:a", "aac", "-b:a", "192k"]
