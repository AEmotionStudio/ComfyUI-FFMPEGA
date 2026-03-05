import functools
import shutil


@functools.lru_cache(maxsize=None)
def get_ffmpeg_bin() -> str:
    """Resolve the ffmpeg binary path.

    Returns the full path from ``shutil.which`` or falls back to bare
    ``"ffmpeg"`` so callers never receive ``None``.
    """
    return shutil.which("ffmpeg") or "ffmpeg"


@functools.lru_cache(maxsize=None)
def get_ffprobe_bin() -> str:
    """Resolve the ffprobe binary path.

    Returns the full path from ``shutil.which`` or falls back to bare
    ``"ffprobe"`` so callers never receive ``None``.
    """
    return shutil.which("ffprobe") or "ffprobe"
