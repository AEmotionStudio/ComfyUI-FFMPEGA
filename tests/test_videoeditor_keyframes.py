"""Tests for videoeditor.processing.keyframes expression converter."""

import json
import pytest

from videoeditor.processing.keyframes import (
    keyframes_to_ffmpeg_expr,
    build_speed_keyframe_filter,
    build_volume_keyframe_filter,
    has_keyframes,
)


class TestKeyframesToFFmpegExpr:
    """Test the core keyframe → FFmpeg expression converter."""

    def test_empty_json_returns_none(self):
        assert keyframes_to_ffmpeg_expr("") is None
        assert keyframes_to_ffmpeg_expr("{}") is None
        assert keyframes_to_ffmpeg_expr("[]") is None

    def test_single_keyframe_returns_none(self):
        """Need >= 2 keyframes for interpolation."""
        data = {"keyframes": [{"time": 0, "value": 1.0, "easing": "linear"}]}
        assert keyframes_to_ffmpeg_expr(json.dumps(data)) is None

    def test_two_keyframes_linear(self):
        data = {
            "keyframes": [
                {"time": 0, "value": 1.0, "easing": "linear"},
                {"time": 5, "value": 2.0, "easing": "linear"},
            ]
        }
        expr = keyframes_to_ffmpeg_expr(json.dumps(data))
        assert expr is not None
        assert "between(t," in expr
        assert "lt(t," in expr

    def test_three_keyframes(self):
        data = {
            "keyframes": [
                {"time": 0, "value": 1.0, "easing": "linear"},
                {"time": 3, "value": 0.5, "easing": "linear"},
                {"time": 6, "value": 2.0, "easing": "linear"},
            ]
        }
        expr = keyframes_to_ffmpeg_expr(json.dumps(data))
        assert expr is not None
        # Should have 2 between() segments
        assert expr.count("between(t,") == 2

    def test_ease_in_easing(self):
        data = {
            "keyframes": [
                {"time": 0, "value": 1.0, "easing": "ease-in"},
                {"time": 5, "value": 2.0, "easing": "linear"},
            ]
        }
        expr = keyframes_to_ffmpeg_expr(json.dumps(data))
        assert expr is not None
        assert "pow(" in expr  # quadratic easing uses pow

    def test_ease_out_easing(self):
        data = {
            "keyframes": [
                {"time": 0, "value": 1.0, "easing": "ease-out"},
                {"time": 5, "value": 2.0, "easing": "linear"},
            ]
        }
        expr = keyframes_to_ffmpeg_expr(json.dumps(data))
        assert expr is not None
        assert "pow(" in expr

    def test_ease_in_out_easing(self):
        data = {
            "keyframes": [
                {"time": 0, "value": 1.0, "easing": "ease-in-out"},
                {"time": 5, "value": 2.0, "easing": "linear"},
            ]
        }
        expr = keyframes_to_ffmpeg_expr(json.dumps(data))
        assert expr is not None
        assert "pow(" in expr

    def test_step_easing(self):
        data = {
            "keyframes": [
                {"time": 0, "value": 1.0, "easing": "step"},
                {"time": 5, "value": 2.0, "easing": "linear"},
            ]
        }
        expr = keyframes_to_ffmpeg_expr(json.dumps(data))
        assert expr is not None
        # Step just returns the start value
        assert "1.0000" in expr

    def test_unsorted_keyframes_get_sorted(self):
        data = {
            "keyframes": [
                {"time": 5, "value": 2.0, "easing": "linear"},
                {"time": 0, "value": 1.0, "easing": "linear"},
            ]
        }
        expr = keyframes_to_ffmpeg_expr(json.dumps(data))
        assert expr is not None
        # Should be valid even though input was unsorted
        assert "between(t," in expr

    def test_constant_value_keyframes(self):
        """Two keyframes with same value should produce a constant."""
        data = {
            "keyframes": [
                {"time": 0, "value": 1.5, "easing": "linear"},
                {"time": 5, "value": 1.5, "easing": "linear"},
            ]
        }
        expr = keyframes_to_ffmpeg_expr(json.dumps(data))
        assert expr is not None
        assert "1.5000" in expr

    def test_invalid_json_returns_none(self):
        assert keyframes_to_ffmpeg_expr("not json") is None
        assert keyframes_to_ffmpeg_expr("[1,2]") is None

    def test_clamp_before_first_keyframe(self):
        """Value before first keyframe should clamp to first value."""
        data = {
            "keyframes": [
                {"time": 2, "value": 1.0, "easing": "linear"},
                {"time": 5, "value": 2.0, "easing": "linear"},
            ]
        }
        expr = keyframes_to_ffmpeg_expr(json.dumps(data))
        assert expr is not None
        # Should have lt(t, 2.000) check that returns 1.0
        assert "lt(t,2.000)" in expr
        assert "1.0000" in expr


class TestBuildSpeedKeyframeFilter:
    def test_returns_setpts(self):
        data = {
            "keyframes": [
                {"time": 0, "value": 1.0, "easing": "linear"},
                {"time": 5, "value": 2.0, "easing": "linear"},
            ]
        }
        result = build_speed_keyframe_filter(json.dumps(data))
        assert result is not None
        assert result.startswith("setpts=PTS/(")

    def test_empty_returns_none(self):
        assert build_speed_keyframe_filter("{}") is None


class TestBuildVolumeKeyframeFilter:
    def test_returns_volume_eval_frame(self):
        data = {
            "keyframes": [
                {"time": 0, "value": 1.0, "easing": "linear"},
                {"time": 5, "value": 0.0, "easing": "linear"},
            ]
        }
        result = build_volume_keyframe_filter(json.dumps(data))
        assert result is not None
        assert result.startswith("volume='")
        assert "eval=frame" in result

    def test_empty_returns_none(self):
        assert build_volume_keyframe_filter("{}") is None


class TestHasKeyframes:
    def test_empty_returns_false(self):
        assert has_keyframes("") is False
        assert has_keyframes("{}") is False

    def test_single_keyframe_returns_false(self):
        data = {"keyframes": [{"time": 0, "value": 1.0}]}
        assert has_keyframes(json.dumps(data)) is False

    def test_two_keyframes_returns_true(self):
        data = {
            "keyframes": [
                {"time": 0, "value": 1.0},
                {"time": 5, "value": 2.0},
            ]
        }
        assert has_keyframes(json.dumps(data)) is True

    def test_invalid_returns_false(self):
        assert has_keyframes("not json") is False
