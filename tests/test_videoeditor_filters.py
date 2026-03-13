"""Tests for videoeditor.processing.filters preset builder."""

import json
import pytest

from videoeditor.processing.filters import (
    build_filter_preset,
    has_filter_preset,
    PRESET_NAMES,
)


class TestBuildFilterPreset:
    """Unit tests for build_filter_preset()."""

    def test_empty_json_returns_empty(self):
        vf, fc = build_filter_preset("")
        assert vf == [] and fc == ""

    def test_empty_dict_returns_empty(self):
        vf, fc = build_filter_preset("{}")
        assert vf == [] and fc == ""

    def test_none_preset_returns_empty(self):
        vf, fc = build_filter_preset(json.dumps({"preset": "none"}))
        assert vf == [] and fc == ""

    def test_cinematic_full_intensity(self):
        """Cinematic at 100% should return a single -vf filter."""
        vf, fc = build_filter_preset(json.dumps({"preset": "cinematic", "intensity": 1.0}))
        assert len(vf) == 1
        assert "eq=" in vf[0]
        assert "saturation=0.7" in vf[0]
        assert fc == ""

    def test_vintage_full_intensity(self):
        vf, fc = build_filter_preset(json.dumps({"preset": "vintage"}))
        assert len(vf) == 1
        assert "colorbalance" in vf[0]
        assert fc == ""

    def test_noir_full_intensity(self):
        vf, fc = build_filter_preset(json.dumps({"preset": "noir"}))
        assert len(vf) == 1
        assert "saturation=0.0" in vf[0]

    def test_sepia_full_intensity(self):
        vf, fc = build_filter_preset(json.dumps({"preset": "sepia"}))
        assert len(vf) == 1
        assert "colorchannelmixer" in vf[0]

    def test_b_and_w(self):
        vf, fc = build_filter_preset(json.dumps({"preset": "b_and_w"}))
        assert len(vf) == 1
        assert "saturation=0.0" in vf[0]

    def test_reduced_intensity_uses_blend(self):
        """Below 100% intensity should produce a filter_complex with split→blend."""
        vf, fc = build_filter_preset(json.dumps({"preset": "cinematic", "intensity": 0.5}))
        assert vf == []
        assert "split" in fc
        assert "blend" in fc
        assert "all_opacity=0.50" in fc

    def test_comic_book_is_complex(self):
        """Comic book preset should return a filter_complex, not -vf."""
        vf, fc = build_filter_preset(json.dumps({"preset": "comic_book"}))
        assert vf == []
        assert "edgedetect" in fc
        assert "blend" in fc

    def test_thermal_is_complex(self):
        vf, fc = build_filter_preset(json.dumps({"preset": "thermal"}))
        assert vf == []
        assert "pseudocolor" in fc

    def test_comic_book_reduced_intensity(self):
        """Complex preset at reduced intensity wraps in split→blend."""
        vf, fc = build_filter_preset(json.dumps({"preset": "comic_book", "intensity": 0.7}))
        assert vf == []
        assert "__orig" in fc
        assert "all_opacity=0.70" in fc

    def test_unknown_preset_returns_empty(self):
        vf, fc = build_filter_preset(json.dumps({"preset": "totally_unknown"}))
        assert vf == [] and fc == ""

    def test_invalid_json_returns_empty(self):
        vf, fc = build_filter_preset("not json!!")
        assert vf == [] and fc == ""

    def test_intensity_clamped(self):
        """Intensity should be clamped to [0, 1]."""
        vf, fc = build_filter_preset(json.dumps({"preset": "cinematic", "intensity": 5.0}))
        # 5.0 clamped to 1.0 → full intensity → returns vf, not blend
        assert len(vf) == 1
        assert fc == ""

    def test_zero_intensity_uses_blend(self):
        vf, fc = build_filter_preset(json.dumps({"preset": "cinematic", "intensity": 0.0}))
        assert vf == []
        assert "all_opacity=0.00" in fc

    def test_all_simple_presets_produce_valid_filters(self):
        """Every preset in the registry should produce non-empty output."""
        for name in PRESET_NAMES:
            vf, fc = build_filter_preset(json.dumps({"preset": name}))
            assert vf or fc, f"Preset '{name}' produced no output"

    def test_case_insensitive(self):
        vf, fc = build_filter_preset(json.dumps({"preset": "CINEMATIC"}))
        assert len(vf) == 1

    def test_preset_with_whitespace(self):
        vf, fc = build_filter_preset(json.dumps({"preset": " vintage "}))
        assert len(vf) == 1


class TestHasFilterPreset:
    """Test the quick-check helper."""

    def test_empty_returns_false(self):
        assert has_filter_preset("") is False
        assert has_filter_preset("{}") is False

    def test_none_returns_false(self):
        assert has_filter_preset(json.dumps({"preset": "none"})) is False

    def test_valid_preset_returns_true(self):
        assert has_filter_preset(json.dumps({"preset": "cinematic"})) is True

    def test_invalid_json_returns_false(self):
        assert has_filter_preset("not json") is False
