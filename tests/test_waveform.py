"""Unit tests for videoeditor.processing.waveform module.

Tests the peak extraction and downsampling logic without needing
a real video file.  Uses synthetic PCM data to verify bin count,
normalisation, and edge cases.
"""

from __future__ import annotations

import asyncio
import math
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module under test — adjust path for direct pytest runs
# without the full ComfyUI package context.
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from videoeditor.processing.waveform import (
    _downsample_peaks,
    extract_waveform_peaks,
    PEAK_COUNT,
)


# ---------------------------------------------------------------------------
#  _downsample_peaks
# ---------------------------------------------------------------------------


class TestDownsamplePeaks:
    """Test the peak downsampling helper."""

    def test_basic_bin_count(self):
        """Output should have exactly the requested number of bins."""
        samples = [math.sin(i / 100) for i in range(10_000)]
        peaks = _downsample_peaks(samples, 100)
        assert len(peaks) == 100

    def test_normalisation(self):
        """Max peak should be 1.0 after normalisation."""
        samples = [0.5, -0.8, 0.3, -0.1, 0.8, -0.5, 0.2, 0.0]
        peaks = _downsample_peaks(samples, 4)
        assert len(peaks) == 4
        assert max(peaks) == pytest.approx(1.0)

    def test_all_zeros(self):
        """All-zero input should produce all-zero peaks (no division by zero)."""
        samples = [0.0] * 1000
        peaks = _downsample_peaks(samples, 50)
        assert all(p == 0.0 for p in peaks)

    def test_short_audio(self):
        """Audio shorter than bin count should not crash."""
        samples = [0.5, -0.5, 0.3]
        peaks = _downsample_peaks(samples, 100)
        assert len(peaks) == 100
        # First 3 bins should have values, rest should be 0
        assert peaks[0] > 0
        assert peaks[99] == 0.0

    def test_single_sample(self):
        """Single sample should produce a valid result."""
        peaks = _downsample_peaks([0.7], 10)
        assert len(peaks) == 10
        assert peaks[0] == pytest.approx(1.0)  # normalised

    def test_values_are_absolute(self):
        """Peaks should use absolute values (negative samples count)."""
        # All negative signals should still produce positive peaks
        samples = [-0.5, -1.0, -0.3, -0.8]
        peaks = _downsample_peaks(samples, 2)
        assert all(p >= 0 for p in peaks)


# ---------------------------------------------------------------------------
#  extract_waveform_peaks (integration with mocked subprocess)
# ---------------------------------------------------------------------------


def _make_pcm_bytes(samples: list[float]) -> bytes:
    """Convert a list of floats to f32le PCM bytes."""
    return struct.pack(f"<{len(samples)}f", *samples)


def _mock_subprocess(probe_stdout: str, probe_rc: int,
                     ffmpeg_stdout: bytes, ffmpeg_rc: int):
    """Create an AsyncMock for asyncio.create_subprocess_exec.

    Returns a side_effect function that yields the ffprobe result first,
    then the ffmpeg result on the second call.
    """
    probe_proc = AsyncMock()
    probe_proc.returncode = probe_rc
    probe_proc.communicate = AsyncMock(
        return_value=(probe_stdout.encode(), b""),
    )
    probe_proc.kill = AsyncMock()
    probe_proc.wait = AsyncMock()

    ffmpeg_proc = AsyncMock()
    ffmpeg_proc.returncode = ffmpeg_rc
    ffmpeg_proc.communicate = AsyncMock(
        return_value=(ffmpeg_stdout, b""),
    )
    ffmpeg_proc.kill = AsyncMock()
    ffmpeg_proc.wait = AsyncMock()

    calls = iter([probe_proc, ffmpeg_proc])
    return AsyncMock(side_effect=lambda *a, **kw: next(calls))


