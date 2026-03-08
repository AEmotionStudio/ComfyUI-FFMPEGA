"""Shared concat demuxer utility for video segment concatenation.

Used by both the export pipeline and the transitions module to avoid
duplicating the FFmpeg concat demuxer logic.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

try:
    from ...core.bin_paths import get_ffmpeg_bin
except (ImportError, ValueError):
    def get_ffmpeg_bin() -> str:
        return shutil.which("ffmpeg") or "ffmpeg"

log = logging.getLogger("ffmpega.videoeditor")


def concat_segments(
    segment_files: list[str],
    output_path: str,
    *,
    raise_on_error: bool = False,
) -> str:
    """Concatenate video segment files using FFmpeg's concat demuxer.

    Parameters
    ----------
    segment_files:
        Paths to individual segment video files.
    output_path:
        Destination file path.
    raise_on_error:
        If True, raise RuntimeError on concat failure.
        If False, fall back to copying the first segment file.

    Returns
    -------
    str
        *output_path* on success, or first segment file on graceful fallback.
    """
    if not segment_files:
        return output_path
    if len(segment_files) == 1:
        shutil.copy2(segment_files[0], output_path)
        return output_path

    ffmpeg = get_ffmpeg_bin()
    tmp_dir = tempfile.mkdtemp(prefix="ffmpega_concat_")
    try:
        concat_list = os.path.join(tmp_dir, "concat.txt")
        with open(concat_list, "w") as f:
            for sf in segment_files:
                f.write(f"file '{sf}'\n")

        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c", "copy",
            "-v", "warning",
            output_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            msg = f"Concat failed (rc={result.returncode}): {result.stderr[:300]}"
            if raise_on_error:
                raise RuntimeError(msg)
            log.warning("[VideoEditor] %s", msg)
            if segment_files:
                shutil.copy2(segment_files[0], output_path)

        return output_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
