
import sys
from unittest.mock import MagicMock
import importlib.util
import unittest
from unittest.mock import patch

# Mock dependencies
sys.modules["torch"] = MagicMock()
sys.modules["numpy"] = MagicMock()
sys.modules["av"] = MagicMock()
sys.modules["PIL"] = MagicMock()

# Load module directly from file path
file_path = "core/media_converter.py"
spec = importlib.util.spec_from_file_location("media_converter_module", file_path)
media_converter_module = importlib.util.module_from_spec(spec)
# We must add it to sys.modules so absolute imports inside it work (if any),
# but here it only imports stdlib and mocked deps.
sys.modules["media_converter_module"] = media_converter_module
spec.loader.exec_module(media_converter_module)

MediaConverter = media_converter_module.MediaConverter

class TestMediaConverterBufsize(unittest.TestCase):
    # Patching attributes on the loaded module instance
    def test_images_to_video_bufsize(self):
        # We need to patch the imported modules INSIDE the media_converter_module

        with patch.object(media_converter_module, 'shutil') as mock_shutil, \
             patch.object(media_converter_module, 'subprocess') as mock_subprocess, \
             patch.object(media_converter_module, 'tempfile') as mock_temp, \
             patch.object(media_converter_module, 'os') as mock_os:

            # Setup mocks
            mock_shutil.which.return_value = "/usr/bin/ffmpeg"

            mock_temp_obj = MagicMock()
            mock_temp_obj.name = "test.mp4"
            mock_temp.NamedTemporaryFile.return_value = mock_temp_obj

            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdin = MagicMock()
            mock_proc.stderr.read.return_value = b""

            mock_subprocess.Popen.return_value = mock_proc
            mock_subprocess.PIPE = -1
            mock_subprocess.DEVNULL = -3

            mock_images = MagicMock()
            mock_images.shape = (10, 1080, 1920, 3)

            converter = MediaConverter()
            converter.images_to_video(mock_images, fps=30)

            # Verify
            if not mock_subprocess.Popen.called:
                self.fail("subprocess.Popen not called")

            args, kwargs = mock_subprocess.Popen.call_args
            self.assertIn("bufsize", kwargs)
            self.assertEqual(kwargs["bufsize"], 16 * 1024 * 1024)
            print(f"SUCCESS: bufsize={kwargs['bufsize']}")

if __name__ == "__main__":
    unittest.main()
