"""Tests for videoeditor.processing.ai_compose module."""

import json
import pytest

from videoeditor.processing.ai_compose import (
    parse_bg_removal_settings,
    parse_depth_settings,
    has_bg_removal,
    has_depth_effect,
    has_ai_compose,
    parse_ai_compose,
    build_bg_blur_filter,
    build_depth_bokeh_filter,
    build_fog_filter,
    build_tilt_shift_filter,
)


class TestParseBgRemovalSettings:
    def test_empty_returns_defaults(self):
        result = parse_bg_removal_settings("")
        assert result["enabled"] is False
        assert result["model"] == "bria-rmbg"
        assert result["background_type"] == "transparent"

    def test_valid_settings(self):
        data = {"enabled": True, "model": "birefnet-general", "background_type": "blur"}
        result = parse_bg_removal_settings(json.dumps(data))
        assert result["enabled"] is True
        assert result["model"] == "birefnet-general"
        assert result["background_type"] == "blur"

    def test_invalid_model_defaults(self):
        data = {"enabled": True, "model": "nonexistent"}
        result = parse_bg_removal_settings(json.dumps(data))
        assert result["model"] == "bria-rmbg"

    def test_edge_refine_clamped(self):
        data = {"enabled": True, "edge_refine": 5.0}
        result = parse_bg_removal_settings(json.dumps(data))
        assert result["edge_refine"] == 1.0

    def test_blur_strength_clamped(self):
        data = {"enabled": True, "blur_strength": 100}
        result = parse_bg_removal_settings(json.dumps(data))
        assert result["blur_strength"] == 50


class TestParseDepthSettings:
    def test_empty_returns_defaults(self):
        result = parse_depth_settings("")
        assert result["enabled"] is False
        assert result["model"] == "video-depth-anything"
        assert result["effect"] == "bokeh"

    def test_valid_settings(self):
        data = {"enabled": True, "effect": "fog", "fog_density": 0.8}
        result = parse_depth_settings(json.dumps(data))
        assert result["effect"] == "fog"
        assert result["fog_density"] == 0.8

    def test_invalid_effect_defaults(self):
        data = {"enabled": True, "effect": "invalid"}
        result = parse_depth_settings(json.dumps(data))
        assert result["effect"] == "bokeh"

    def test_focus_distance_clamped(self):
        data = {"enabled": True, "focus_distance": -1.0}
        result = parse_depth_settings(json.dumps(data))
        assert result["focus_distance"] == 0.0

    def test_tilt_shift_settings(self):
        data = {"enabled": True, "effect": "tilt-shift",
                "tilt_shift_center": 0.3, "tilt_shift_width": 0.5}
        result = parse_depth_settings(json.dumps(data))
        assert result["tilt_shift_center"] == 0.3
        assert result["tilt_shift_width"] == 0.5


class TestHasBgRemoval:
    def test_empty_false(self):
        assert has_bg_removal("") is False
        assert has_bg_removal("{}") is False

    def test_enabled_true(self):
        assert has_bg_removal(json.dumps({"enabled": True})) is True

    def test_disabled_false(self):
        assert has_bg_removal(json.dumps({"enabled": False})) is False


class TestHasDepthEffect:
    def test_empty_false(self):
        assert has_depth_effect("") is False

    def test_enabled_true(self):
        assert has_depth_effect(json.dumps({"enabled": True})) is True


class TestHasAICompose:
    def test_empty_false(self):
        assert has_ai_compose("") is False
        assert has_ai_compose("{}") is False

    def test_bg_enabled(self):
        data = {"bg_removal": {"enabled": True}}
        assert has_ai_compose(json.dumps(data)) is True

    def test_depth_enabled(self):
        data = {"depth_effect": {"enabled": True}}
        assert has_ai_compose(json.dumps(data)) is True

    def test_both_disabled(self):
        data = {"bg_removal": {"enabled": False}, "depth_effect": {"enabled": False}}
        assert has_ai_compose(json.dumps(data)) is False

    def test_invalid_json(self):
        assert has_ai_compose("not json") is False


class TestParseAICompose:
    def test_empty(self):
        result = parse_ai_compose("")
        assert result["bg_removal"]["enabled"] is False
        assert result["depth_effect"]["enabled"] is False

    def test_full(self):
        data = {
            "bg_removal": {"enabled": True, "model": "birefnet-general"},
            "depth_effect": {"enabled": True, "effect": "fog"},
        }
        result = parse_ai_compose(json.dumps(data))
        assert result["bg_removal"]["enabled"] is True
        assert result["bg_removal"]["model"] == "birefnet-general"
        assert result["depth_effect"]["effect"] == "fog"


class TestBuildBgBlurFilter:
    def test_default(self):
        result = build_bg_blur_filter()
        assert "boxblur=15:15" in result[0]

    def test_custom_strength(self):
        result = build_bg_blur_filter(25)
        assert "boxblur=25:25" in result[0]

    def test_clamped(self):
        result = build_bg_blur_filter(100)
        assert "boxblur=50:50" in result[0]


class TestBuildDepthBokehFilter:
    def test_default(self):
        result = build_depth_bokeh_filter()
        assert "boxblur" in result
        assert "0.50" in result

    def test_custom(self):
        result = build_depth_bokeh_filter(0.3, 20)
        assert "0.30" in result
        assert "20" in result


class TestBuildFogFilter:
    def test_default(self):
        result = build_fog_filter()
        assert len(result) >= 1
        assert "colorbalance" in result[0]

    def test_zero_density(self):
        result = build_fog_filter(0.0)
        # Zero density → zero opacity → near-zero colorbalance values
        assert "colorbalance" in result[0]


class TestBuildTiltShiftFilter:
    def test_default(self):
        result = build_tilt_shift_filter()
        assert "boxblur" in result
        assert "luma_radius" in result

    def test_custom(self):
        result = build_tilt_shift_filter(0.3, 0.4, 15)
        assert "0.10" in result  # top = 0.3 - 0.2 = 0.10
        assert "15" in result
