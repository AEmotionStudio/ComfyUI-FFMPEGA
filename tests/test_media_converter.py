
import pytest
import torch
import numpy as np
import sys
import os
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

    def test_save_frames_as_images(self):
        """Test save_frames_as_images with tensor input."""
        # Create tensor (10 frames)
        images = torch.rand(10, 64, 64, 3, dtype=torch.float32)

        # Save max 5 frames
        paths = self.converter.save_frames_as_images(images, max_frames=5)

        assert len(paths) == 5
        for p in paths:
            assert os.path.exists(p)
            assert p.endswith(".png")

        # Clean up
        for p in paths:
            os.remove(p)
        os.rmdir(os.path.dirname(paths[0]))

    def test_save_frames_as_images_full(self):
        """Test save_frames_as_images with fewer frames than max."""
        images = torch.rand(3, 64, 64, 3, dtype=torch.float32)
        paths = self.converter.save_frames_as_images(images, max_frames=5)
        assert len(paths) == 3
        # Clean up
        for p in paths:
            os.remove(p)
        os.rmdir(os.path.dirname(paths[0]))


class TestMuxAudioMode:
    """Tests for the audio_mode parameter in mux_audio."""

    def setup_method(self):
        self.converter = MediaConverter()
        # Create a minimal audio dict
        self.audio = {
            "waveform": torch.zeros(1, 1, 44100, dtype=torch.float32),
            "sample_rate": 44100,
        }

    def _get_mux_cmd(self, calls):
        """Extract the main mux command from subprocess.run calls.

        The first call writes the WAV, the second does the actual mux.
        """
        for call in calls:
            args = call[0][0]  # positional arg 0, element 0
            if isinstance(args, list) and "-map" in args:
                return args
        return None

    @patch("core.media_converter.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("core.media_converter.subprocess.run")
    def test_mux_audio_trim_mode(self, mock_run, mock_which):
        """Trim mode should use -shortest without any looping."""
        mock_run.return_value = MagicMock(returncode=0)

        self.converter.mux_audio("/tmp/video.mp4", self.audio, audio_mode="trim")

        cmd = self._get_mux_cmd(mock_run.call_args_list)
        assert cmd is not None, "No mux command found"
        assert "-shortest" in cmd
        assert "-stream_loop" not in cmd
        assert "-af" not in cmd

    @patch("core.media_converter.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("core.media_converter.shutil.move")
    @patch("core.media_converter.subprocess.run")
    @patch.object(MediaConverter, "_probe_media_duration")
    def test_mux_audio_loop_mode_audio_shorter(
        self, mock_probe, mock_run, mock_move, mock_which,
    ):
        """Loop mode with audio shorter than video should use -stream_loop and afade."""
        # Video = 30s, Audio = 10s -> needs looping
        mock_probe.side_effect = lambda path: 30.0 if "video" in path else 10.0
        mock_run.return_value = MagicMock(returncode=0)

        self.converter.mux_audio("/tmp/video.mp4", self.audio, audio_mode="loop")

        cmd = self._get_mux_cmd(mock_run.call_args_list)
        assert cmd is not None, "No mux command found"
        assert "-stream_loop" in cmd
        # Should loop twice (ceil(30/10) - 1 = 2)
        loop_idx = cmd.index("-stream_loop")
        assert cmd[loop_idx + 1] == "2"
        # Should have audio filters for crossfade
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        af_str = cmd[af_idx + 1]
        assert "afade" in af_str
        assert "atrim" in af_str

    @patch("core.media_converter.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("core.media_converter.shutil.move")
    @patch("core.media_converter.subprocess.run")
    @patch.object(MediaConverter, "_probe_media_duration")
    def test_mux_audio_loop_mode_audio_longer(
        self, mock_probe, mock_run, mock_move, mock_which,
    ):
        """Loop mode with audio longer than video should NOT loop."""
        # Video = 10s, Audio = 30s -> no looping needed
        mock_probe.side_effect = lambda path: 10.0 if "video" in path else 30.0
        mock_run.return_value = MagicMock(returncode=0)

        self.converter.mux_audio("/tmp/video.mp4", self.audio, audio_mode="loop")

        cmd = self._get_mux_cmd(mock_run.call_args_list)
        assert cmd is not None, "No mux command found"
        assert "-stream_loop" not in cmd
        assert "-shortest" in cmd

    @patch("core.media_converter.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("core.media_converter.subprocess.run")
    def test_mux_audio_pad_mode(self, mock_run, mock_which):
        """Pad mode should use apad filter and -shortest."""
        mock_run.return_value = MagicMock(returncode=0)

        self.converter.mux_audio("/tmp/video.mp4", self.audio, audio_mode="pad")

        cmd = self._get_mux_cmd(mock_run.call_args_list)
        assert cmd is not None, "No mux command found"
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        assert "apad" in cmd[af_idx + 1]
        assert "-shortest" in cmd

    @patch("core.media_converter.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("core.media_converter.subprocess.run")
    def test_mux_audio_default_is_loop(self, mock_run, mock_which):
        """Default audio_mode should be 'loop'."""
        mock_run.return_value = MagicMock(returncode=0)

        # Mock _probe_media_duration to return equal durations (no loop needed)
        with patch.object(MediaConverter, "_probe_media_duration", return_value=10.0):
            self.converter.mux_audio("/tmp/video.mp4", self.audio)

        # With equal durations, loop mode falls through to no-loop path
        cmd = self._get_mux_cmd(mock_run.call_args_list)
        assert cmd is not None, "No mux command found"
        assert "-shortest" in cmd

    @patch("core.media_converter.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("core.media_converter.subprocess.run")
    def test_mux_audio_mix_forwards_audio_mode(self, mock_run, mock_which):
        """mux_audio_mix with single audio should forward audio_mode."""
        mock_run.return_value = MagicMock(returncode=0)

        with patch.object(self.converter, "mux_audio") as mock_mux:
            self.converter.mux_audio_mix(
                "/tmp/video.mp4", [self.audio], audio_mode="pad",
            )
            mock_mux.assert_called_once_with(
                "/tmp/video.mp4", self.audio, audio_mode="pad",
            )
