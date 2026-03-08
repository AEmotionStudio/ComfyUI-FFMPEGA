"""Shared FFmpeg/FFprobe binary resolution for videoeditor processing modules.

Centralises the import-with-fallback pattern so individual processing
modules don't each need their own try/except stanza.
"""

from __future__ import annotations

import shutil

try:
    from ...core.bin_paths import get_ffmpeg_bin as _core_ffmpeg
    from ...core.bin_paths import get_ffprobe_bin as _core_ffprobe
except (ImportError, ValueError):
    _core_ffmpeg = None  # type: ignore[assignment]
    _core_ffprobe = None  # type: ignore[assignment]


def get_ffmpeg_bin() -> str:
    """Return the FFmpeg binary path, with shutil.which fallback."""
    if _core_ffmpeg is not None:
        result = _core_ffmpeg()
        if result:
            return result
    return shutil.which("ffmpeg") or "ffmpeg"


def get_ffprobe_bin() -> str:
    """Return the FFprobe binary path, with shutil.which fallback."""
    if _core_ffprobe is not None:
        result = _core_ffprobe()
        if result:
            return result
    return shutil.which("ffprobe") or "ffprobe"
