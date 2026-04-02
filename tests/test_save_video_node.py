"""Tests for SaveVideoNode image-to-video encoding."""

import os
import sys
import types
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

torch = pytest.importorskip("torch")


# Mock folder_paths before importing the node
@pytest.fixture(autouse=True)
def mock_folder_paths(tmp_path):
    """Provide a mock folder_paths module for all tests."""
    mock_fp = types.ModuleType("folder_paths")
    output_dir = str(tmp_path / "output")
    os.makedirs(output_dir, exist_ok=True)
    mock_fp.get_output_directory = lambda: output_dir
    mock_fp.get_temp_directory = lambda: str(tmp_path / "temp")
    mock_fp.get_save_image_path = lambda prefix, out_dir: (
        out_dir, prefix, 1, "", ""
    )
    sys.modules["folder_paths"] = mock_fp
    yield mock_fp


@pytest.fixture
def node():
    from nodes.save_video_node import SaveVideoNode
    return SaveVideoNode()


class TestSaveVideoImagesEncoding:
    """Test IMAGE batch → video encoding in SaveVideoNode."""

    @patch("core.media_converter.get_ffmpeg_bin", return_value="/usr/bin/ffmpeg")
    def test_images_without_video_path_triggers_encoding(
        self, mock_ffmpeg, node, tmp_path,
    ):
        """When images are provided without video_path, images_to_video is called."""
        images = torch.rand(21, 64, 64, 3, dtype=torch.float32)

        # Create a fake temp video that images_to_video would produce
        fake_video = str(tmp_path / "encoded.mp4")
        with open(fake_video, "wb") as f:
            f.write(b"\x00" * 1024)  # minimal placeholder

        with patch("core.media_converter.MediaConverter.images_to_video", return_value=fake_video) as mock_encode:
            result = node.save_video(
                video_path="",
                images=images,
                fps=30,
            )

            mock_encode.assert_called_once_with(images, fps=30)
            # Should return valid UI data (not the empty fallback)
            assert result["ui"]["file_size"][0] != "0 B"

    def test_video_path_provided_skips_encoding(self, node, tmp_path):
        """When video_path is valid, images_to_video should NOT be called."""
        images = torch.rand(5, 64, 64, 3, dtype=torch.float32)

        # Create a real video file
        fake_video = str(tmp_path / "existing.mp4")
        with open(fake_video, "wb") as f:
            f.write(b"\x00" * 512)

        with patch("core.media_converter.MediaConverter.images_to_video") as mock_encode:
            result = node.save_video(
                video_path=fake_video,
                images=images,
            )
            mock_encode.assert_not_called()

    def test_no_images_no_video_returns_empty(self, node):
        """When neither images nor video_path are provided, return empty."""
        result = node.save_video(video_path="", images=None)

        assert result["ui"]["video"] == []
        assert result["ui"]["file_size"] == ["0 B"]
        assert result["result"][2] == ""  # video_path output

    @patch("core.media_converter.get_ffmpeg_bin", return_value="/usr/bin/ffmpeg")
    def test_temp_file_cleaned_up(self, mock_ffmpeg, node, tmp_path):
        """Temp video from encoding should be deleted after copy."""
        images = torch.rand(5, 64, 64, 3, dtype=torch.float32)

        fake_video = str(tmp_path / "temp_encoded.mp4")
        with open(fake_video, "wb") as f:
            f.write(b"\x00" * 1024)

        with patch("core.media_converter.MediaConverter.images_to_video", return_value=fake_video):
            node.save_video(
                video_path="",
                images=images,
                fps=24,
            )

        # Temp file should be cleaned up
        assert not os.path.isfile(fake_video)

    @patch("core.media_converter.get_ffmpeg_bin", return_value="/usr/bin/ffmpeg")
    def test_default_fps_is_24(self, mock_ffmpeg, node, tmp_path):
        """Default fps should be 24."""
        images = torch.rand(3, 64, 64, 3, dtype=torch.float32)

        fake_video = str(tmp_path / "default_fps.mp4")
        with open(fake_video, "wb") as f:
            f.write(b"\x00" * 1024)

        with patch("core.media_converter.MediaConverter.images_to_video", return_value=fake_video) as mock_encode:
            node.save_video(video_path="", images=images)
            mock_encode.assert_called_once_with(images, fps=24)

    def test_encoding_failure_returns_empty(self, node):
        """If images_to_video raises, node returns empty gracefully."""
        images = torch.rand(5, 64, 64, 3, dtype=torch.float32)

        with patch("core.media_converter.MediaConverter.images_to_video", side_effect=RuntimeError("ffmpeg failed")):
            result = node.save_video(video_path="", images=images)

        # Should fall through to the empty-path guard
        assert result["ui"]["video"] == []
        assert result["ui"]["file_size"] == ["0 B"]
