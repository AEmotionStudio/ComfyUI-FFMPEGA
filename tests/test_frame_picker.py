"""Tests for FramePickerNode."""

from __future__ import annotations

import json
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture()
def node():
    """Importable FramePickerNode instance."""
    from nodes.frame_picker_node import FramePickerNode
    return FramePickerNode()


@pytest.fixture()
def mock_cv2_video(monkeypatch):
    """Patch cv2.VideoCapture to return fake frames."""
    frames = [
        np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
        for _ in range(5)
    ]

    class FakeCapture:
        def __init__(self, _path):
            self._idx = 0
            self._frames = frames

        def isOpened(self):
            return True

        def get(self, prop):
            import cv2
            if prop == cv2.CAP_PROP_FPS:
                return 24.0
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return len(self._frames)
            if prop == cv2.CAP_PROP_FRAME_WIDTH:
                return 64
            if prop == cv2.CAP_PROP_FRAME_HEIGHT:
                return 64
            return 0

        def set(self, prop, value):
            import cv2
            if prop == cv2.CAP_PROP_POS_FRAMES:
                self._idx = int(value)

        def read(self):
            if self._idx < len(self._frames):
                frame = self._frames[self._idx]
                self._idx += 1
                return True, frame
            return False, None

        def release(self):
            pass

    import cv2
    monkeypatch.setattr(cv2, "VideoCapture", FakeCapture)
    return frames


# ── INPUT_TYPES ─────────────────────────────────────────────────────────

class TestInputTypes:
    def test_required_fields(self, node):
        types = node.INPUT_TYPES()
        assert "pause_on_input" in types["required"]
        assert "auto_open_editor" in types["required"]

    def test_optional_fields(self, node):
        types = node.INPUT_TYPES()
        opt = types["optional"]
        assert "images" in opt
        assert "video_path" in opt
        assert "audio" in opt
        assert "fps" in opt

    def test_hidden_fields(self, node):
        types = node.INPUT_TYPES()
        hidden = types["hidden"]
        assert "_edit_action" in hidden
        assert "unique_id" in hidden


# ── RETURN_TYPES ────────────────────────────────────────────────────────

class TestReturnTypes:
    def test_return_types(self, node):
        assert node.RETURN_TYPES == (
            "IMAGE", "STRING", "AUDIO", "FLOAT", "INT", "STRING")

    def test_return_names(self, node):
        assert node.RETURN_NAMES == (
            "images", "video_path", "audio", "fps",
            "frame_count", "selected_indices")


# ── IS_CHANGED ──────────────────────────────────────────────────────────

class TestIsChanged:
    def test_passthrough_returns_empty(self, node):
        result = node.IS_CHANGED(pause_on_input=False)
        assert result == ""

    def test_pause_returns_hash(self, node):
        result = node.IS_CHANGED(pause_on_input=True, _edit_action="none")
        assert isinstance(result, str) and len(result) == 64


# ── Execute Passthrough ────────────────────────────────────────────────

class TestPassthrough:
    def test_no_input_returns_empty(self, node):
        result = node.execute(
            pause_on_input=False, images=None, video_path="",
        )
        assert "result" in result
        images = result["result"][0]
        assert images.shape == (1, 512, 512, 3)

    def test_passthrough_with_video(self, node, mock_cv2_video, tmp_path):
        # Create a fake video file
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake")

        # Patch _is_path_sandboxed to return True
        with patch.object(type(node), '_is_path_sandboxed', return_value=True):
            result = node.execute(
                pause_on_input=False,
                video_path=str(video_file),
            )

        assert "result" in result
        images = result["result"][0]
        assert images.shape[0] == 5  # 5 frames from mock
        indices = json.loads(result["result"][5])
        assert indices == [0, 1, 2, 3, 4]


# ── VALIDATE_INPUTS ────────────────────────────────────────────────────

class TestValidateInputs:
    def test_valid_fps(self, node):
        assert node.VALIDATE_INPUTS(fps=24.0) is True
        assert node.VALIDATE_INPUTS(fps="") is True
        assert node.VALIDATE_INPUTS(fps=None) is True

    def test_invalid_fps(self, node):
        result = node.VALIDATE_INPUTS(fps="not_a_number")
        assert isinstance(result, str) and "Invalid" in result
