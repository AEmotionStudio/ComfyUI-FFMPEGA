"""Tests for videoeditor.processing.color_grading filter builder."""

import json
import pytest

from videoeditor.processing.color_grading import (
    build_color_grading_filters,
    has_color_grading,
)


class TestBuildColorGradingFilters:
    """Unit tests for build_color_grading_filters()."""

    def test_empty_json_returns_empty(self):
        assert build_color_grading_filters("") == []
        assert build_color_grading_filters("{}") == []
        assert build_color_grading_filters("  ") == []

    def test_all_defaults_returns_empty(self):
        """All default values should produce no filters (skip re-encode)."""
        defaults = {
            "brightness": 0,
            "contrast": 1,
            "saturation": 1,
            "exposure": 0,
            "gamma": 1,
            "shadows_r": 0,
            "shadows_g": 0,
            "shadows_b": 0,
            "midtones_r": 0,
            "midtones_g": 0,
            "midtones_b": 0,
            "temperature": 6500,
        }
        result = build_color_grading_filters(json.dumps(defaults))
        assert result == []

    def test_brightness_only(self):
        state = {"brightness": 0.3}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        assert result[0].startswith("eq=brightness=")
        assert "0.3" in result[0]

    def test_contrast_only(self):
        state = {"contrast": 1.5}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        assert "contrast=1.5" in result[0]

    def test_saturation_only(self):
        state = {"saturation": 0.5}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        assert "saturation=0.5" in result[0]

    def test_gamma_only(self):
        state = {"gamma": 2.0}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        assert "gamma=2.0" in result[0]

    def test_exposure_maps_to_brightness(self):
        """Exposure is additively mapped to eq brightness."""
        state = {"exposure": 2.0}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        # exposure * 0.1 = 0.2 brightness
        assert "brightness=0.2" in result[0]

    def test_combined_eq_params(self):
        """Multiple eq params should be in a single eq= filter."""
        state = {"brightness": 0.2, "contrast": 1.3, "saturation": 0.8}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        assert result[0].startswith("eq=")
        assert "brightness=" in result[0]
        assert "contrast=" in result[0]
        assert "saturation=" in result[0]

    def test_color_balance_shadows(self):
        state = {"shadows_r": 0.3, "shadows_g": -0.1}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        assert "colorbalance=" in result[0]
        assert "rs=0.3" in result[0]
        assert "gs=-0.1" in result[0]

    def test_color_balance_midtones(self):
        state = {"midtones_r": 0.2, "midtones_b": -0.3}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        assert "colorbalance=" in result[0]
        assert "rm=0.2" in result[0]
        assert "bm=-0.3" in result[0]

    def test_temperature_warm(self):
        state = {"temperature": 8000}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        assert "colortemperature=temperature=8000" in result[0]

    def test_temperature_cool(self):
        state = {"temperature": 3500}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        assert "colortemperature=temperature=3500" in result[0]

    def test_temperature_near_default_skipped(self):
        """Temperature within tolerance of 6500K should be skipped."""
        state = {"temperature": 6520}
        result = build_color_grading_filters(json.dumps(state))
        assert result == []

    def test_full_combo(self):
        """All parameter types set should produce eq + colorbalance + colortemperature."""
        state = {
            "brightness": 0.1,
            "contrast": 1.2,
            "saturation": 1.3,
            "exposure": 1.0,
            "gamma": 0.9,
            "shadows_r": 0.1,
            "shadows_g": 0.0,
            "shadows_b": -0.1,
            "midtones_r": 0.0,
            "midtones_g": 0.0,
            "midtones_b": 0.0,
            "temperature": 8000,
        }
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 3  # eq, colorbalance, colortemperature
        assert result[0].startswith("eq=")
        assert result[1].startswith("colorbalance=")
        assert result[2].startswith("colortemperature=")

    def test_negative_brightness(self):
        state = {"brightness": -0.5}
        result = build_color_grading_filters(json.dumps(state))
        assert len(result) == 1
        assert "brightness=-0.5" in result[0]

    def test_invalid_json_returns_empty(self):
        assert build_color_grading_filters("not valid json") == []
        assert build_color_grading_filters("[1,2,3]") == []

    def test_null_json_returns_empty(self):
        assert build_color_grading_filters("null") == []


class TestHasColorGrading:
    """Test the quick-check helper."""

    def test_empty_returns_false(self):
        assert has_color_grading("") is False
        assert has_color_grading("{}") is False

    def test_defaults_returns_false(self):
        defaults = {"brightness": 0, "contrast": 1, "saturation": 1}
        assert has_color_grading(json.dumps(defaults)) is False

    def test_non_default_returns_true(self):
        assert has_color_grading(json.dumps({"brightness": 0.5})) is True
        assert has_color_grading(json.dumps({"temperature": 4000})) is True
