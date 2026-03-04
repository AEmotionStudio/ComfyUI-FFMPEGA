import functools
import shutil

@functools.lru_cache(maxsize=None)
def get_ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg")

@functools.lru_cache(maxsize=None)
def get_ffprobe_bin() -> str | None:
    return shutil.which("ffprobe")
