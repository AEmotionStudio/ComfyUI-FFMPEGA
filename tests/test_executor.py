"""Tests for the FFMPEG executor module."""

import pytest
from pathlib import Path
import tempfile

from core.executor.command_builder import CommandBuilder, Filter, FilterChain, FFMPEGCommand
from core.executor.process_manager import ProcessManager, ProcessResult


class TestFilter:
    """Tests for Filter class."""

    def test_simple_filter(self):
        """Test basic filter string generation."""
        f = Filter(name="scale", params={"w": 1920, "h": 1080})
        assert f.to_string() == "scale=w=1920:h=1080"

    def test_filter_with_labels(self):
        """Test filter with input/output labels."""
        f = Filter(
            name="scale",
            params={"w": 1920, "h": 1080},
            inputs=["0:v"],
            outputs=["scaled"],
        )
        assert f.to_string() == "[0:v]scale=w=1920:h=1080[scaled]"

    def test_filter_no_params(self):
        """Test filter without parameters."""
        f = Filter(name="hflip")
        assert f.to_string() == "hflip"


class TestFilterChain:
    """Tests for FilterChain class."""

    def test_single_filter_chain(self):
        """Test chain with single filter."""
        chain = FilterChain()
        chain.add_filter("scale", {"w": 1280, "h": 720})
        assert chain.to_string() == "scale=w=1280:h=720"

    def test_multiple_filter_chain(self):
        """Test chain with multiple filters."""
        chain = FilterChain()
        chain.add_filter("scale", {"w": 1280, "h": 720})
        chain.add_filter("fps", {"": "30"})
        result = chain.to_string()
        assert "scale=w=1280:h=720" in result
        assert "fps" in result

    def test_empty_chain(self):
        """Test empty filter chain."""
        chain = FilterChain()
        assert chain.to_string() == ""


class TestCommandBuilder:
    """Tests for CommandBuilder class."""

    def test_basic_command(self):
        """Test basic command generation."""
        builder = CommandBuilder()
        builder.input("/input.mp4")
        builder.output("/output.mp4")

        args = builder.build_args()

        assert "ffmpeg" in args
        assert "-i" in args
        assert "/input.mp4" in args
        assert "/output.mp4" in args

    def test_with_video_codec(self):
        """Test command with video codec."""
        builder = CommandBuilder()
        builder.input("/input.mp4")
        builder.video_codec("libx264", crf=23, preset="medium")
        builder.output("/output.mp4")

        args = builder.build_args()

        assert "-c:v" in args
        assert "libx264" in args
        assert "-crf" in args
        assert "23" in args
        assert "-preset" in args
        assert "medium" in args

    def test_with_filters(self):
        """Test command with video filters."""
        builder = CommandBuilder()
        builder.input("/input.mp4")
        builder.scale(1280, 720)
        builder.eq(brightness=0.1, contrast=1.2)
        builder.output("/output.mp4")

        cmd_str = builder.build_string()

        assert "-vf" in cmd_str
        assert "scale" in cmd_str
        assert "eq" in cmd_str

    def test_trim(self):
        """Test trim command."""
        builder = CommandBuilder()
        builder.input("/input.mp4")
        builder.trim(start=5, end=30)
        builder.output("/output.mp4")

        args = builder.build_args()

        assert "-ss" in args
        assert "5" in args
        assert "-to" in args
        assert "30" in args

    def test_speed(self):
        """Test speed adjustment."""
        builder = CommandBuilder()
        builder.input("/input.mp4")
        builder.speed(2.0)
        builder.output("/output.mp4")

        cmd_str = builder.build_string()

        assert "setpts" in cmd_str
        assert "atempo" in cmd_str

    def test_no_audio(self):
        """Test removing audio."""
        builder = CommandBuilder()
        builder.input("/input.mp4")
        builder.no_audio()
        builder.output("/output.mp4")

        args = builder.build_args()

        assert "-an" in args

    def test_quality_preset(self):
        """Test quality preset."""
        builder = CommandBuilder()
        builder.input("/input.mp4")
        builder.quality("high")
        builder.output("/output.mp4")

        args = builder.build_args()

        assert "-crf" in args
        assert "18" in args


class TestFFMPEGCommand:
    """Tests for FFMPEGCommand class."""

    def test_to_args(self):
        """Test conversion to argument list."""
        cmd = FFMPEGCommand()
        cmd.inputs = ["/input.mp4"]
        cmd.outputs = ["/output.mp4"]

        args = cmd.to_args()

        assert args[0] == "ffmpeg"
        assert "-y" in args  # Overwrite by default
        assert "-i" in args

    def test_to_string(self):
        """Test conversion to shell string."""
        cmd = FFMPEGCommand()
        cmd.inputs = ["/input.mp4"]
        cmd.outputs = ["/output.mp4"]

        cmd_str = cmd.to_string()

        assert "ffmpeg" in cmd_str
        assert "-i" in cmd_str
        assert "/input.mp4" in cmd_str


class TestProcessManager:
    """Tests for ProcessManager class."""

    def test_init_finds_ffmpeg(self):
        """Test that ProcessManager finds ffmpeg."""
        # This will raise if ffmpeg not found
        try:
            pm = ProcessManager()
            assert pm.ffmpeg_path is not None
        except RuntimeError:
            pytest.skip("ffmpeg not installed")

    def test_validate_command_missing_input(self):
        """Test validation catches missing input."""
        try:
            pm = ProcessManager()
        except RuntimeError:
            pytest.skip("ffmpeg not installed")

        cmd = FFMPEGCommand()
        cmd.outputs = ["/output.mp4"]

        is_valid, error = pm.validate_command(cmd)

        assert not is_valid
        assert "input" in error.lower()

    def test_validate_command_missing_output(self):
        """Test validation catches missing output."""
        try:
            pm = ProcessManager()
        except RuntimeError:
            pytest.skip("ffmpeg not installed")

        # Use a real temp file so we pass the input-exists check
        # and actually reach the missing-output validation.
        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
            cmd = FFMPEGCommand()
            cmd.inputs = [tmp.name]

            is_valid, error = pm.validate_command(cmd)

            assert not is_valid
            assert "output" in error.lower()


class TestProcessResult:
    """Tests for ProcessResult class."""

    def test_success_result(self):
        """Test successful result."""
        result = ProcessResult(
            success=True,
            return_code=0,
            stdout="",
            stderr="",
            command="ffmpeg -i input.mp4 output.mp4",
            output_path="/output.mp4",
        )

        assert result.success
        assert result.return_code == 0

    def test_error_result(self):
        """Test error result."""
        result = ProcessResult(
            success=False,
            return_code=1,
            stdout="",
            stderr="Error: file not found",
            command="ffmpeg -i input.mp4 output.mp4",
            error_message="File not found",
        )

        assert not result.success
        assert result.error_message == "File not found"
