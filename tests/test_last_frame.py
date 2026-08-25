"""Tests for the Save/Load Last Frame node pair.

The pair exists so a scene can be continued across queue runs, so the tests
that matter are: the passthrough is bit-exact (that is the whole reason the
tensor path is preferred over re-decoding the mp4), the slot holds exactly
what the last run wrote, and a cold slot degrades usefully instead of
handing a black frame to the next generation.
"""

import os
import shutil
import subprocess
import sys
import types

import pytest

torch = pytest.importorskip("torch")
np = pytest.importorskip("numpy")

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture(autouse=True)
def mock_folder_paths(tmp_path):
    """folder_paths with a real get_save_image_path (it must split subfolders)."""
    import importlib

    fp = sys.modules.get("folder_paths")
    if fp is None:
        fp = types.ModuleType("folder_paths")
        sys.modules["folder_paths"] = fp

    output_dir = str(tmp_path / "output")
    temp_dir = str(tmp_path / "temp")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

    def get_save_image_path(prefix, out_dir, *_a, **_kw):
        subfolder = os.path.dirname(os.path.normpath(prefix))
        filename = os.path.basename(os.path.normpath(prefix))
        full = os.path.join(out_dir, subfolder)
        if os.path.commonpath((out_dir, os.path.abspath(full))) != out_dir:
            raise Exception("Saving image outside the output folder is not allowed.")
        return full, filename, 1, subfolder, prefix

    fp.get_output_directory = lambda: output_dir
    fp.get_temp_directory = lambda: temp_dir
    fp.get_input_directory = lambda: str(tmp_path / "input")
    fp.get_save_image_path = get_save_image_path

    # These modules bind folder_paths at import time.
    for mod in ("core.last_frame", "nodes.save_last_frame_node"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    yield fp


@pytest.fixture
def save_node():
    from nodes.save_last_frame_node import SaveLastFrameNode
    return SaveLastFrameNode()


@pytest.fixture
def load_node():
    from loadlast.load_last_frame import LoadLastFrame
    return LoadLastFrame()


def ramp_batch(n=8, size=16):
    """n frames of increasing brightness, so frame identity is checkable."""
    frames = [torch.full((size, size, 3), i / 10.0) for i in range(n)]
    return torch.stack(frames, dim=0)


def slot_files(tmp_path, slot="default", prefix="lastframe"):
    directory = tmp_path / "output" / "ffmpega_last_frame" / slot
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.name.startswith(prefix))


class TestSaveTensorPath:
    def test_saves_single_last_frame(self, save_node, tmp_path):
        out = save_node.save_last_frame(slot_name="drone", images=ramp_batch(8))
        assert slot_files(tmp_path, "drone") == ["lastframe_00.png"]
        assert out["result"][3] == 1
        assert out["result"][2] == "drone"

    def test_passthrough_is_bit_exact(self, save_node):
        """The reason the tensor path exists — no PNG round-trip on the output."""
        images = ramp_batch(8)
        out = save_node.save_last_frame(slot_name="drone", images=images)
        assert torch.equal(out["result"][0][0], images[-1])

    def test_multiple_frames_are_chronological(self, save_node, tmp_path):
        images = ramp_batch(8)
        out = save_node.save_last_frame(
            slot_name="drone", images=images, frame_count=3,
        )
        assert slot_files(tmp_path, "drone") == [
            "lastframe_00.png", "lastframe_01.png", "lastframe_02.png",
        ]
        batch = out["result"][0]
        assert batch.shape[0] == 3
        assert torch.equal(batch[0], images[5])
        assert torch.equal(batch[2], images[7])

    def test_offset_skips_the_tail(self, save_node):
        images = ramp_batch(8)
        out = save_node.save_last_frame(
            slot_name="drone", images=images, offset_from_end=2,
        )
        assert torch.equal(out["result"][0][0], images[5])

    def test_offset_past_start_clamps_without_raising(self, save_node):
        images = ramp_batch(4)
        out = save_node.save_last_frame(
            slot_name="drone", images=images, offset_from_end=99,
        )
        assert torch.equal(out["result"][0][0], images[0])

    def test_three_dim_tensor_is_accepted(self, save_node, tmp_path):
        out = save_node.save_last_frame(
            slot_name="drone", images=torch.full((16, 16, 3), 0.5),
        )
        assert out["result"][3] == 1
        assert slot_files(tmp_path, "drone") == ["lastframe_00.png"]

    def test_empty_batch_leaves_the_slot_untouched(self, save_node, tmp_path):
        """A black PNG here would silently poison the next generation."""
        save_node.save_last_frame(slot_name="drone", images=ramp_batch(4))
        before = slot_files(tmp_path, "drone")

        out = save_node.save_last_frame(
            slot_name="drone", images=torch.zeros(0, 16, 16, 3),
        )
        assert out["result"][3] == 0
        assert slot_files(tmp_path, "drone") == before

    def test_no_source_writes_nothing(self, save_node, tmp_path):
        out = save_node.save_last_frame(slot_name="drone")
        assert out["result"][3] == 0
        assert slot_files(tmp_path, "drone") == []

    def test_slots_are_independent(self, save_node, tmp_path):
        save_node.save_last_frame(slot_name="drone_a", images=ramp_batch(4))
        save_node.save_last_frame(slot_name="drone_b", images=ramp_batch(6))
        assert slot_files(tmp_path, "drone_a") == ["lastframe_00.png"]
        assert slot_files(tmp_path, "drone_b") == ["lastframe_00.png"]

    def test_traversal_slot_stays_inside_output(self, save_node, tmp_path):
        out = save_node.save_last_frame(
            slot_name="../../etc", images=ramp_batch(4),
        )
        assert out["result"][3] == 1
        written = os.path.realpath(out["result"][1])
        assert written.startswith(os.path.realpath(str(tmp_path / "output")))


