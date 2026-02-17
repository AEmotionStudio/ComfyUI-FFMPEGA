
import pytest
import torch
import numpy as np
import sys
from unittest.mock import MagicMock, patch
from core.media_converter import MediaConverter

class TestFramesToTensorOptimization:
    def setup_method(self):
        self.converter = MediaConverter()

    def test_frames_to_tensor_preallocation(self):
        """Test the pre-allocation path (num_frames > 0) with optimization."""
        mock_av = MagicMock()
        mock_container = MagicMock()
        mock_stream = MagicMock()

        # Simulate 5 frames
        num_frames = 5
        mock_stream.frames = num_frames
        mock_container.streams.video = [mock_stream]

        # Create mock frames with known data
        mock_frames = []
        for i in range(num_frames):
            frame = MagicMock()
            # Fill with known pattern: i * 10
            arr = np.full((64, 64, 3), i * 10, dtype=np.uint8)
            frame.to_ndarray.return_value = arr
            mock_frames.append(frame)

        mock_container.decode.return_value = iter(mock_frames)
        mock_av.open.return_value = mock_container

        with patch.dict(sys.modules, {"av": mock_av}):
            tensor = self.converter.frames_to_tensor("dummy.mp4")

            assert tensor.shape == (5, 64, 64, 3)
            assert tensor.dtype == torch.float32

            # Verify values
            for i in range(num_frames):
                expected = (i * 10) / 255.0
                # Check slice
                assert torch.allclose(tensor[i], torch.tensor(expected)), f"Frame {i} mismatch"

            # Ensure we didn't just allocate zeros
            assert not torch.all(tensor == 0.0)