class TestExtractWaveformPeaks:
    """Test the full extraction pipeline with mocked async subprocesses."""

    @patch("videoeditor.processing.waveform.get_ffprobe_bin", return_value="/usr/bin/ffprobe")
    @patch("videoeditor.processing.waveform.get_ffmpeg_bin", return_value="/usr/bin/ffmpeg")
    @patch("videoeditor.processing.waveform.asyncio.create_subprocess_exec")
    def test_successful_extraction(self, mock_exec, mock_ffmpeg, mock_ffprobe):
        """Successful extraction returns peaks with correct structure."""
        samples = [math.sin(i * 0.1) * 0.5 for i in range(8000)]
        mock_exec.side_effect = _mock_subprocess(
            "10.5\n", 0, _make_pcm_bytes(samples), 0,
        ).side_effect

        result = asyncio.run(
            extract_waveform_peaks("/tmp/test.mp4"),
        )

        assert "peaks" in result
        assert "duration" in result
        assert "sampleRate" in result
        assert len(result["peaks"]) == PEAK_COUNT
        assert result["duration"] == 10.5
        assert result["sampleRate"] == 8000
        assert max(result["peaks"]) == pytest.approx(1.0, abs=0.01)

    @patch("videoeditor.processing.waveform.get_ffprobe_bin", return_value="/usr/bin/ffprobe")
    @patch("videoeditor.processing.waveform.get_ffmpeg_bin", return_value="/usr/bin/ffmpeg")
    @patch("videoeditor.processing.waveform.asyncio.create_subprocess_exec")
    def test_no_audio_returns_flat(self, mock_exec, mock_ffmpeg, mock_ffprobe):
        """Video with no audio returns flat waveform."""
        mock_exec.side_effect = _mock_subprocess(
            "5.0\n", 0, b"", 1,
        ).side_effect

        result = asyncio.run(
            extract_waveform_peaks("/tmp/silent.mp4"),
        )

        assert len(result["peaks"]) == PEAK_COUNT
        assert all(p == pytest.approx(0.1) for p in result["peaks"])

    @patch("videoeditor.processing.waveform.get_ffprobe_bin", return_value=None)
    @patch("videoeditor.processing.waveform.get_ffmpeg_bin", return_value=None)
    def test_no_ffmpeg_returns_flat(self, mock_ffmpeg, mock_ffprobe):
        """Missing FFmpeg returns flat waveform."""
        result = asyncio.run(
            extract_waveform_peaks("/tmp/test.mp4"),
        )

        assert len(result["peaks"]) == PEAK_COUNT
        assert result["duration"] == 0.0

    @patch("videoeditor.processing.waveform.get_ffprobe_bin", return_value="/usr/bin/ffprobe")
    @patch("videoeditor.processing.waveform.get_ffmpeg_bin", return_value="/usr/bin/ffmpeg")
    @patch("videoeditor.processing.waveform.asyncio.create_subprocess_exec")
    def test_timeout_returns_flat(self, mock_exec, mock_ffmpeg, mock_ffprobe):
        """FFmpeg timeout returns flat waveform."""
        # Probe succeeds, FFmpeg communicate() times out
        probe_proc = AsyncMock()
        probe_proc.returncode = 0
        probe_proc.communicate = AsyncMock(return_value=(b"5.0\n", b""))

        ffmpeg_proc = AsyncMock()
        ffmpeg_proc.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError(),
        )
        ffmpeg_proc.kill = AsyncMock()
        ffmpeg_proc.wait = AsyncMock()

        calls = iter([probe_proc, ffmpeg_proc])
        mock_exec.side_effect = lambda *a, **kw: next(calls)

        result = asyncio.run(
            extract_waveform_peaks("/tmp/test.mp4"),
        )

        assert len(result["peaks"]) == PEAK_COUNT
        assert all(p == pytest.approx(0.1) for p in result["peaks"])

    @patch("videoeditor.processing.waveform.get_ffprobe_bin", return_value="/usr/bin/ffprobe")
    @patch("videoeditor.processing.waveform.get_ffmpeg_bin", return_value="/usr/bin/ffmpeg")
    @patch("videoeditor.processing.waveform.asyncio.create_subprocess_exec")
    def test_long_video_returns_flat(self, mock_exec, mock_ffmpeg, mock_ffprobe):
        """Video over 30 minutes returns flat waveform (duration cap)."""
        probe_proc = AsyncMock()
        probe_proc.returncode = 0
        probe_proc.communicate = AsyncMock(return_value=(b"3600.0\n", b""))

        mock_exec.return_value = probe_proc

        result = asyncio.run(
            extract_waveform_peaks("/tmp/long.mp4"),
        )

        assert len(result["peaks"]) == PEAK_COUNT
        assert all(p == pytest.approx(0.1) for p in result["peaks"])