class TestOverwriteAndHistory:
    def test_stale_frames_are_pruned(self, save_node, tmp_path):
        """A 5-frame run followed by a 2-frame run must not leave 3 orphans."""
        save_node.save_last_frame(
            slot_name="drone", images=ramp_batch(8), frame_count=5,
        )
        assert len(slot_files(tmp_path, "drone")) == 5

        save_node.save_last_frame(
            slot_name="drone", images=ramp_batch(8), frame_count=2,
        )
        assert slot_files(tmp_path, "drone") == [
            "lastframe_00.png", "lastframe_01.png",
        ]

    def test_overwrite_keeps_names_stable(self, save_node, tmp_path):
        for _ in range(3):
            save_node.save_last_frame(slot_name="drone", images=ramp_batch(4))
        assert slot_files(tmp_path, "drone") == ["lastframe_00.png"]

    def test_history_accumulates(self, save_node, tmp_path):
        save_node.save_last_frame(
            slot_name="drone", images=ramp_batch(4), keep_history=True,
        )
        save_node.save_last_frame(
            slot_name="drone", images=ramp_batch(4), keep_history=True,
        )
        files = slot_files(tmp_path, "drone")
        assert files == ["lastframe_00.png", "lastframe_01.png"]


class TestLoadRoundTrip:
    def test_load_reads_back_what_save_wrote(self, save_node, load_node):
        images = ramp_batch(8)
        save_node.save_last_frame(slot_name="drone", images=images)

        out = load_node.load(slot_name="drone")
        loaded, _mask, path, w, h, count = out["result"]
        assert count == 1
        assert (w, h) == (16, 16)
        assert path.endswith("lastframe_00.png")
        # atol covers PNG 8-bit quantisation of the float tensor.
        assert torch.allclose(loaded[0], images[-1], atol=1.0 / 255.0)

    def test_batch_round_trip_stays_chronological(self, save_node, load_node):
        images = ramp_batch(8)
        save_node.save_last_frame(
            slot_name="drone", images=images, frame_count=3,
        )
        loaded = load_node.load(slot_name="drone", frame_count=3)["result"][0]
        assert loaded.shape[0] == 3
        assert torch.allclose(loaded[0], images[5], atol=1.0 / 255.0)
        assert torch.allclose(loaded[2], images[7], atol=1.0 / 255.0)

    def test_load_offset_selects_from_the_slot(self, save_node, load_node):
        images = ramp_batch(8)
        save_node.save_last_frame(
            slot_name="drone", images=images, frame_count=3,
        )
        loaded = load_node.load(
            slot_name="drone", frame_count=1, offset_from_end=1,
        )["result"][0]
        assert torch.allclose(loaded[0], images[6], atol=1.0 / 255.0)

    def test_load_caps_at_what_the_slot_holds(self, save_node, load_node):
        save_node.save_last_frame(
            slot_name="drone", images=ramp_batch(8), frame_count=2,
        )
        out = load_node.load(slot_name="drone", frame_count=10)
        assert out["result"][5] == 2

    def test_slots_do_not_bleed(self, save_node, load_node):
        save_node.save_last_frame(slot_name="drone_a", images=ramp_batch(4))
        out = load_node.load(slot_name="drone_b")
        assert out["result"][5] == 0


