# coding: utf-8
"""Tests for Rembg background removal integration."""

import sys
import os
import json
import asyncio
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import dataclass

import pytest

# Ensure project root is on sys.path
_proj = os.path.dirname(os.path.dirname(__file__))
if _proj not in sys.path:
    sys.path.insert(0, _proj)

# PyTorch guard
try:
    import torch  # noqa: F401
    _has_torch = True
except (ImportError, RuntimeError):
    _has_torch = False


# ------------------------------------------------------------------ #
#  No-LLM mode dropdown
# ------------------------------------------------------------------ #

class TestRembgNoLLMMode:
    """Test the rembg no_llm_mode integration."""

    def test_rembg_in_no_llm_dropdown(self):
        """'rembg' should be in the no_llm_mode dropdown choices."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        choices = input_types["required"]["no_llm_mode"][0]
        assert "rembg" in choices

    def test_rembg_model_dropdown_exists(self):
        """rembg_model should be in optional INPUT_TYPES."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        optional = input_types.get("optional", {})
        assert "rembg_model" in optional
        models = optional["rembg_model"][0]
        assert "bria-rmbg" in models

    def test_rembg_background_dropdown_exists(self):
        """rembg_background should be in optional INPUT_TYPES."""
        pytest.importorskip("torch")
        from nodes.agent_node import FFMPEGAgentNode
        input_types = FFMPEGAgentNode.INPUT_TYPES()
        optional = input_types.get("optional", {})
        assert "rembg_background" in optional
        backgrounds = optional["rembg_background"][0]
        assert "transparent" in backgrounds
        assert "green" in backgrounds

    def test_process_rembg_only_exists(self):
        """process_rembg_only should be importable from nollm_modes."""
        pytest.importorskip("torch")
        from nodes.nollm_modes import process_rembg_only
        assert callable(process_rembg_only)


# ------------------------------------------------------------------ #
#  process_rembg_only logic
# ------------------------------------------------------------------ #

@pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
class TestProcessRembgOnly:
    """Unit tests for process_rembg_only with mocked dependencies."""

    @staticmethod
    def _make_handler_result(fc="[0:v]some_filter[_vout]", output_options=None):
        """Create a mock HandlerResult dataclass."""
        @dataclass
        class _MockResult:
            filter_complex: str
            output_options: list
        return _MockResult(
            filter_complex=fc,
            output_options=output_options or [],
        )

    @pytest.fixture
    def tmp_video(self, tmp_path):
        """Create a fake video file for testing."""
        vid = tmp_path / "test.mp4"
        vid.write_text("fake")
        return str(vid)

    @pytest.fixture
    def output_dir(self, tmp_path):
        return str(tmp_path / "output")

    def test_solid_background_uses_h264(self, tmp_video, output_dir):
        """Solid background should produce H.264 encoding flags."""
        from nodes.nollm_modes import process_rembg_only

        mock_media = MagicMock()
        handler_result = self._make_handler_result()

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        mock_tensor = torch.zeros(1, 2, 2, 3)
        mock_audio = {}

        with patch("nodes.nollm_modes.build_output_path") as mock_bop, \
             patch("skills.handlers.visual._f_remove_background", return_value=handler_result), \
             patch("nodes.nollm_modes._get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("asyncio.to_thread") as mock_thread, \
             patch("nodes.nollm_modes.collect_frame_output", return_value=(mock_tensor, mock_audio)):

            mock_bop.return_value = (output_dir + "/out.mp4", output_dir)

            # First call = handler, second call = subprocess.run
            mock_thread.side_effect = [handler_result, mock_proc]

            result = asyncio.run(
                process_rembg_only(
                    media_converter=mock_media,
                    effective_video_path=tmp_video,
                    video_metadata={"audio_codec": "aac"},
                    save_output=False,
                    output_path=output_dir + "/out.mp4",
                    preview_mode=False,
                    quality_preset="standard",
                    crf=-1,
                    encoding_preset="auto",
                    rembg_model="bria-rmbg",
                    rembg_background="green",
                )
            )

            # Should return 6-tuple
            assert len(result) == 6
            # Verify FFmpeg was called with H.264 flags
            ffmpeg_call = mock_thread.call_args_list[1]
            cmd_args = ffmpeg_call[0][1]  # subprocess.run args
            assert "libx264" in cmd_args

    def test_transparent_background_uses_webm(self, tmp_video, output_dir):
        """Transparent background should switch output to .webm."""
        from nodes.nollm_modes import process_rembg_only

        mock_media = MagicMock()
        handler_result = self._make_handler_result(
            output_options=["-c:v", "libvpx-vp9", "-auto-alt-ref", "0"]
        )

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        mock_tensor = torch.zeros(1, 2, 2, 3)
        mock_audio = {}

        with patch("nodes.nollm_modes.build_output_path") as mock_bop, \
             patch("skills.handlers.visual._f_remove_background", return_value=handler_result), \
             patch("nodes.nollm_modes._get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("asyncio.to_thread") as mock_thread, \
             patch("nodes.nollm_modes.collect_frame_output", return_value=(mock_tensor, mock_audio)):

            mock_bop.return_value = (output_dir + "/out.mp4", output_dir)
            mock_thread.side_effect = [handler_result, mock_proc]

            result = asyncio.run(
                process_rembg_only(
                    media_converter=mock_media,
                    effective_video_path=tmp_video,
                    video_metadata=None,
                    save_output=False,
                    output_path=output_dir + "/out.mp4",
                    preview_mode=False,
                    quality_preset="standard",
                    crf=-1,
                    encoding_preset="auto",
                    rembg_model="bria-rmbg",
                    rembg_background="transparent",
                )
            )

            assert len(result) == 6
            # Output path should be .webm
            assert result[2].endswith(".webm")

    def test_handler_error_raises_runtime(self, tmp_video, output_dir):
        """Empty filter_complex from handler should raise RuntimeError."""
        from nodes.nollm_modes import process_rembg_only

        mock_media = MagicMock()
        handler_result = self._make_handler_result(fc="")

        with patch("nodes.nollm_modes.build_output_path") as mock_bop, \
             patch("skills.handlers.visual._f_remove_background", return_value=handler_result), \
             patch("asyncio.to_thread", return_value=handler_result):

            mock_bop.return_value = (output_dir + "/out.mp4", output_dir)

            with pytest.raises(RuntimeError, match="rembg handler returned no filter_complex"):
                asyncio.run(
                    process_rembg_only(
                        media_converter=mock_media,
                        effective_video_path=tmp_video,
                        video_metadata=None,
                        save_output=False,
                        output_path=output_dir + "/out.mp4",
                        preview_mode=False,
                        quality_preset="standard",
                        crf=-1,
                        encoding_preset="auto",
                    )
                )

    def test_ffmpeg_failure_raises_runtime(self, tmp_video, output_dir):
        """Non-zero FFmpeg exit code should raise RuntimeError."""
        from nodes.nollm_modes import process_rembg_only

        mock_media = MagicMock()
        handler_result = self._make_handler_result()

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "Error encoding"

        with patch("nodes.nollm_modes.build_output_path") as mock_bop, \
             patch("skills.handlers.visual._f_remove_background", return_value=handler_result), \
             patch("nodes.nollm_modes._get_ffmpeg_bin", return_value="ffmpeg"), \
             patch("asyncio.to_thread") as mock_thread:

            mock_bop.return_value = (output_dir + "/out.mp4", output_dir)
            mock_thread.side_effect = [handler_result, mock_proc]

            with pytest.raises(RuntimeError, match="FFmpeg rembg render failed"):
                asyncio.run(
                    process_rembg_only(
                        media_converter=mock_media,
                        effective_video_path=tmp_video,
                        video_metadata=None,
                        save_output=False,
                        output_path=output_dir + "/out.mp4",
                        preview_mode=False,
                        quality_preset="standard",
                        crf=-1,
                        encoding_preset="auto",
                        rembg_background="green",
                    )
                )
