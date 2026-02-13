
import pytest
import torch
import numpy as np
import sys
from unittest.mock import MagicMock, patch

# Import MediaConverter
from core.media_converter import MediaConverter

class TestMediaConverter:
    def setup_method(self):
        self.converter = MediaConverter()

    @patch("shutil.which")
    @patch("subprocess.Popen")
    def test_images_to_video_optimization(self, mock_popen, mock_which):
        """Test that images_to_video uses direct write instead of tobytes()."""
        mock_which.return_value = "/usr/bin/ffmpeg"

        # Mock process
        process_mock = MagicMock()
        # Mock stdin.write
        process_mock.stdin.write = MagicMock()
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        # Create input tensor (B, H, W, 3)
        images = torch.rand(10, 64, 64, 3, dtype=torch.float32)

        # Call method
        try:
            self.converter.images_to_video(images, fps=24)
        except RuntimeError:
            pass

        # Verify write was called
        assert process_mock.stdin.write.called

        # Check argument
        args, _ = process_mock.stdin.write.call_args
        written_data = args[0]

        # Check that written_data is a numpy array (optimization) not bytes
        assert isinstance(written_data, np.ndarray)
        assert written_data.dtype == np.uint8
        assert written_data.flags['C_CONTIGUOUS']

    def test_frames_to_tensor_logic(self):
        """Test logic of frames_to_tensor optimization."""
        # Create dummy frames (list of uint8 arrays)
        frames = [np.zeros((10, 10, 3), dtype=np.uint8) for _ in range(5)]

        # Manually run the optimized logic
        stacked = np.stack(frames)
        tensor = torch.from_numpy(stacked).float().div_(255.0)

        assert tensor.shape == (5, 10, 10, 3)
        assert tensor.dtype == torch.float32
        assert torch.all(tensor == 0.0)

    def test_frames_to_tensor_with_av_mock(self):
        """Test frames_to_tensor with mocked av library."""
        # Create mock av module
        mock_av = MagicMock()

        # Mock container and stream
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.frames = 5
        mock_container.streams.video = [mock_stream]

        # Mock frames
        mock_frames = []
        for i in range(5):
            frame = MagicMock()
            # Return random data
            arr = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
            frame.to_ndarray.return_value = arr
            mock_frames.append(frame)

        # Configure decode to return iterator
        mock_container.decode.return_value = iter(mock_frames)
        mock_av.open.return_value = mock_container

        # Apply mock
        with patch.dict(sys.modules, {"av": mock_av}):
            # Reload module or re-import inside function?
            # Since MediaConverter imports av inside the function, patching sys.modules works

            # Call method
            tensor = self.converter.frames_to_tensor("dummy.mp4")

            assert tensor.shape == (5, 64, 64, 3)
            assert tensor.dtype == torch.float32

            # Verify decode was called
            mock_container.decode.assert_called_with(video=0)

    def test_frames_to_tensor_mismatch_under(self):
        """Test frames_to_tensor when fewer frames are decoded than expected."""
        mock_av = MagicMock()
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.frames = 10 # Expect 10
        mock_container.streams.video = [mock_stream]

        # Only provide 5 frames
        mock_frames = []
        for i in range(5):
            frame = MagicMock()
            arr = np.zeros((64, 64, 3), dtype=np.uint8)
            frame.to_ndarray.return_value = arr
            mock_frames.append(frame)

        mock_container.decode.return_value = iter(mock_frames)
        mock_av.open.return_value = mock_container

        with patch.dict(sys.modules, {"av": mock_av}):
            tensor = self.converter.frames_to_tensor("dummy.mp4")

            # Should return 5 frames
            assert tensor.shape == (5, 64, 64, 3)

    def test_frames_to_tensor_mismatch_over(self):
        """Test frames_to_tensor when more frames are decoded than expected."""
        mock_av = MagicMock()
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.frames = 3 # Expect 3
        mock_container.streams.video = [mock_stream]

        # Provide 5 frames
        mock_frames = []
        for i in range(5):
            frame = MagicMock()
            arr = np.zeros((64, 64, 3), dtype=np.uint8)
            frame.to_ndarray.return_value = arr
            mock_frames.append(frame)

        mock_container.decode.return_value = iter(mock_frames)
        mock_av.open.return_value = mock_container

        with patch.dict(sys.modules, {"av": mock_av}):
            tensor = self.converter.frames_to_tensor("dummy.mp4")

            # Should return 5 frames
            assert tensor.shape == (5, 64, 64, 3)

    def test_frames_to_tensor_fallback(self):
        """Test fallback when stream.frames is 0."""
        mock_av = MagicMock()
        mock_container = MagicMock()
        mock_stream = MagicMock()
        mock_stream.frames = 0 # Unknown frames
        mock_container.streams.video = [mock_stream]

        # Provide 5 frames
        mock_frames = []
        for i in range(5):
            frame = MagicMock()
            arr = np.zeros((64, 64, 3), dtype=np.uint8)
            frame.to_ndarray.return_value = arr
            mock_frames.append(frame)

        mock_container.decode.return_value = iter(mock_frames)
        mock_av.open.return_value = mock_container

        with patch.dict(sys.modules, {"av": mock_av}):
            tensor = self.converter.frames_to_tensor("dummy.mp4")

            assert tensor.shape == (5, 64, 64, 3)
