"""Tests for videoeditor.processing.transform module."""

import json
import math
import pytest

from videoeditor.processing.transform import (
    build_transform_filter,
    has_transform,
    parse_transform,
)


class TestBuildTransformFilter:
    def test_disabled_returns_empty(self):
        assert build_transform_filter({"enabled": False}) == []

    def test_scale_only(self):
        result = build_transform_filter({"enabled": True, "scale": 200})
        assert len(result) >= 1
        assert any("scale=iw*2.000:ih*2.000" in f for f in result)

    def test_no_scale_at_100(self):
        result = build_transform_filter({"enabled": True, "scale": 100})
        assert not any("scale=" in f for f in result)

    def test_rotation(self):
        result = build_transform_filter({"enabled": True, "rotation": 45})
        assert any("rotate=" in f for f in result)
        # Check radians conversion: 45° ≈ 0.7854
        assert any("0.7854" in f for f in result)

    def test_no_rotation_at_zero(self):
        result = build_transform_filter({"enabled": True, "rotation": 0})
        assert not any("rotate=" in f for f in result)

    def test_flip_h(self):
        result = build_transform_filter({"enabled": True, "flip_h": True})
        assert "hflip" in result

    def test_flip_v(self):
        result = build_transform_filter({"enabled": True, "flip_v": True})
        assert "vflip" in result

    def test_both_flips(self):
        result = build_transform_filter({"enabled": True, "flip_h": True, "flip_v": True})
        assert "hflip" in result
        assert "vflip" in result

    def test_position_offset(self):
        result = build_transform_filter({
            "enabled": True, "position_x": 50, "position_y": 30,
        })
        assert any("pad=" in f for f in result)

    def test_no_position_at_zero(self):
        result = build_transform_filter({
            "enabled": True, "position_x": 0, "position_y": 0,
        })
        assert not any("pad=" in f for f in result)

    def test_opacity(self):
        result = build_transform_filter({"enabled": True, "opacity": 50})
        assert any("colorchannelmixer=aa=0.50" in f for f in result)

    def test_no_opacity_at_100(self):
        result = build_transform_filter({"enabled": True, "opacity": 100})
        assert not any("colorchannelmixer" in f for f in result)

    def test_combined(self):
        result = build_transform_filter({
            "enabled": True, "scale": 150, "rotation": 90,
            "flip_h": True, "opacity": 75,
        })
        assert any("scale=" in f for f in result)
        assert any("rotate=" in f for f in result)
        assert "hflip" in result
        assert any("colorchannelmixer" in f for f in result)

    def test_scale_clamped_min(self):
        result = build_transform_filter({"enabled": True, "scale": 1})
        assert any("scale=iw*0.100:ih*0.100" in f for f in result)

    def test_scale_clamped_max(self):
        result = build_transform_filter({"enabled": True, "scale": 500})
        assert any("scale=iw*4.000:ih*4.000" in f for f in result)


class TestHasTransform:
    def test_empty_returns_false(self):
        assert has_transform("") is False
        assert has_transform("{}") is False

    def test_enabled(self):
        assert has_transform(json.dumps({"enabled": True})) is True

    def test_disabled(self):
        assert has_transform(json.dumps({"enabled": False})) is False

    def test_invalid_json(self):
        assert has_transform("not json") is False


class TestParseTransform:
    def test_empty_returns_defaults(self):
        result = parse_transform("")
        assert result["enabled"] is False
        assert result["scale"] == 100
        assert result["rotation"] == 0
        assert result["opacity"] == 100

    def test_valid(self):
        data = {"enabled": True, "scale": 200, "rotation": -45}
        result = parse_transform(json.dumps(data))
        assert result["enabled"] is True
        assert result["scale"] == 200
        assert result["rotation"] == -45

    def test_clamped(self):
        data = {"enabled": True, "scale": 999, "rotation": 360, "opacity": -10}
        result = parse_transform(json.dumps(data))
        assert result["scale"] == 400
        assert result["rotation"] == 180
        assert result["opacity"] == 0

    def test_invalid_json(self):
        result = parse_transform("bad json")
        assert result["enabled"] is False
