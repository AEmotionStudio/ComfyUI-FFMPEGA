"""Tests for SaveVideoNode image-to-video encoding."""

import os
import shutil
import subprocess
import sys
import types
from unittest.mock import patch

import pytest

torch = pytest.importorskip("torch")

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


# Mock folder_paths before importing the node
@pytest.fixture(autouse=True)
def mock_folder_paths(tmp_path):
    """Provide a mock folder_paths module for all tests."""
    import importlib
    # Patch the *existing* module (may have been set by conftest or other tests)
    fp = sys.modules.get("folder_paths")
    if fp is None:
        fp = types.ModuleType("folder_paths")
        sys.modules["folder_paths"] = fp

    output_dir = str(tmp_path / "output")
    os.makedirs(output_dir, exist_ok=True)
    fp.get_output_directory = lambda: output_dir
    fp.get_temp_directory = lambda: str(tmp_path / "temp")
    fp.get_save_image_path = lambda prefix, out_dir, *a, **kw: (
        out_dir, prefix, 1, "", ""
    )
    # Reload so save_video_node picks up the patched module-level reference
    if "nodes.save_video_node" in sys.modules:
        importlib.reload(sys.modules["nodes.save_video_node"])
    yield fp


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

            mock_encode.assert_called_once()
            call_args, call_kwargs = mock_encode.call_args
            assert call_args[0] is images
            assert call_kwargs["fps"] == 30
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
        assert result["ui"]["frame_count"] == [0]
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
            mock_encode.assert_called_once()
            assert mock_encode.call_args.kwargs["fps"] == 24

    def test_encoding_failure_returns_empty(self, node):
        """If images_to_video raises, node returns empty gracefully."""
        images = torch.rand(5, 64, 64, 3, dtype=torch.float32)

        with patch("core.media_converter.MediaConverter.images_to_video", side_effect=RuntimeError("ffmpeg failed")):
            result = node.save_video(video_path="", images=images)

        # Should fall through to the empty-path guard
        assert result["ui"]["video"] == []
        assert result["ui"]["file_size"] == ["0 B"]


@pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="ffmpeg not installed")
class TestSaveVideoRealEncode:
    """End-to-end runs through real ffmpeg.

    Every test above mocks ``images_to_video``, so none of them touch the
    format table, the colour policy or the copy/remux/encode decision.
    """

    @staticmethod
    def _out_file(result):
        import folder_paths
        entry = result["ui"]["video"][0]
        return os.path.join(
            folder_paths.get_output_directory(),
            entry["subfolder"], entry["filename"],
        )

    @staticmethod
    def _make_source(path):
        subprocess.run(
            [FFMPEG, "-v", "error", "-y", "-f", "lavfi",
             "-i", "testsrc2=s=32x32:d=1:r=10", "-frames:v", "5",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
            check=True, timeout=60,
        )
        return str(path)

    def test_images_encode_to_mp4_by_default(self, node):
        images = torch.rand(6, 32, 32, 3, dtype=torch.float32)
        result = node.save_video(
            filename_prefix="dflt", images_a=images, fps=12,
        )
        out = self._out_file(result)
        assert out.endswith(".mp4") and os.path.getsize(out) > 0

    @pytest.mark.parametrize(
        "fmt,ext",
        [("h265-mp4", ".mp4"), ("vp9-webm", ".webm"), ("ffv1-mkv", ".mkv"),
         ("prores-mov", ".mov"), ("gif", ".gif"), ("webp", ".webp")],
    )
    def test_each_format_writes_its_own_container(self, node, fmt, ext):
        images = torch.rand(4, 32, 32, 3, dtype=torch.float32)
        result = node.save_video(
            filename_prefix=f"fmt{fmt[:4]}", images_a=images, fps=10,
            output_format=fmt, crf=32, encode_preset="ultrafast",
        )
        out = self._out_file(result)
        assert out.endswith(ext), out
        assert os.path.getsize(out) > 0

    @pytest.mark.parametrize(
        "policy,expected",
        [("sRGB (recommended)", "iec61966-2-1"),
         ("BT.709 broadcast", "bt709"),
         ("ComfyUI native match", "unknown")],
    )
    def test_colour_policy_reaches_the_saved_file(self, node, policy, expected):
        images = torch.rand(4, 32, 32, 3, dtype=torch.float32)
        result = node.save_video(
            filename_prefix="col", images_a=images, fps=10,
            output_format="h264-mp4", crf=32, encode_preset="ultrafast",
            color_policy=policy,
        )
        probe = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=color_transfer", "-of", "csv=p=0",
             self._out_file(result)],
            capture_output=True, timeout=60,
        )
        assert probe.stdout.decode().strip() == expected

    def test_source_format_stays_a_plain_copy(self, node, tmp_path):
        """The zero-cost path must not gain a transcode."""
        src = self._make_source(tmp_path / "already.mp4")
        with patch(
            "nodes.save_video_node.encode_opts.build_file_command"
        ) as no_transcode:
            result = node.save_video(
                filename_prefix="cp", video_path_a=src,
                embed_workflow=False, frame_output="none",
            )
            assert not no_transcode.called
        out = self._out_file(result)
        with open(src, "rb") as a, open(out, "rb") as b:
            assert a.read() == b.read(), "copy path altered the file"

    def test_workflow_metadata_lands_in_the_container(self, node, tmp_path):
        src = self._make_source(tmp_path / "meta_src.mp4")
        result = node.save_video(
            filename_prefix="meta", video_path_a=src,
            embed_workflow=True, frame_output="none",
            prompt={"1": {"class_type": "Test"}},
            extra_pnginfo={"workflow": {"nodes": []}},
        )
        probe = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format_tags",
             "-of", "default=nk=0", self._out_file(result)],
            capture_output=True, timeout=60,
        )
        text = probe.stdout.decode()
        assert "TAG:prompt=" in text and "TAG:workflow=" in text

    def test_matching_codec_remuxes_instead_of_re_encoding(self, node, tmp_path):
        """h264 source into h264-mp4 must stay bit-identical in the video."""
        src = self._make_source(tmp_path / "h264.mp4")
        result = node.save_video(
            filename_prefix="rmx", video_path_a=src,
            output_format="h264-mp4", embed_workflow=False,
            frame_output="none",
        )
        out = self._out_file(result)
        streams = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", out],
            capture_output=True, timeout=60,
        )
        assert streams.stdout.decode().strip() == "h264"

    def _frame_count(self, path):
        probe = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", path],
            capture_output=True, timeout=120,
        )
        return int(probe.stdout.decode().strip())

    def test_pingpong_doubles_the_clip(self, node):
        images = torch.rand(5, 32, 32, 3, dtype=torch.float32)
        result = node.save_video(
            filename_prefix="pp", images_a=images, fps=10,
            output_format="h264-mp4", crf=32, encode_preset="ultrafast",
            pingpong=True, frame_output="none",
        )
        # 5 frames forward, then the 3 interior frames back
        assert self._frame_count(self._out_file(result)) == 8

    def test_loop_count_repeats_the_clip(self, node):
        images = torch.rand(4, 32, 32, 3, dtype=torch.float32)
        result = node.save_video(
            filename_prefix="lp", images_a=images, fps=10,
            output_format="h264-mp4", crf=32, encode_preset="ultrafast",
            loop_count=2, frame_output="none",
        )
        assert self._frame_count(self._out_file(result)) == 12

    def test_ui_reports_the_frame_count_and_fps(self, node):
        """The info bar's numbers come from the file that was written."""
        images = torch.rand(7, 32, 32, 3, dtype=torch.float32)
        result = node.save_video(
            filename_prefix="fc", images_a=images, fps=12,
            output_format="h264-mp4", crf=32, encode_preset="ultrafast",
            frame_output="none",
        )
        assert result["ui"]["frame_count"] == [7]
        assert result["ui"]["frame_count"][0] == self._frame_count(
            self._out_file(result)
        )
        assert result["ui"]["fps"] == [12]

    def test_ui_frame_count_follows_pingpong(self, node):
        """Probed from the file, so it is not just ``images.shape[0]``."""
        images = torch.rand(5, 32, 32, 3, dtype=torch.float32)
        result = node.save_video(
            filename_prefix="fcpp", images_a=images, fps=10,
            output_format="h264-mp4", crf=32, encode_preset="ultrafast",
            pingpong=True, frame_output="none",
        )
        assert result["ui"]["frame_count"] == [8]

    def test_ui_fps_is_the_sources_own_when_passing_through(self, node, tmp_path):
        """A copied video keeps its rate — the ``fps`` widget does not apply."""
        src = self._make_source(tmp_path / "tenfps.mp4")  # 5 frames @ 10 fps
        result = node.save_video(
            filename_prefix="fcpt", video_path_a=src, fps=99,
            embed_workflow=False, frame_output="none",
        )
        assert result["ui"]["fps"] == [10]
        assert result["ui"]["frame_count"] == [5]

    def test_frame_output_controls_decoding(self, node, tmp_path):
        """Only applies when frames come from a file.

        An IMAGE batch that arrived on the input is forwarded as-is, since
        re-decoding it from the file we just wrote would cost time and
        quality for no gain.
        """
        src = self._make_source(tmp_path / "frames.mp4")
        none_result = node.save_video(
            filename_prefix="nof", video_path_a=src, frame_output="none",
            embed_workflow=False,
        )
        assert none_result["result"][0].shape == (1, 64, 64, 3)

        all_result = node.save_video(
            filename_prefix="allf", video_path_a=src, frame_output="all",
            embed_workflow=False,
        )
        assert all_result["result"][0].shape[0] == 5

    def test_upstream_images_pass_through_untouched(self, node):
        images = torch.rand(6, 32, 32, 3, dtype=torch.float32)
        result = node.save_video(
            filename_prefix="pt", images_a=images, fps=10,
            frame_output="none",
        )
        assert torch.equal(result["result"][0], images)

    @pytest.mark.parametrize("show_advanced", [True, False])
    def test_advanced_toggle_is_display_only(self, node, show_advanced):
        """Collapsing the section must not silently change the encode.

        ``show_advanced`` is a frontend affordance; the backend never sees it
        as permission to ignore the values the user already set.
        """
        images = torch.rand(4, 32, 32, 3, dtype=torch.float32)
        result = node.save_video(
            filename_prefix=f"adv{int(show_advanced)}", images_a=images, fps=10,
            show_advanced=show_advanced,
            output_format="vp9-webm", crf=40, color_policy="BT.709 broadcast",
            frame_output="none",
        )
        out = self._out_file(result)
        assert out.endswith(".webm")
        probe = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name,color_transfer",
             "-of", "csv=p=0", out],
            capture_output=True, timeout=60,
        )
        assert probe.stdout.decode().strip() == "vp9,bt709"

    def test_audio_is_muxed_into_an_image_encode(self, node):
        """A connected AUDIO used to be dropped on the images path."""
        images = torch.rand(10, 32, 32, 3, dtype=torch.float32)
        audio = {
            "waveform": torch.zeros(1, 2, 44100),
            "sample_rate": 44100,
        }
        result = node.save_video(
            filename_prefix="aud", images_a=images, fps=10, audio=audio,
            output_format="h264-mp4", crf=32, encode_preset="ultrafast",
            frame_output="none",
        )
        probe = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0",
             self._out_file(result)],
            capture_output=True, timeout=60,
        )
        assert "audio" in probe.stdout.decode()
