"""Tests for videoeditor.processing.compose module."""

import json
import pytest

from videoeditor.processing.compose import (
    build_pip_filter,
    build_watermark_filter,
    build_chromakey_filter,
    build_blend_filter,
    build_split_screen_filter,
    build_vignette_filter,
    build_mask_filter,
    has_compose,
    build_compose_filters,
)


class TestBuildPipFilter:
    def test_disabled_returns_none(self):
        assert build_pip_filter({"enabled": False}) is None

    def test_basic_pip(self):
        result = build_pip_filter({
            "enabled": True,
            "size": 25,
            "opacity": 100,
            "position": "bottom-right",
        })
        assert result is not None
        assert "[pip]" in result
        assert "overlay=" in result
        assert "W-w-10" in result
        assert "scale=iw*0.250" in result

    def test_pip_with_opacity(self):
        result = build_pip_filter({
            "enabled": True, "size": 30, "opacity": 50,
            "position": "top-left",
        })
        assert "colorchannelmixer=aa=0.50" in result
        assert "overlay=10:10" in result

    def test_pip_custom_position(self):
        result = build_pip_filter({
            "enabled": True, "size": 25, "opacity": 100,
            "position": "custom", "x": 100, "y": 200,
        })
        assert "overlay=100:200" in result

    def test_pip_with_timing(self):
        result = build_pip_filter({
            "enabled": True, "size": 25, "opacity": 100,
            "position": "center",
            "start_time": 2.0, "end_time": 10.0,
        })
        assert "between(t,2.00,10.00)" in result

    def test_pip_with_border(self):
        result = build_pip_filter({
            "enabled": True, "size": 25, "opacity": 100,
            "position": "center",
            "border": True, "border_color": "#ff0000", "border_width": 4,
        })
        assert "pad=" in result
        assert "0xff0000" in result

    def test_pip_center_position(self):
        result = build_pip_filter({
            "enabled": True, "size": 25, "opacity": 100,
            "position": "center",
        })
        assert "(W-w)/2" in result
        assert "(H-h)/2" in result

    def test_pip_size_clamped(self):
        result = build_pip_filter({
            "enabled": True, "size": 200, "opacity": 100,
            "position": "center",
        })
        assert "scale=iw*1.000" in result  # clamped to 100

    def test_pip_size_minimum(self):
        result = build_pip_filter({
            "enabled": True, "size": 1, "opacity": 100,
            "position": "center",
        })
        assert "scale=iw*0.050" in result  # clamped to 5


class TestBuildWatermarkFilter:
    def test_disabled_returns_none(self):
        assert build_watermark_filter({"enabled": False}) is None

    def test_no_path_returns_none(self):
        assert build_watermark_filter({"enabled": True, "path": ""}) is None

    def test_basic_watermark(self):
        result = build_watermark_filter({
            "enabled": True,
            "path": "/tmp/logo.png",
            "size": 15,
            "opacity": 80,
            "position": "bottom-right",
        })
        assert result is not None
        assert "movie=/tmp/logo.png" in result
        assert "overlay=" in result
        assert "colorchannelmixer=aa=0.80" in result


class TestBuildChromakeyFilter:
    def test_disabled_returns_empty(self):
        assert build_chromakey_filter({"enabled": False}) == []

    def test_default_green(self):
        result = build_chromakey_filter({
            "enabled": True, "color": "#00ff00",
            "similarity": 0.3, "blend": 0.1,
        })
        assert len(result) == 1
        assert "chromakey=0x00ff00:0.30:0.10" in result[0]

    def test_colorkey_mode(self):
        result = build_chromakey_filter({
            "enabled": True, "color": "#0000ff",
            "similarity": 0.5, "blend": 0.2,
            "mode": "colorkey",
        })
        assert "colorkey=" in result[0]

    def test_invalid_mode_defaults(self):
        result = build_chromakey_filter({
            "enabled": True, "color": "#00ff00",
            "similarity": 0.3, "blend": 0.1,
            "mode": "badmode",
        })
        assert "chromakey=" in result[0]


class TestBuildBlendFilter:
    def test_disabled_returns_empty(self):
        assert build_blend_filter({"enabled": False}) == []

    def test_multiply(self):
        result = build_blend_filter({
            "enabled": True, "mode": "multiply", "opacity": 0.8,
        })
        assert "blend=all_mode=multiply:all_opacity=0.80" in result[0]

    def test_invalid_mode_defaults_normal(self):
        result = build_blend_filter({
            "enabled": True, "mode": "invalid", "opacity": 1.0,
        })
        assert "all_mode=normal" in result[0]


class TestBuildSplitScreenFilter:
    def test_disabled_returns_none(self):
        assert build_split_screen_filter({"enabled": False}) is None

    def test_2h_layout(self):
        result = build_split_screen_filter({"enabled": True, "layout": "2h"})
        assert "xstack=inputs=2" in result

    def test_4grid_layout(self):
        result = build_split_screen_filter({"enabled": True, "layout": "4"})
        assert "xstack=inputs=4" in result

    def test_invalid_layout(self):
        assert build_split_screen_filter({"enabled": True, "layout": "99"}) is None


class TestBuildVignetteFilter:
    def test_disabled_returns_empty(self):
        assert build_vignette_filter({"enabled": False}) == []

    def test_basic_vignette(self):
        result = build_vignette_filter({"enabled": True, "intensity": 50})
        assert len(result) == 1
        assert "vignette=angle=" in result[0]

    def test_zero_intensity(self):
        result = build_vignette_filter({"enabled": True, "intensity": 0})
        assert "angle=0.0000" in result[0]


class TestBuildMaskFilter:
    def test_disabled_returns_empty(self):
        assert build_mask_filter({"enabled": False}) == []

    def test_blur_mask(self):
        result = build_mask_filter({"enabled": True, "effect": "blur", "invert": True})
        assert len(result) >= 1

    def test_darken_mask(self):
        result = build_mask_filter({"enabled": True, "effect": "darken"})
        assert any("drawbox" in f for f in result)


class TestHasCompose:
    def test_empty_returns_false(self):
        assert has_compose("") is False
        assert has_compose("{}") is False

    def test_all_disabled_returns_false(self):
        data = {"pip": {"enabled": False}, "watermark": {"enabled": False}}
        assert has_compose(json.dumps(data)) is False

    def test_pip_enabled_returns_true(self):
        data = {"pip": {"enabled": True}}
        assert has_compose(json.dumps(data)) is True

    def test_vignette_enabled_returns_true(self):
        data = {"vignette": {"enabled": True}}
        assert has_compose(json.dumps(data)) is True

    def test_invalid_json_returns_false(self):
        assert has_compose("not json") is False


class TestBuildComposeFilters:
    def test_empty_returns_all_none(self):
        result = build_compose_filters("{}")
        assert result["pip_filter"] is None
        assert result["watermark_filter"] is None
        assert result["chromakey"] == []
        assert result["vignette"] == []

    def test_pip_enabled(self):
        data = {"pip": {"enabled": True, "size": 25, "opacity": 100, "position": "center"}}
        result = build_compose_filters(json.dumps(data))
        assert result["pip_filter"] is not None
        assert "overlay=" in result["pip_filter"]

    def test_multiple_features(self):
        data = {
            "vignette": {"enabled": True, "intensity": 50},
            "chromakey": {"enabled": True, "color": "#00ff00", "similarity": 0.3, "blend": 0.1},
        }
        result = build_compose_filters(json.dumps(data))
        assert len(result["vignette"]) > 0
        assert len(result["chromakey"]) > 0
