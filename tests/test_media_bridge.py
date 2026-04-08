"""Tests for MediaBridgeNode — bidirectional images ↔ path converter."""

import pytest
torch = pytest.importorskip("torch")

import sys
import types
import os
from unittest.mock import MagicMock, patch

# Ensure conftest sys.path setup has run; add project root if needed
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Mock folder_paths if not present
if "folder_paths" not in sys.modules:
    mock_fp = types.ModuleType("folder_paths")
    mock_fp.get_output_directory = lambda: "/tmp/comfyui_output"
    mock_fp.get_temp_directory = lambda: "/tmp/comfyui_temp"
    sys.modules["folder_paths"] = mock_fp

from nodes.media_bridge_node import MediaBridgeNode


# ── INPUT_TYPES & class attributes ──────────────────────────────────


class TestMediaBridgeInputTypes:
    """Verify INPUT_TYPES structure and return types."""

    def test_mode_in_required(self):
        it = MediaBridgeNode.INPUT_TYPES()
        assert "mode" in it["required"]

    def test_mode_choices(self):
        it = MediaBridgeNode.INPUT_TYPES()
        choices = it["required"]["mode"][0]
        assert "images_to_path" in choices
        assert "path_to_images" in choices

    def test_images_in_optional(self):
        it = MediaBridgeNode.INPUT_TYPES()
        assert "images" in it["optional"]

    def test_video_path_in_optional(self):
        it = MediaBridgeNode.INPUT_TYPES()
        assert "video_path" in it["optional"]

    def test_fps_in_optional(self):
        it = MediaBridgeNode.INPUT_TYPES()
        assert "fps" in it["optional"]

    def test_audio_in_optional(self):
        it = MediaBridgeNode.INPUT_TYPES()
        assert "audio" in it["optional"]

    def test_return_types(self):
        assert "STRING" in MediaBridgeNode.RETURN_TYPES
        assert "IMAGE" in MediaBridgeNode.RETURN_TYPES
        assert "AUDIO" in MediaBridgeNode.RETURN_TYPES
        assert "MASK" in MediaBridgeNode.RETURN_TYPES

    def test_return_names(self):
        assert "video_path" in MediaBridgeNode.RETURN_NAMES
        assert "images" in MediaBridgeNode.RETURN_NAMES
        assert "audio" in MediaBridgeNode.RETURN_NAMES
        assert "mask" in MediaBridgeNode.RETURN_NAMES


# ── images_to_path mode ─────────────────────────────────────────────


class TestImagesToPath:
    """Test images_to_path conversion mode."""

    def setup_method(self):
        self.node = MediaBridgeNode()

    @patch("nodes.media_bridge_node.torch.cuda.is_available", return_value=False)
    def test_converts_images_to_video(self, _mock_cuda):
        images = torch.rand(10, 64, 64, 3, dtype=torch.float32)
        fake_path = "/tmp/ffmpega_test_video.mp4"

        mock_converter = MagicMock()
        mock_converter.images_to_video.return_value = fake_path

        with patch("nodes.media_bridge_node.MediaConverter", return_value=mock_converter):
            result = self.node.convert(mode="images_to_path", images=images, fps=30)

        video_path, out_images, out_audio, out_mask = result
        assert video_path == fake_path
        # Unused outputs should be safe defaults
        assert out_images.shape == (1, 64, 64, 3)
        assert "waveform" in out_audio

    @patch("nodes.media_bridge_node.torch.cuda.is_available", return_value=False)
    def test_muxes_audio_when_provided(self, _mock_cuda):
        images = torch.rand(5, 32, 32, 3, dtype=torch.float32)
        fake_path = "/tmp/ffmpega_test_audio.mp4"
        audio = {"waveform": torch.zeros(1, 1, 44100), "sample_rate": 44100}

        mock_converter = MagicMock()
        mock_converter.images_to_video.return_value = fake_path

        with patch("nodes.media_bridge_node.MediaConverter", return_value=mock_converter):
            result = self.node.convert(mode="images_to_path", images=images, audio=audio)

        mock_converter.mux_audio.assert_called_once_with(fake_path, audio)
        assert result[0] == fake_path

    def test_error_without_images(self):
        with pytest.raises(ValueError, match="images.*required"):
            self.node.convert(mode="images_to_path", images=None)


# ── path_to_images mode ─────────────────────────────────────────────


class TestPathToImages:
    """Test path_to_images conversion mode."""

    def setup_method(self):
        self.node = MediaBridgeNode()

    def test_decodes_video_to_images(self, tmp_path):
        # Create a dummy file so os.path.isfile passes
        dummy_vid = tmp_path / "test.mp4"
        dummy_vid.write_bytes(b"\x00" * 100)

        fake_tensor = torch.rand(15, 128, 128, 3, dtype=torch.float32)
        fake_audio = {"waveform": torch.zeros(1, 1, 44100), "sample_rate": 44100}

        mock_converter = MagicMock()
        mock_converter.frames_to_tensor.return_value = fake_tensor
        mock_converter.extract_audio.return_value = fake_audio

        with patch("nodes.media_bridge_node.MediaConverter", return_value=mock_converter), \
             patch.object(MediaBridgeNode, "_probe_fps", return_value=29.97):
            result = self.node.convert(mode="path_to_images", video_path=str(dummy_vid))

        video_path, images, audio, mask = result
        assert video_path == ""
        assert images.shape == (15, 128, 128, 3)
        assert audio == fake_audio

    def test_error_without_video_path(self):
        with pytest.raises(ValueError, match="video_path.*required"):
            self.node.convert(mode="path_to_images", video_path=None)

    def test_error_with_empty_video_path(self):
        with pytest.raises(ValueError, match="video_path.*required"):
            self.node.convert(mode="path_to_images", video_path="")

    def test_error_with_nonexistent_file(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            self.node.convert(mode="path_to_images", video_path="/definitely/not/a/file.mp4")


# ── _probe_fps ───────────────────────────────────────────────────────


class TestProbeFps:
    """Test FPS probing from video files."""

    @patch("subprocess.run")
    def test_probe_fps_parses_fraction(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"streams": [{"codec_type": "video", "r_frame_rate": "30000/1001"}]}',
        )
        with patch("core.bin_paths.get_ffprobe_bin", return_value="/usr/bin/ffprobe"):
            fps = MediaBridgeNode._probe_fps("dummy.mp4")
        assert abs(fps - 29.97) < 0.01

    @patch("subprocess.run")
    def test_probe_fps_handles_simple_rate(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"streams": [{"codec_type": "video", "r_frame_rate": "24/1"}]}',
        )
        with patch("core.bin_paths.get_ffprobe_bin", return_value="/usr/bin/ffprobe"):
            fps = MediaBridgeNode._probe_fps("dummy.mp4")
        assert fps == 24.0

    def test_probe_fps_no_ffprobe(self):
        with patch("core.bin_paths.get_ffprobe_bin", return_value=None):
            fps = MediaBridgeNode._probe_fps("dummy.mp4")
        assert fps == 24.0
