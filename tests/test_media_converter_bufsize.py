
import unittest
from unittest.mock import MagicMock, patch
import sys
import importlib.util

class TestMediaConverterBufsize(unittest.TestCase):
    def test_images_to_video_bufsize(self):
        # Create mocks for heavy dependencies to avoid import errors
        # or side effects during test execution
        mock_torch = MagicMock()
        mock_numpy = MagicMock()
        mock_av = MagicMock()
        mock_pil = MagicMock()

        # Patch sys.modules temporarily to isolate this test from the environment
        # and prevent polluting global state for other tests
        with patch.dict(sys.modules, {
            "torch": mock_torch,
            "numpy": mock_numpy,
            "av": mock_av,
            "PIL": mock_pil,
            # Also mock core.sanitize to avoid importing pydantic etc if transitively imported
            "core.sanitize": MagicMock(),
        }):
            # Dynamically load the module under test
            # We use a unique name to ensure we get a fresh module instance
            spec = importlib.util.spec_from_file_location("core.media_converter_isolated", "core/media_converter.py")
            module = importlib.util.module_from_spec(spec)

            # Register it in sys.modules so it can be initialized
            sys.modules["core.media_converter_isolated"] = module
            spec.loader.exec_module(module)

            MediaConverter = module.MediaConverter

            # Now mock the standard library modules used inside the function
            # We patch them on the *imported module instance* to ensure we catch the calls
            with patch.object(module, 'subprocess') as mock_subprocess, \
                 patch.object(module, 'shutil') as mock_shutil, \
                 patch.object(module, 'tempfile') as mock_temp, \
                 patch.object(module, 'os') as mock_os:

                 # Setup return values
                 mock_shutil.which.return_value = "/usr/bin/ffmpeg"

                 mock_temp_file = MagicMock()
                 mock_temp_file.name = "test.mp4"
                 mock_temp.NamedTemporaryFile.return_value = mock_temp_file

                 mock_proc = MagicMock()
                 mock_proc.returncode = 0
                 mock_proc.stdin = MagicMock()
                 mock_proc.stderr.read.return_value = b""
                 mock_subprocess.Popen.return_value = mock_proc
                 # Popen constants
                 mock_subprocess.PIPE = -1
                 mock_subprocess.DEVNULL = -3

                 # Create instance
                 converter = MediaConverter()

                 # Create dummy input (mocked torch tensor)
                 mock_images = MagicMock()
                 mock_images.shape = (10, 1080, 1920, 3)

                 # Call method
                 converter.images_to_video(mock_images, fps=30)

                 # Verify bufsize
                 if not mock_subprocess.Popen.called:
                     self.fail("subprocess.Popen not called")

                 args, kwargs = mock_subprocess.Popen.call_args
                 self.assertIn("bufsize", kwargs, "bufsize argument missing")
                 self.assertEqual(kwargs["bufsize"], 16 * 1024 * 1024)

if __name__ == "__main__":
    unittest.main()