class TestColdSlot:
    def test_fallback_image_is_used(self, load_node):
        fallback = torch.full((1, 32, 32, 3), 0.75)
        out = load_node.load(slot_name="empty", fallback_image=fallback)
        loaded, _mask, _path, w, h, count = out["result"]
        assert torch.equal(loaded, fallback)
        assert (w, h, count) == (32, 32, 1)

    def test_missing_without_fallback_returns_black(self, load_node):
        out = load_node.load(slot_name="empty")
        assert out["result"][5] == 0
        assert torch.all(out["result"][0] == 0)

    def test_error_mode_raises(self, load_node):
        with pytest.raises(RuntimeError, match="empty"):
            load_node.load(slot_name="empty", on_missing="error")

    def test_error_mode_does_not_raise_when_populated(self, save_node, load_node):
        save_node.save_last_frame(slot_name="drone", images=ramp_batch(4))
        out = load_node.load(slot_name="drone", on_missing="error")
        assert out["result"][5] == 1


class TestIsChanged:
    def test_missing_slot_is_stable(self):
        from loadlast.load_last_frame import LoadLastFrame
        assert LoadLastFrame.IS_CHANGED(slot_name="nope") == ""

    def test_manual_mode_never_reruns(self, save_node):
        from loadlast.load_last_frame import LoadLastFrame
        save_node.save_last_frame(slot_name="drone", images=ramp_batch(4))
        assert LoadLastFrame.IS_CHANGED(
            slot_name="drone", refresh_mode="manual",
        ) == ""

    def test_hash_is_stable_when_nothing_changes(self, save_node):
        from loadlast.load_last_frame import LoadLastFrame
        save_node.save_last_frame(slot_name="drone", images=ramp_batch(4))
        first = LoadLastFrame.IS_CHANGED(slot_name="drone")
        assert first == LoadLastFrame.IS_CHANGED(slot_name="drone")
        assert first != ""

    def test_hash_changes_after_a_new_save(self, save_node):
        from loadlast.load_last_frame import LoadLastFrame
        save_node.save_last_frame(slot_name="drone", images=ramp_batch(4))
        first = LoadLastFrame.IS_CHANGED(slot_name="drone")

        # Different content and a different size, so the hash must move even
        # if mtime resolution is coarse.
        save_node.save_last_frame(
            slot_name="drone", images=ramp_batch(8, size=32), frame_count=2,
        )
        assert LoadLastFrame.IS_CHANGED(slot_name="drone") != first

    def test_widgets_affect_the_hash(self, save_node):
        from loadlast.load_last_frame import LoadLastFrame
        save_node.save_last_frame(
            slot_name="drone", images=ramp_batch(8), frame_count=3,
        )
        a = LoadLastFrame.IS_CHANGED(slot_name="drone", frame_count=1)
        b = LoadLastFrame.IS_CHANGED(slot_name="drone", frame_count=3)
        c = LoadLastFrame.IS_CHANGED(slot_name="drone", offset_from_end=1)
        assert len({a, b, c}) == 3


class TestSlotViewEntries:
    """The preview strip is built from these, so /view must be able to fetch them."""

    def test_entries_describe_output_files(self, save_node):
        from loadlast.load_last_frame import _slot_view_entries

        save_node.save_last_frame(
            slot_name="drone", images=ramp_batch(8), frame_count=2,
        )
        entries = _slot_view_entries("drone")
        assert [e["filename"] for e in entries] == [
            "lastframe_00.png", "lastframe_01.png",
        ]
        for e in entries:
            assert e["subfolder"] == "ffmpega_last_frame/drone"
            assert e["type"] == "output"
            assert e["mtime"] > 0

    def test_empty_slot_returns_nothing(self):
        from loadlast.load_last_frame import _slot_view_entries
        assert _slot_view_entries("never_used") == []

    def test_traversal_slot_does_not_escape(self):
        from loadlast.load_last_frame import _slot_view_entries
        # Must not raise, and must not resolve outside the slot root.
        for entry in _slot_view_entries("../../etc"):
            assert entry["subfolder"].startswith("ffmpega_last_frame/")


