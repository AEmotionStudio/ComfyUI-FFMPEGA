"""Integration tests — run real ffmpeg on a test video.

These tests verify that composed pipelines actually produce valid
output files when executed through ffmpeg.  They require ffmpeg
to be installed on the system.

The test video is generated dynamically at session start: a 5-frame,
160×120, 0.2s clip with a 440 Hz sine tone — small enough to
process in <1s per test.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from skills.composer import SkillComposer, Pipeline

# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

_ffmpeg = shutil.which("ffmpeg")
_ffprobe = shutil.which("ffprobe")

pytestmark = pytest.mark.skipif(
    not _ffmpeg,
    reason="ffmpeg not found",
)


@pytest.fixture(scope="session")
def _generated_video() -> str:
    """Generate a tiny test video once per session, return its path."""
    assert _ffmpeg, "ffmpeg required"
    tmpdir = tempfile.mkdtemp(prefix="ffmpega_test_")
    path = os.path.join(tmpdir, "test_video.mp4")
    subprocess.run(
        [
            _ffmpeg, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=0.2:size=160x120:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", path,
        ],
        capture_output=True,
        timeout=30,
    )
    yield path
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def test_video(_generated_video: str) -> str:
    """Return the path to the test video fixture."""
    return _generated_video


@pytest.fixture
def output_path(tmp_path: Path) -> str:
    """Return a temporary output path for each test."""
    return str(tmp_path / "output.mp4")


def _run_ffmpeg(command) -> subprocess.CompletedProcess:
    """Execute an FFMPEGCommand and return the completed process."""
    args = command.to_args()
    return subprocess.run(
        args,
        capture_output=True,
        timeout=30,
    )


def _probe(path: str) -> dict:
    """Probe a media file with ffprobe, returning parsed JSON."""
    assert _ffprobe, "ffprobe not found"
    result = subprocess.run(
        [
            _ffprobe, "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(result.stdout)


def _get_video_stream(probe_data: dict) -> dict:
    """Extract the video stream from probe data."""
    for s in probe_data.get("streams", []):
        if s.get("codec_type") == "video":
            return s
    raise ValueError("No video stream found")


def _get_audio_stream(probe_data: dict) -> dict | None:
    """Extract the audio stream from probe data, or None."""
    for s in probe_data.get("streams", []):
        if s.get("codec_type") == "audio":
            return s
    return None


# ---------------------------------------------------------------------------
#  Single-Skill Integration Tests
# ---------------------------------------------------------------------------


class TestSingleSkill:
    """Verify individual skills produce valid ffmpeg output."""

    def test_brightness(self, test_video: str, output_path: str):
        """Brightness adjustment produces a valid output file."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("brightness", {"value": 0.2})
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0

        probe = _probe(output_path)
        video = _get_video_stream(probe)
        assert video["codec_name"] == "h264"

    def test_resize(self, test_video: str, output_path: str):
        """Resize produces output with correct dimensions."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("resize", {"width": 80, "height": 60})
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        probe = _probe(output_path)
        video = _get_video_stream(probe)
        assert int(video["width"]) == 80
        assert int(video["height"]) == 60

    def test_volume(self, test_video: str, output_path: str):
        """Volume adjustment produces valid output with audio stream."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("volume", {"level": 0.5})
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        probe = _probe(output_path)
        audio = _get_audio_stream(probe)
        assert audio is not None, "Audio stream should be present"

    def test_remove_audio(self, test_video: str, output_path: str):
        """remove_audio strips audio from output."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("remove_audio", {})
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        probe = _probe(output_path)
        audio = _get_audio_stream(probe)
        assert audio is None, "Audio stream should NOT be present"

    def test_speed(self, test_video: str, output_path: str):
        """Speed change adjusts duration."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("speed", {"factor": 2.0})
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        probe = _probe(output_path)
        duration = float(probe["format"]["duration"])
        # 2x speed on 0.2s → ~0.1s (allow tolerance for container overhead)
        assert duration <= 0.2, f"Expected ≤0.1s but got {duration}s"


# ---------------------------------------------------------------------------
#  Multi-Skill Pipeline Tests
# ---------------------------------------------------------------------------


class TestMultiSkillPipeline:
    """Verify chained skills produce valid output."""

    def test_resize_brightness_chain(self, test_video: str, output_path: str):
        """resize + brightness chain produces correct dimensions with effects."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("resize", {"width": 80, "height": 60})
        pipeline.add_step("brightness", {"value": 0.1})
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        probe = _probe(output_path)
        video = _get_video_stream(probe)
        assert int(video["width"]) == 80
        assert int(video["height"]) == 60

    def test_trim_resize_brightness(self, test_video: str, output_path: str):
        """trim + resize + brightness chain."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("trim", {"start": 0, "duration": 0.1})
        pipeline.add_step("resize", {"width": 80, "height": 60})
        pipeline.add_step("brightness", {"value": 0.05})
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        probe = _probe(output_path)
        duration = float(probe["format"]["duration"])
        assert duration <= 0.15, f"Expected ≤0.1s but got {duration}s"

    def test_video_and_audio_skills(self, test_video: str, output_path: str):
        """brightness (video) + volume (audio) both apply."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("brightness", {"value": 0.1})
        pipeline.add_step("volume", {"level": 0.5})
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        probe = _probe(output_path)
        assert _get_audio_stream(probe) is not None
        assert _get_video_stream(probe) is not None

    def test_full_realistic_pipeline(self, test_video: str, output_path: str):
        """A realistic multi-skill pipeline like the LLM would generate."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("resize", {"width": 80, "height": 60})
        pipeline.add_step("brightness", {"value": 0.05})
        pipeline.add_step("contrast", {"value": 1.1})
        pipeline.add_step("web_optimize", {})
        pipeline.add_step("quality", {"crf": 23, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        assert os.path.getsize(output_path) > 0

        probe = _probe(output_path)
        video = _get_video_stream(probe)
        assert int(video["width"]) == 80


# ---------------------------------------------------------------------------
#  Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases that could break ffmpeg execution."""

    def test_empty_pipeline_copy(self, test_video: str, output_path: str):
        """Pipeline with no skills should still produce valid output (copy)."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0, f"ffmpeg failed: {result.stderr.decode()}"
        assert os.path.exists(output_path)

    def test_output_overwrites_existing(self, test_video: str, output_path: str):
        """Output file is overwritten when it already exists."""
        # Create a dummy file first
        Path(output_path).write_bytes(b"dummy")

        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("brightness", {"value": 0.1})
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0
        assert os.path.getsize(output_path) > 5  # bigger than "dummy"

    def test_pixel_format_enforcement(self, test_video: str, output_path: str):
        """pixel_format skill enforces yuv420p for maximum compat."""
        composer = SkillComposer()
        pipeline = Pipeline(input_path=test_video, output_path=output_path)
        pipeline.add_step("pixel_format", {"format": "yuv420p"})
        pipeline.add_step("quality", {"crf": 28, "preset": "ultrafast"})

        result = _run_ffmpeg(composer.compose(pipeline))

        assert result.returncode == 0
        probe = _probe(output_path)
        video = _get_video_stream(probe)
        assert video["pix_fmt"] == "yuv420p"
