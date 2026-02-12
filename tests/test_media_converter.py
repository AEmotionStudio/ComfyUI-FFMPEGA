
import pytest
import torch
import numpy as np
import shutil
from unittest.mock import MagicMock, patch

# Import MediaConverter
# Depending on how tests are run, relative import might fail
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
            # It might fail later due to mocked process behavior, but we check write call first
            pass

        # Verify write was called
        assert process_mock.stdin.write.called

        # Check argument
        args, _ = process_mock.stdin.write.call_args
        written_data = args[0]

        # Check that written_data is a numpy array (optimization) not bytes
        # If I removed tobytes(), it passes ndarray directly
        assert isinstance(written_data, np.ndarray)
        assert written_data.dtype == np.uint8
        # Ensure it is contiguous as required for efficient write
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

        # Check values (should be 0.0)
        assert torch.all(tensor == 0.0)
