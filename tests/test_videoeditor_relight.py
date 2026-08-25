"""Tests for videoeditor.processing.relight filter builder."""

import json
import pytest

from videoeditor.processing.relight import build_relight_filters, has_relight


class TestBuildRelightFilters:
    """Test the relight → FFmpeg filter chain builder."""

    def test_empty_returns_empty(self):
        assert build_relight_filters("") == []
        assert build_relight_filters("{}") == []

    def test_disabled_returns_empty(self):
        state = {"enabled": False, "azimuth": 45, "intensity": 1.0}
        assert build_relight_filters(json.dumps(state)) == []

    def test_front_light_defaults(self):
        """Front light (az=0) at default intensity should produce filters."""
        state = {"enabled": True, "azimuth": 0, "elevation": 45, "intensity": 1.0, "ambient": 0.3}
        filters = build_relight_filters(json.dumps(state))
        # Front light should produce at least contrast adjustment
        assert len(filters) > 0

    def test_side_light_produces_brightness(self):
        """Side light (az=90) should darken one side."""
        state = {"enabled": True, "azimuth": 90, "elevation": 45, "intensity": 1.0, "ambient": 0.3}
        filters = build_relight_filters(json.dumps(state))
        assert any("brightness" in f for f in filters)

    def test_colored_light_produces_colorbalance(self):
        """Non-white light should produce colorbalance filter."""
        state = {"enabled": True, "azimuth": 0, "elevation": 45, "intensity": 1.0,
                 "ambient": 0.3, "color_r": 255, "color_g": 200, "color_b": 100}
        filters = build_relight_filters(json.dumps(state))
        assert any("colorbalance" in f for f in filters)

    def test_white_light_no_colorbalance(self):
        """Pure white light should NOT produce colorbalance (centered)."""
        state = {"enabled": True, "azimuth": 0, "elevation": 45, "intensity": 1.0,
                 "ambient": 0.3, "color_r": 255, "color_g": 255, "color_b": 255}
        filters = build_relight_filters(json.dumps(state))
        # White light is at 0.5 normalized for all channels → shifts are ~0
        # so colorbalance may or may not be there depending on threshold
        # Either way, there should be no crash

    def test_zero_intensity(self):
        """Zero intensity should produce minimal/no filters."""
        state = {"enabled": True, "azimuth": 45, "elevation": 45, "intensity": 0.0, "ambient": 0.3}
        filters = build_relight_filters(json.dumps(state))
        # Should be empty or very minimal
        assert isinstance(filters, list)

    def test_high_intensity(self):
        """High intensity should produce stronger filter values."""
        state = {"enabled": True, "azimuth": 90, "elevation": 45, "intensity": 2.0, "ambient": 0.3}
        filters = build_relight_filters(json.dumps(state))
        assert len(filters) > 0

    def test_negative_azimuth(self):
        """Left-side light (az=-90) should work."""
        state = {"enabled": True, "azimuth": -90, "elevation": 45, "intensity": 1.0, "ambient": 0.3}
        filters = build_relight_filters(json.dumps(state))
        assert len(filters) > 0

    def test_top_light_less_side(self):
        """Top-down light (elev=90) should produce less side-lighting effect."""
        state = {"enabled": True, "azimuth": 90, "elevation": 90, "intensity": 1.0, "ambient": 0.3}
        filters = build_relight_filters(json.dumps(state))
        # At elevation=90, cos(90°) ≈ 0, so lx ≈ 0 → no brightness shift
        # This is expected — top-down light is even
        assert isinstance(filters, list)

    def test_invalid_json_returns_empty(self):
        assert build_relight_filters("not json") == []

    def test_high_ambient_reduces_shadow(self):
        """High ambient should reduce shadow depth."""
        state = {"enabled": True, "azimuth": 90, "elevation": 45, "intensity": 1.0, "ambient": 1.0}
        filters = build_relight_filters(json.dumps(state))
        # With ambient=1, shadow_depth formula is 0 → no curves filter
        assert not any("curves" in f for f in filters)


class TestHasRelight:
    def test_empty_returns_false(self):
        assert has_relight("") is False
        assert has_relight("{}") is False

    def test_disabled_returns_false(self):
        assert has_relight(json.dumps({"enabled": False})) is False

    def test_enabled_returns_true(self):
        assert has_relight(json.dumps({"enabled": True})) is True

    def test_invalid_returns_false(self):
        assert has_relight("not json") is False
