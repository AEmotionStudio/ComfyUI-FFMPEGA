"""Tests for processing/video_edit.py — trim, concat, and metadata."""

from __future__ import annotations

import os
import sys
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from loadlast.processing.video_edit import (
    EditSegment,
    VideoEditError,
    concat_segments,
    get_edit_metadata,
    trim_video,
)


# ─── Helpers ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def generated_video() -> str:
    """Generate a 4-second test video using FFmpeg."""
    path = os.path.join(tempfile.gettempdir(), "test_edit_source.mp4")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        "color=c=blue:s=320x240:d=4:r=25",
        "-f", "lavfi", "-i",
        "sine=frequency=440:duration=4:sample_rate=44100",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "64k",
        "-pix_fmt", "yuv420p",
        "-v", "warning",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"Test video generation failed: {result.stderr}"
    assert os.path.getsize(path) > 0
    return path


def _get_duration(path: str) -> float:
    """Get video duration via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return float(result.stdout.strip())


# ─── EditSegment tests ─────────────────────────────────────────────────

class TestEditSegment:
    def test_valid_segment(self):
        seg = EditSegment(start=1.0, end=3.0)
        assert seg.duration == 2.0

    def test_negative_start_raises(self):
        with pytest.raises(VideoEditError, match="start must be"):
            EditSegment(start=-1.0, end=2.0)

    def test_end_before_start_raises(self):
        with pytest.raises(VideoEditError, match="end.*must be"):
            EditSegment(start=3.0, end=1.0)

    def test_equal_start_end_raises(self):
        with pytest.raises(VideoEditError, match="end.*must be"):
            EditSegment(start=2.0, end=2.0)


# ─── get_edit_metadata tests ──────────────────────────────────────────

class TestGetEditMetadata:
    def test_valid_video(self, generated_video):
        meta = get_edit_metadata(generated_video)
        assert meta.duration > 3.5
        assert meta.fps > 20
        assert meta.width == 320
        assert meta.height == 240
        assert meta.has_audio is True
        assert meta.codec in ("h264", "libx264")

    def test_missing_file(self):
        with pytest.raises(VideoEditError, match="not found"):
            get_edit_metadata("/nonexistent/video.mp4")


# ─── trim_video tests ────────────────────────────────────────────────

class TestTrimVideo:
    def test_basic_trim(self, generated_video):
        out = os.path.join(tempfile.gettempdir(), "test_trim_out.mp4")
        result = trim_video(generated_video, 1.0, 3.0, out)
        assert result == out
        assert os.path.exists(out)
        dur = _get_duration(out)
        # Stream copy cuts at keyframes, so allow wider tolerance
        assert 1.0 < dur < 3.5, f"Expected ~2s (stream copy), got {dur}"
        os.unlink(out)

    def test_trim_full_range(self, generated_video):
        out = os.path.join(tempfile.gettempdir(), "test_trim_full.mp4")
        result = trim_video(generated_video, 0.0, 4.0, out)
        assert result == out
        dur = _get_duration(out)
        assert dur > 3.5
        os.unlink(out)

    def test_invalid_range(self, generated_video):
        out = os.path.join(tempfile.gettempdir(), "test_trim_bad.mp4")
        with pytest.raises(VideoEditError, match="must be"):
            trim_video(generated_video, 3.0, 1.0, out)

    def test_missing_file(self):
        with pytest.raises(VideoEditError, match="not found"):
            trim_video("/nonexistent.mp4", 0, 1, "/tmp/out.mp4")


# ─── concat_segments tests ──────────────────────────────────────────

class TestConcatSegments:
    def test_single_segment_fast_path(self, generated_video):
        """Single segment should use stream copy (trim_video)."""
        out = os.path.join(tempfile.gettempdir(), "test_concat_single.mp4")
        segs = [EditSegment(start=0.5, end=2.5)]
        result = concat_segments(generated_video, segs, out)
        assert result == out
        dur = _get_duration(out)
        # Single segment = stream copy, keyframe-aligned tolerance
        assert 1.0 < dur < 3.0, f"Expected ~2s (stream copy), got {dur}"
        os.unlink(out)

    def test_multiple_segments(self, generated_video):
        """Multiple segments should re-encode and concatenate."""
        out = os.path.join(tempfile.gettempdir(), "test_concat_multi.mp4")
        segs = [
            EditSegment(start=0.0, end=1.0),
            EditSegment(start=2.0, end=3.0),
        ]
        result = concat_segments(generated_video, segs, out)
        assert result == out
        dur = _get_duration(out)
        # Re-encoded segments should be frame-accurate
        assert 1.5 < dur < 2.8, f"Expected ~2s (re-encoded), got {dur}"
        os.unlink(out)

    def test_empty_segments_raises(self, generated_video):
        with pytest.raises(VideoEditError, match="No segments"):
            concat_segments(generated_video, [], "/tmp/out.mp4")

    def test_overlapping_segments_raises(self, generated_video):
        segs = [
            EditSegment(start=0.0, end=2.0),
            EditSegment(start=1.5, end=3.0),
        ]
        out = os.path.join(tempfile.gettempdir(), "test_concat_overlap.mp4")
        with pytest.raises(VideoEditError, match="overlaps"):
            concat_segments(generated_video, segs, out)
