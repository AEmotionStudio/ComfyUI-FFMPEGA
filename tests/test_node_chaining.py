"""Tests for upstream input chaining on Load / Extract nodes.

Verifies that LoadVideoPathNode, FrameExtractNode, and LoadImagePathNode
accept the new optional IMAGE, AUDIO, and path inputs, and that override
logic works correctly.
"""

import os
import sys
import types

import pytest

# Ensure conftest.py has run for mocking, then add additional mocks
# that these specific node imports need.

# Mock sanitize if not already present
pkg_name = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
core_key = f"{pkg_name}.core"
sanitize_key = f"{pkg_name}.core.sanitize"
executor_key = f"{pkg_name}.core.executor"
preview_key = f"{pkg_name}.core.executor.preview"

if core_key not in sys.modules:
    core_mod = types.ModuleType(core_key)
    core_mod.__path__ = [os.path.join(sys.modules[pkg_name].__path__[0], "core")]
    sys.modules[core_key] = core_mod

if sanitize_key not in sys.modules:
    sanitize_mod = types.ModuleType(sanitize_key)
    sanitize_mod.validate_video_path = lambda p: None
    sys.modules[sanitize_key] = sanitize_mod

if executor_key not in sys.modules:
    executor_mod = types.ModuleType(executor_key)
    executor_mod.__path__ = [os.path.join(
        sys.modules[pkg_name].__path__[0], "core", "executor",
    )]
    sys.modules[executor_key] = executor_mod

if preview_key not in sys.modules:
    preview_mod = types.ModuleType(preview_key)

    class _MockPreviewGen:
        def extract_frames(self, **kwargs):
            return []

    preview_mod.PreviewGenerator = _MockPreviewGen
    sys.modules[preview_key] = preview_mod

# Add missing folder_paths helpers
fp = sys.modules["folder_paths"]
if not hasattr(fp, "get_annotated_filepath"):
    fp.get_annotated_filepath = lambda v: os.path.join("/tmp/comfyui_input", v) if v else ""
if not hasattr(fp, "exists_annotated_filepath"):
    fp.exists_annotated_filepath = lambda v: True
if not hasattr(fp, "filter_files_content_types"):
    fp.filter_files_content_types = lambda files, types: files
if not hasattr(fp, "get_input_directory"):
    fp.get_input_directory = lambda: "/tmp/comfyui_input"
if not hasattr(fp, "get_temp_directory"):
    fp.get_temp_directory = lambda: "/tmp/comfyui_temp"

import torch

# Set up full package hierarchy so relative imports work in node modules
_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure the nodes subpackage is registered properly
nodes_key = f"{pkg_name}.nodes"
if nodes_key not in sys.modules:
    nodes_mod = types.ModuleType(nodes_key)
    nodes_mod.__path__ = [os.path.join(_proj_root, "nodes")]
    nodes_mod.__package__ = nodes_key
    sys.modules[nodes_key] = nodes_mod

# Now import node modules through the package (relative imports will work)
import importlib

_lvp = importlib.import_module(f"{pkg_name}.nodes.load_video_path_node")
_fe = importlib.import_module(f"{pkg_name}.nodes.frame_extract_node")
_lip = importlib.import_module(f"{pkg_name}.nodes.load_image_path_node")

LoadVideoPathNode = _lvp.LoadVideoPathNode
FrameExtractNode = _fe.FrameExtractNode
LoadImagePathNode = _lip.LoadImagePathNode


# ========================================================================
# INPUT_TYPES tests
# ========================================================================

class TestLoadVideoPathInputTypes:
    """Verify LoadVideoPathNode has the new optional inputs."""

    def test_has_optional_section(self):
        it = LoadVideoPathNode.INPUT_TYPES()
        assert "optional" in it

    def test_has_images_input(self):
        opt = LoadVideoPathNode.INPUT_TYPES()["optional"]
        assert "images" in opt
        assert opt["images"][0] == "IMAGE"

    def test_has_audio_input(self):
        opt = LoadVideoPathNode.INPUT_TYPES()["optional"]
        assert "audio" in opt
        assert opt["audio"][0] == "AUDIO"

    def test_has_video_path_input(self):
        opt = LoadVideoPathNode.INPUT_TYPES()["optional"]
        assert "video_path" in opt
        assert opt["video_path"][0] == "STRING"
        assert opt["video_path"][1].get("forceInput") is True

    def test_return_types_include_image_audio(self):
        assert "IMAGE" in LoadVideoPathNode.RETURN_TYPES
        assert "AUDIO" in LoadVideoPathNode.RETURN_TYPES

    def test_return_names_include_images_audio(self):
        assert "images" in LoadVideoPathNode.RETURN_NAMES
        assert "audio" in LoadVideoPathNode.RETURN_NAMES


class TestFrameExtractInputTypes:
    """Verify FrameExtractNode has the new optional inputs."""

    def test_has_images_input(self):
        opt = FrameExtractNode.INPUT_TYPES()["optional"]
        assert "images" in opt
        assert opt["images"][0] == "IMAGE"

    def test_has_audio_input(self):
        opt = FrameExtractNode.INPUT_TYPES()["optional"]
        assert "audio" in opt
        assert opt["audio"][0] == "AUDIO"

    def test_has_input_video_path(self):
        opt = FrameExtractNode.INPUT_TYPES()["optional"]
        assert "input_video_path" in opt
        assert opt["input_video_path"][0] == "STRING"
        assert opt["input_video_path"][1].get("forceInput") is True


class TestLoadImagePathInputTypes:
    """Verify LoadImagePathNode has the new optional inputs."""

    def test_has_optional_section(self):
        it = LoadImagePathNode.INPUT_TYPES()
        assert "optional" in it

    def test_has_images_input(self):
        opt = LoadImagePathNode.INPUT_TYPES()["optional"]
        assert "images" in opt
        assert opt["images"][0] == "IMAGE"

    def test_has_image_path_input(self):
        opt = LoadImagePathNode.INPUT_TYPES()["optional"]
        assert "image_path" in opt
        assert opt["image_path"][0] == "STRING"
        assert opt["image_path"][1].get("forceInput") is True

    def test_return_types_include_image(self):
        assert "IMAGE" in LoadImagePathNode.RETURN_TYPES

    def test_return_names_include_images(self):
        assert "images" in LoadImagePathNode.RETURN_NAMES


# ========================================================================
# Override behaviour tests
# ========================================================================

class TestLoadVideoPathOverride:
    """Verify upstream video_path overrides file picker."""

    def test_upstream_overrides_combo(self, tmp_path, monkeypatch):
        """When video_path kwarg is set, it should be used instead of combo."""
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"\x00" * 100)

        monkeypatch.setattr(
            _lvp, "_probe_video",
            lambda p: {
                "width": 1920, "height": 1080,
                "fps": 30.0, "duration": 10.0, "total_frames": 300,
            },
        )

        node = LoadVideoPathNode()
        result = node.load_path(
            video="nonexistent.mp4",
            video_path=str(video_file),
        )
        assert result["result"][0] == str(video_file)

    def test_passthrough_images(self, tmp_path, monkeypatch):
        """Upstream images should be passed through in result."""
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"\x00" * 100)

        monkeypatch.setattr(
            _lvp, "_probe_video",
            lambda p: {
                "width": 1920, "height": 1080,
                "fps": 30.0, "duration": 10.0, "total_frames": 300,
            },
        )

        fake_images = torch.randn(4, 512, 512, 3)
        node = LoadVideoPathNode()
        result = node.load_path(
            video="nonexistent.mp4",
            video_path=str(video_file),
            images=fake_images,
        )
        # images_out is at index 5
        assert torch.equal(result["result"][5], fake_images)

    def test_passthrough_audio(self, tmp_path, monkeypatch):
        """Upstream audio should be passed through in result."""
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"\x00" * 100)

        monkeypatch.setattr(
            _lvp, "_probe_video",
            lambda p: {
                "width": 1920, "height": 1080,
                "fps": 30.0, "duration": 10.0, "total_frames": 300,
            },
        )

        fake_audio = {"waveform": torch.randn(1, 2, 44100), "sample_rate": 44100}
        node = LoadVideoPathNode()
        result = node.load_path(
            video="nonexistent.mp4",
            video_path=str(video_file),
            audio=fake_audio,
        )
        # audio_out is at index 6
        assert result["result"][6] is fake_audio

    def test_empty_defaults_when_no_upstream(self, tmp_path, monkeypatch):
        """Without upstream inputs, IMAGE/AUDIO outputs should be empty defaults."""
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"\x00" * 100)

        monkeypatch.setattr(
            _lvp, "_probe_video",
            lambda p: {
                "width": 1920, "height": 1080,
                "fps": 30.0, "duration": 10.0, "total_frames": 300,
            },
        )
        monkeypatch.setattr(
            _lvp.folder_paths, "get_annotated_filepath",
            lambda v: str(video_file),
        )

        node = LoadVideoPathNode()
        result = node.load_path(video="test.mp4")
        # images_out should be a 1x64x64x3 zero tensor
        assert result["result"][5].shape == (1, 64, 64, 3)
        # audio_out should be silence dict
        assert result["result"][6]["sample_rate"] == 44100


class TestLoadImagePathOverride:
    """Verify upstream image_path overrides file picker."""

    def test_upstream_overrides_combo(self, tmp_path):
        """When image_path kwarg is set, it should be used."""
        img_file = tmp_path / "test.png"
        img_file.write_bytes(b"\x00" * 100)

        node = LoadImagePathNode()
        result = node.load_image_path(
            image="nonexistent.png",
            image_path=str(img_file),
        )
        assert result["result"][0] == str(img_file)

    def test_passthrough_images(self, tmp_path):
        """Upstream images should be passed through."""
        img_file = tmp_path / "test.png"
        img_file.write_bytes(b"\x00" * 100)

        fake_images = torch.randn(1, 256, 256, 3)
        node = LoadImagePathNode()
        result = node.load_image_path(
            image="nonexistent.png",
            image_path=str(img_file),
            images=fake_images,
        )
        # images_out is at index 2
        assert torch.equal(result["result"][2], fake_images)

    def test_empty_default_when_no_upstream(self, tmp_path):
        """Without upstream images, IMAGE output should be empty default."""
        img_file = tmp_path / "test.png"
        img_file.write_bytes(b"\x00" * 100)

        node = LoadImagePathNode()
        result = node.load_image_path(
            image="nonexistent.png",
            image_path=str(img_file),
        )
        assert result["result"][2].shape == (1, 64, 64, 3)