def _make_ramp_video(path, frames=10, size=32, fps=10):
    """Encode a losslessly-coded brightness ramp so frames are identifiable."""
    raw = b"".join(
        bytes([min(255, i * 25)]) * (size * size * 3) for i in range(frames)
    )
    cmd = [
        FFMPEG, "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{size}x{size}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p", str(path),
    ]
    subprocess.run(cmd, input=raw, capture_output=True, timeout=60, check=True)


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
class TestVideoPath:
    def test_last_frame_from_video(self, save_node, tmp_path):
        video = tmp_path / "ramp.mp4"
        _make_ramp_video(video)

        out = save_node.save_last_frame(
            slot_name="drone", video_path=str(video),
        )
        assert out["result"][3] == 1
        assert slot_files(tmp_path, "drone") == ["lastframe_00.png"]
        # Frame 9 of the ramp is 9*25 = 225.
        mean = float(out["result"][0][0].mean()) * 255.0
        assert abs(mean - 225) < 12, f"expected the last frame (~225), got {mean:.0f}"

    def test_multiple_frames_from_video_are_chronological(self, save_node, tmp_path):
        video = tmp_path / "ramp.mp4"
        _make_ramp_video(video)

        out = save_node.save_last_frame(
            slot_name="drone", video_path=str(video), frame_count=3,
        )
        assert out["result"][3] == 3
        batch = out["result"][0]
        means = [float(batch[i].mean()) * 255.0 for i in range(3)]
        assert means[0] < means[1] < means[2], f"not chronological: {means}"
        assert abs(means[2] - 225) < 12

    def test_offset_from_end_on_video(self, save_node, tmp_path):
        video = tmp_path / "ramp.mp4"
        _make_ramp_video(video)

        out = save_node.save_last_frame(
            slot_name="drone", video_path=str(video), offset_from_end=2,
        )
        # Frame 7 of the ramp is 7*25 = 175.
        mean = float(out["result"][0][0].mean()) * 255.0
        assert abs(mean - 175) < 12, f"expected frame 7 (~175), got {mean:.0f}"

    def test_tensor_wins_over_video_path(self, save_node, tmp_path):
        video = tmp_path / "ramp.mp4"
        _make_ramp_video(video)
        images = ramp_batch(4)

        out = save_node.save_last_frame(
            slot_name="drone", images=images, video_path=str(video),
        )
        assert torch.equal(out["result"][0][0], images[-1])

    def test_missing_video_writes_nothing(self, save_node, tmp_path):
        out = save_node.save_last_frame(
            slot_name="drone", video_path=str(tmp_path / "nope.mp4"),
        )
        assert out["result"][3] == 0
        assert slot_files(tmp_path, "drone") == []


class TestProbeResilience:
    def test_probe_without_ffprobe_returns_zeros(self, monkeypatch):
        """get_ffprobe_bin falls back to a bare name; that must not explode."""
        import core.last_frame as lf

        monkeypatch.setattr(lf, "get_ffprobe_bin", lambda: "definitely-not-ffprobe")
        assert lf.probe_video_stats("/tmp/whatever.mp4") == (0.0, 0.0, 0)

    def test_extract_without_ffmpeg_returns_empty(self, monkeypatch, tmp_path):
        import core.last_frame as lf

        video = tmp_path / "fake.mp4"
        video.write_bytes(b"not a video")
        monkeypatch.setattr(lf, "get_ffmpeg_bin", lambda: "definitely-not-ffmpeg")
        monkeypatch.setattr(lf, "get_ffprobe_bin", lambda: "definitely-not-ffprobe")
        assert lf.extract_tail_frames(str(video), 1, 0, str(tmp_path / "o")) == []

    def test_extract_on_missing_file_returns_empty(self, tmp_path):
        import core.last_frame as lf
        assert lf.extract_tail_frames(str(tmp_path / "nope.mp4")) == []
