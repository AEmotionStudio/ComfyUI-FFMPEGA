"""
Video editing operations using FFmpeg subprocess calls.

Provides trim, concat, and metadata extraction for the integrated
edit mode in LoadLastVideo. Uses stream copy for single-segment
trims (instant, lossless) and re-encodes only when concatenating
multiple segments.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class VideoEditError(Exception):
    """Raised when a video edit operation fails."""


@dataclass
class EditSegment:
    """A time range within a video."""
    start: float  # seconds
    end: float    # seconds

    def __post_init__(self) -> None:
        if self.start < 0:
            raise VideoEditError(f"Segment start must be >= 0, got {self.start}")
        if self.end <= self.start:
            raise VideoEditError(
                f"Segment end ({self.end}) must be > start ({self.start})"
            )

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class EditMetadata:
    """Video metadata needed by the edit timeline."""
    duration: float
    fps: float
    width: int
    height: int
    codec: str
    has_audio: bool


def get_edit_metadata(video_path: str) -> EditMetadata:
    """Extract metadata from a video file using ffprobe.

    Returns an EditMetadata with duration, fps, dimensions, codec,
    and whether audio is present.
    """
    if not os.path.isfile(video_path):
        raise VideoEditError(f"Video file not found: {video_path}")

    cmd = [
        "ffprobe", "-v", "error",
        "-show_format", "-show_streams",
        "-print_format", "json",
        video_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            raise VideoEditError(
                f"ffprobe failed: {result.stderr[:200]}"
            )
        data = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        raise VideoEditError("ffprobe timed out")
    except json.JSONDecodeError:
        raise VideoEditError("ffprobe returned invalid JSON")

    # Find video stream
    video_stream = None
    has_audio = False
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and video_stream is None:
            video_stream = stream
        elif stream.get("codec_type") == "audio":
            has_audio = True

    if video_stream is None:
        raise VideoEditError("No video stream found")

    # Parse FPS from r_frame_rate fraction
    fps = 24.0
    rfr = video_stream.get("r_frame_rate", "")
    if "/" in rfr:
        num, den = rfr.split("/")
        if int(den) > 0:
            fps = int(num) / int(den)

    # Duration: try stream, then format
    duration = 0.0
    if video_stream.get("duration"):
        duration = float(video_stream["duration"])
    elif data.get("format", {}).get("duration"):
        duration = float(data["format"]["duration"])

    return EditMetadata(
        duration=duration,
        fps=round(fps, 3),
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        codec=video_stream.get("codec_name", "unknown"),
        has_audio=has_audio,
    )


def trim_video(
    input_path: str,
    start: float,
    end: float,
    output_path: str,
) -> str:
    """Trim a video using stream copy (no re-encode, near-instant).

    Args:
        input_path: Source video file path.
        start: Start time in seconds.
        end: End time in seconds.
        output_path: Destination file path.

    Returns:
        The output_path on success.

    Raises:
        VideoEditError: If FFmpeg fails.
    """
    if not os.path.isfile(input_path):
        raise VideoEditError(f"Input file not found: {input_path}")
    if start < 0:
        start = 0.0
    if end <= start:
        raise VideoEditError(f"End ({end}) must be > start ({start})")

    duration = end - start

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", input_path,
        "-t", f"{duration:.3f}",
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        "-v", "warning",
        output_path,
    ]

    logger.info("[VideoEdit] Trimming %.2f–%.2f → %s", start, end, output_path)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise VideoEditError(
                f"FFmpeg trim failed: {result.stderr[:300]}"
            )
    except subprocess.TimeoutExpired:
        raise VideoEditError("FFmpeg trim timed out")

    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise VideoEditError("FFmpeg produced empty output")

    return output_path


def _trim_reencode(
    input_path: str,
    start: float,
    end: float,
    output_path: str,
) -> str:
    """Trim with re-encoding for frame-accurate cuts (used internally)."""
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", input_path,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-crf", "18",
        "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-v", "warning",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise VideoEditError(f"FFmpeg re-encode trim failed: {result.stderr[:300]}")
    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise VideoEditError("FFmpeg re-encode produced empty output")
    return output_path


def concat_segments(
    input_path: str,
    segments: list[EditSegment],
    output_path: str,
) -> str:
    """Extract and concatenate multiple segments from a video.

    For a single segment, delegates to trim_video (stream copy).
    For multiple segments, extracts each to a temp file and
    concatenates via FFmpeg's concat demuxer with re-encoding.

    Args:
        input_path: Source video file path.
        segments: Ordered list of EditSegment(start, end) pairs.
        output_path: Destination file path.

    Returns:
        The output_path on success.

    Raises:
        VideoEditError: If segments are invalid or FFmpeg fails.
    """
    if not segments:
        raise VideoEditError("No segments provided")
    if not os.path.isfile(input_path):
        raise VideoEditError(f"Input file not found: {input_path}")

    # Validate segments don't overlap and are in order
    for i, seg in enumerate(segments):
        if i > 0 and seg.start < segments[i - 1].end - 0.001:
            raise VideoEditError(
                f"Segment {i} (start={seg.start}) overlaps with "
                f"segment {i-1} (end={segments[i-1].end})"
            )

    # Single segment → stream copy (fast path)
    if len(segments) == 1:
        return trim_video(input_path, segments[0].start, segments[0].end, output_path)

    # Multiple segments → extract each, then concat with re-encode
    tmp_dir = tempfile.mkdtemp(prefix="loadlast_edit_")
    segment_files: list[str] = []

    try:
        # Extract each segment with re-encoding for accurate cuts
        for i, seg in enumerate(segments):
            seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mp4")
            _trim_reencode(input_path, seg.start, seg.end, seg_path)
            segment_files.append(seg_path)

        # Write concat list file
        list_path = os.path.join(tmp_dir, "concat.txt")
        with open(list_path, "w") as f:
            for sf in segment_files:
                # FFmpeg concat demuxer requires escaped paths
                escaped = sf.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        # Concatenate with re-encoding for clean joins
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c:v", "libx264", "-crf", "18",
            "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-v", "warning",
            output_path,
        ]

        logger.info(
            "[VideoEdit] Concatenating %d segments → %s",
            len(segments), output_path,
        )
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise VideoEditError(
                f"FFmpeg concat failed: {result.stderr[:300]}"
            )

        if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            raise VideoEditError("FFmpeg concat produced empty output")

        return output_path

    finally:
        # Clean up temp segment files
        for sf in segment_files:
            try:
                os.unlink(sf)
            except OSError:
                pass
        try:
            list_path_local = os.path.join(tmp_dir, "concat.txt")
            if os.path.exists(list_path_local):
                os.unlink(list_path_local)
            os.rmdir(tmp_dir)
        except OSError:
            pass
