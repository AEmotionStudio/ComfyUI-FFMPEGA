"""Segment-based trim and splice via FFmpeg.

Each segment becomes a separate trim operation.  When no re-encoding filters
(crop, speed, text) are required, segments are extracted with stream-copy
for near-instant performance.  Otherwise segments are re-encoded with
libx264 CRF 18.

Segments are concatenated via the FFmpeg concat demuxer.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile

try:
    from ...core.bin_paths import get_ffmpeg_bin
except (ImportError, ValueError):
    import shutil
    def get_ffmpeg_bin() -> str:
        return shutil.which("ffmpeg") or "ffmpeg"

log = logging.getLogger("ffmpega.videoeditor")


def trim_segments(
    source_path: str,
    segments_json: str,
    output_path: str,
    *,
    stream_copy: bool = True,
) -> str:
    """Extract and concatenate segments from *source_path*.

    Parameters
    ----------
    source_path:
        Path to the source video file.
    segments_json:
        JSON string of ``[[start, end], ...]`` pairs (seconds).
    output_path:
        Destination file path for the concatenated result.
    stream_copy:
        When ``True`` (default) and no re-encoding is needed, use
        ``-c copy`` for a fast path.  Set to ``False`` when the caller
        will chain additional filters that require re-encoding.

    Returns
    -------
    str
        The *output_path* on success.
    """
    segments = _parse_segments(segments_json)
    if not segments:
        return source_path  # nothing to trim

    ffmpeg = get_ffmpeg_bin()
    tmp_dir = tempfile.mkdtemp(prefix="ffmpega_trim_")

    try:
        seg_files: list[str] = []

        for idx, (start, end) in enumerate(segments):
            seg_out = os.path.join(tmp_dir, f"seg_{idx:04d}.mp4")
            duration = end - start
            if duration <= 0:
                continue

            cmd: list[str] = [ffmpeg, "-y"]

            if stream_copy:
                # Fast seek + stream copy
                cmd += ["-ss", f"{start:.6f}", "-i", source_path]
                cmd += ["-t", f"{duration:.6f}"]
                cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
            else:
                # Precise seek with re-encode
                cmd += ["-ss", f"{start:.6f}", "-i", source_path]
                cmd += ["-t", f"{duration:.6f}"]
                cmd += [
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k",
                ]

            cmd += ["-v", "warning", seg_out]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                log.warning(
                    "[VideoEditor] Trim segment %d failed: %s",
                    idx, result.stderr[:300],
                )
                continue

            seg_files.append(seg_out)

        if not seg_files:
            return source_path

        if len(seg_files) == 1:
            # Single segment — just move it
            os.replace(seg_files[0], output_path)
            return output_path

        # Concat via demuxer file list
        concat_list = os.path.join(tmp_dir, "concat.txt")
        with open(concat_list, "w") as f:
            for sf in seg_files:
                f.write(f"file '{sf}'\n")

        concat_cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c", "copy",
            "-v", "warning",
            output_path,
        ]
        result = subprocess.run(
            concat_cmd, capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            log.warning(
                "[VideoEditor] Concat failed: %s", result.stderr[:300],
            )
            return source_path

        return output_path

    finally:
        # Clean up temp segment files
        _cleanup_dir(tmp_dir)


def _parse_segments(segments_json: str) -> list[tuple[float, float]]:
    """Parse a JSON segments string into a list of (start, end) tuples."""
    try:
        raw = json.loads(segments_json)
    except (json.JSONDecodeError, TypeError):
        return []

    result: list[tuple[float, float]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            start, end = float(item[0]), float(item[1])
            if end > start:
                result.append((start, end))
    return result


def _cleanup_dir(path: str) -> None:
    """Remove a temporary directory and its contents, ignoring errors."""
    import shutil
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass
