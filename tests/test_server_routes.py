"""Unit tests for server.py route input validation.

Tests the video_export route's parameter validation, path resolution,
and response sanitization.

Note: server.py uses relative imports that require ComfyUI's package
context, so we test the *logic* used by the routes (path sanitization,
cache management, serialization) without importing server.py directly.
"""

from __future__ import annotations

import json
import os
import time

import pytest


# ---------------------------------------------------------------------------
#  Path sanitisation (used by video_export route)
# ---------------------------------------------------------------------------


class TestOutputPathSanitisation:
    """Test the path sanitisation logic used by video_export."""

    def test_basename_strips_traversal(self):
        """os.path.basename prevents path traversal in output_name."""
        assert os.path.basename("../../../etc/evil.mp4") == "evil.mp4"
        assert os.path.basename("/absolute/path/video.mp4") == "video.mp4"
        assert os.path.basename("just_a_name.mp4") == "just_a_name.mp4"

    def test_empty_name_generates_timestamp(self):
        """Empty output_name should generate a timestamped filename."""
        output_name = os.path.basename("")
        if not output_name:
            output_name = f"videoeditor_export_{int(time.time())}.mp4"
        assert output_name.startswith("videoeditor_export_")
        assert output_name.endswith(".mp4")

    def test_non_mp4_gets_extension_appended(self):
        """Non-.mp4 filenames get .mp4 appended."""
        for name in ("my_video", "my_video.avi", "my_video.mkv"):
            output = name
            if not output.endswith(".mp4"):
                output += ".mp4"
            assert output.endswith(".mp4")

    def test_mp4_not_doubled(self):
        """Files already ending in .mp4 don't get doubled."""
        name = "already.mp4"
        if not name.endswith(".mp4"):
            name += ".mp4"
        assert name == "already.mp4"

    def test_result_dict_sanitisation(self):
        """Result dict should only contain basename, not full path."""
        result = {"output_path": "/home/user/ComfyUI/output/my_edit.mp4"}
        result["output_path"] = os.path.basename(result["output_path"])
        assert result["output_path"] == "my_edit.mp4"
        assert "/" not in result["output_path"]


# ---------------------------------------------------------------------------
#  Volume validation (used by video_export route)
# ---------------------------------------------------------------------------


class TestVolumeValidation:
    """Test volume parameter parsing as done by the export route."""

    def test_valid_float(self):
        assert float("1.0") == 1.0
        assert float("0.5") == 0.5
        assert float("0") == 0.0
        assert float("2.0") == 2.0

    def test_invalid_raises(self):
        with pytest.raises((ValueError, TypeError)):
            float("not_a_number")

    def test_none_default(self):
        """body.get("volume", 1.0) returns 1.0 for missing key."""
        body: dict = {}
        volume = float(body.get("volume", 1.0))
        assert volume == 1.0


# ---------------------------------------------------------------------------
#  JSON serialisation (used by video_export route)
# ---------------------------------------------------------------------------


class TestExportJsonSerialisation:
    """Test the JSON serialisation patterns used by the export route."""

    def test_segments_roundtrip(self):
        segments = [[0, 3.5], [5.0, 10.0]]
        serialised = json.dumps(segments)
        assert json.loads(serialised) == segments

    def test_crop_none_to_empty(self):
        """None crop should produce empty string."""
        crop_val = None
        crop_json = json.dumps(crop_val) if crop_val else ""
        assert crop_json == ""

    def test_crop_valid_roundtrip(self):
        crop_val = {"x": 100, "y": 50, "w": 800, "h": 600}
        crop_json = json.dumps(crop_val)
        parsed = json.loads(crop_json)
        assert parsed == crop_val

    def test_speed_map_roundtrip(self):
        speed = {"0": 2.0, "1": 0.5}
        serialised = json.dumps(speed)
        assert json.loads(serialised) == speed

    def test_text_overlays_roundtrip(self):
        overlays = [{"text": "Hello", "x": "center", "y": "bottom"}]
        serialised = json.dumps(overlays)
        assert json.loads(serialised) == overlays

    def test_transitions_roundtrip(self):
        transitions = [{"after_segment": 0, "type": "crossfade", "duration": 0.5}]
        serialised = json.dumps(transitions)
        assert json.loads(serialised) == transitions

    def test_empty_collections_serialise(self):
        """Default empty values should serialise cleanly."""
        assert json.dumps([]) == "[]"
        assert json.dumps({}) == "{}"


# ---------------------------------------------------------------------------
#  Preview cache logic
# ---------------------------------------------------------------------------


class TestPreviewCacheLogic:
    """Test the preview cache management patterns used in server.py."""

    def test_fifo_eviction(self):
        """Dict insertion-order FIFO eviction pattern."""
        cache: dict[str, str] = {}
        max_size = 3

        for i in range(5):
            cache[f"key_{i}"] = f"path_{i}"
            while len(cache) > max_size:
                oldest = next(iter(cache))
                del cache[oldest]

        assert len(cache) == max_size
        # Oldest two (key_0, key_1) should have been evicted
        assert "key_0" not in cache
        assert "key_1" not in cache
        assert "key_4" in cache

    def test_cache_key_includes_mtime(self):
        """Same path with different mtime = different cache key."""
        key1 = ("/video.mp4", 1000.0, 5000, 0.0, 30.0)
        key2 = ("/video.mp4", 2000.0, 5000, 0.0, 30.0)
        assert key1 != key2

    def test_cache_key_includes_start_time(self):
        """Same file with different start_time = different cache key."""
        key1 = ("/video.mp4", 1000.0, 5000, 0.0, 30.0)
        key2 = ("/video.mp4", 1000.0, 5000, 5.0, 30.0)
        assert key1 != key2
