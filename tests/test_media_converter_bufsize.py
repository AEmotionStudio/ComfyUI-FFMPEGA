
import unittest
from unittest.mock import MagicMock, patch

import pytest

torch = pytest.importorskip("torch")

from core.media_converter import MediaConverter


class TestMediaConverterBufsize(unittest.TestCase):
    """The raw-video pipe must keep its large stdin buffer.

    Writing 1080p frames through the default buffer costs many syscalls per
    frame; the 16MB buffer is a measured optimisation, so it is pinned here.
    """

    def test_images_to_video_bufsize(self):
        with patch("core.media_converter.subprocess") as mock_subprocess, \
             patch("core.media_converter.tempfile") as mock_temp:

            mock_temp_file = MagicMock()
            mock_temp_file.name = "test.mp4"
            mock_temp.NamedTemporaryFile.return_value = mock_temp_file

            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdin = MagicMock()
            mock_proc.stderr.read.return_value = b""
            mock_subprocess.Popen.return_value = mock_proc
            mock_subprocess.PIPE = -1
            mock_subprocess.DEVNULL = -3

            images = torch.rand(4, 16, 16, 3, dtype=torch.float32)
            MediaConverter().images_to_video(images, fps=30)

            if not mock_subprocess.Popen.called:
                self.fail("subprocess.Popen not called")

            _args, kwargs = mock_subprocess.Popen.call_args
            self.assertIn("bufsize", kwargs, "bufsize argument missing")
            self.assertEqual(kwargs["bufsize"], 16 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
