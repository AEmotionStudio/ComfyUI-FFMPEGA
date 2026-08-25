"""Tests for LoadVideoPathNode frame decoding.

The node used to borrow SaveVideoNode's preview frame extractor without
passing a mode, so it inherited the ``preview (64)`` default and evenly
sampled every clip down to 64 frames. Even sampling keeps the whole action
with fewer frames, so downstream re-encoding played the video faster than the
source — a 121-frame clip came out at 64 frames.
"""

import os
import shutil
import subprocess
import sys
import types

import pytest

torch = pytest.importorskip("torch")

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

pytestmark = pytest.mark.skipif(
    not FFMPEG or not FFPROBE, reason="ffmpeg/ffprobe required"
)


@pytest.fixture(autouse=True)
def mock_folder_paths(tmp_path):
    """Point ComfyUI's directories at a temp tree, as the save-node tests do."""
    import importlib

    fp = sys.modules.get("folder_paths")
    if fp is None:
        fp = types.ModuleType("folder_paths")
        sys.modules["folder_paths"] = fp

    input_dir = tmp_path / "input"
    temp_dir = tmp_path / "temp"
    output_dir = tmp_path / "output"
    for d in (input_dir, temp_dir, output_dir):
        os.makedirs(d, exist_ok=True)

    fp.get_input_directory = lambda: str(input_dir)
    fp.get_temp_directory = lambda: str(temp_dir)
    fp.get_output_directory = lambda: str(output_dir)
    fp.get_annotated_filepath = lambda v: os.path.join(str(input_dir), v) if v else ""
    fp.exists_annotated_filepath = lambda v: os.path.isfile(
        os.path.join(str(input_dir), v)
    )

    if "nodes.load_video_path_node" in sys.modules:
        importlib.reload(sys.modules["nodes.load_video_path_node"])
    yield fp


@pytest.fixture
def source_video(tmp_path):
    """A 100-frame, 25 fps clip — comfortably past the old 64-frame cap."""
    path = tmp_path / "input" / "src.mp4"
    subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-f", "lavfi",
         "-i", "testsrc2=s=64x64:d=10:r=25", "-frames:v", "100",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True, timeout=60,
    )
    return str(path)


@pytest.fixture
def node():
    from nodes.load_video_path_node import LoadVideoPathNode
    return LoadVideoPathNode()


def _load(node, video, **kwargs):
    return node.load_path(video=video, **kwargs)["result"]


class TestLoadVideoPathFrameCount:

    def test_returns_every_frame(self, node, source_video):
        """The regression: 100 frames in, 100 frames out — not 64."""
        images = _load(node, source_video)[0]
        assert images.shape[0] == 100

    def test_frame_count_output_matches_the_images(self, node, source_video):
        """frame_count is predicted from metadata; it must not contradict reality."""
        result = _load(node, source_video)
        images, frame_count = result[0], result[7]
        assert images.shape[0] == frame_count

    def test_fps_output_is_the_source_rate(self, node, source_video):
        assert abs(_load(node, source_video)[8] - 25.0) < 0.01

    @pytest.mark.parametrize("kwargs,expected", [
        ({"frame_load_cap": 30}, 30),
        ({"select_every_nth": 2}, 50),
        ({"skip_first_frames": 10}, 90),
    ])
    def test_trim_widgets_are_the_only_limiters(
        self, node, source_video, kwargs, expected,
    ):
        result = _load(node, source_video, **kwargs)
        images, frame_count = result[0], result[7]
        assert images.shape[0] == expected
        assert frame_count == expected

    def test_upstream_images_pass_through_untouched(self, node, source_video):
        """A connected IMAGE batch is forwarded as-is, whatever its length."""
        passed = torch.rand(7, 16, 16, 3, dtype=torch.float32)
        result = _load(node, source_video, images=passed)
        assert result[0].shape[0] == 7
        assert result[7] == 7

    def test_does_not_reach_into_the_save_node(self):
        """The coupling that let a preview default become a load default."""
        import inspect
        from nodes import load_video_path_node

        src = inspect.getsource(load_video_path_node)
        assert "SaveVideoNode" not in src
