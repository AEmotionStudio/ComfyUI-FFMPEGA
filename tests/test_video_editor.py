"""Unit tests for the videoeditor processing modules.

Tests cover parsing, filter building, and edge case handling.
FFmpeg subprocess calls are mocked to avoid requiring actual binaries.
"""

from __future__ import annotations

import json
import os
import subprocess
from unittest import mock

import pytest


# ── trim.py ──────────────────────────────────────────────────────────


class TestTrimParsing:
    """Test segment JSON parsing."""

    def test_parse_valid_segments(self):
        from videoeditor.processing.trim import _parse_segments

        result = _parse_segments('[[0, 3.5], [5.0, 10.0]]')
        assert result == [(0, 3.5), (5.0, 10.0)]

    def test_parse_empty(self):
        from videoeditor.processing.trim import _parse_segments

        assert _parse_segments('[]') == []
        assert _parse_segments('') == []
        assert _parse_segments('invalid') == []

    def test_parse_filters_invalid_segments(self):
        from videoeditor.processing.trim import _parse_segments

        # end <= start should be filtered out
        result = _parse_segments('[[5, 2], [1, 3]]')
        assert result == [(1, 3)]

    def test_parse_single_element_arrays(self):
        from videoeditor.processing.trim import _parse_segments

        result = _parse_segments('[[1]]')
        assert result == []  # need at least 2 elements


# ── crop.py ──────────────────────────────────────────────────────────


class TestCropParsing:
    """Test crop rect JSON parsing."""

    def test_parse_valid_rect(self):
        from videoeditor.processing.crop import _parse_crop_rect

        result = _parse_crop_rect('{"x": 100, "y": 50, "w": 800, "h": 600}')
        assert result == (100, 50, 800, 600)

    def test_parse_empty(self):
        from videoeditor.processing.crop import _parse_crop_rect

        assert _parse_crop_rect('') is None
        assert _parse_crop_rect('{}') is None

    def test_parse_invalid_json(self):
        from videoeditor.processing.crop import _parse_crop_rect

        assert _parse_crop_rect('not json') is None

    def test_parse_zero_dimensions(self):
        from videoeditor.processing.crop import _parse_crop_rect

        assert _parse_crop_rect('{"x": 0, "y": 0, "w": 0, "h": 100}') is None
        assert _parse_crop_rect('{"x": 0, "y": 0, "w": 100, "h": 0}') is None

    def test_parse_negative_dimensions(self):
        from videoeditor.processing.crop import _parse_crop_rect

        assert _parse_crop_rect('{"x": 0, "y": 0, "w": -10, "h": 100}') is None


# ── speed.py ─────────────────────────────────────────────────────────


class TestSpeedFilters:
    """Test speed filter generation."""

    def test_normal_speed(self):
        from videoeditor.processing.speed import build_speed_filters

        vf, af = build_speed_filters('{"0": 1.0}', 0)
        assert vf is None  # no change
        assert af is None

    def test_double_speed(self):
        from videoeditor.processing.speed import build_speed_filters

        vf, af = build_speed_filters('{"0": 2.0}', 0)
        assert vf == 'setpts=PTS/2.0'
        assert af is not None
        assert 'atempo=2.0' in af

    def test_half_speed(self):
        from videoeditor.processing.speed import build_speed_filters

        vf, af = build_speed_filters('{"0": 0.5}', 0)
        assert vf == 'setpts=PTS/0.5'
        assert 'atempo=0.5' in af

    def test_quarter_speed_requires_chaining(self):
        from videoeditor.processing.speed import build_speed_filters

        vf, af = build_speed_filters('{"0": 0.25}', 0)
        assert vf == 'setpts=PTS/0.25'
        # 0.25x requires chaining: atempo=0.5,atempo=0.5
        assert af is not None
        assert af.count('atempo') >= 2

    def test_4x_speed_requires_chaining(self):
        from videoeditor.processing.speed import build_speed_filters

        vf, af = build_speed_filters('{"0": 4.0}', 0)
        assert af is not None
        assert af.count('atempo') >= 2

    def test_missing_segment(self):
        from videoeditor.processing.speed import build_speed_filters

        vf, af = build_speed_filters('{"0": 2.0}', 1)  # segment 1, not 0
        assert vf is None
        assert af is None

    def test_empty_map(self):
        from videoeditor.processing.speed import build_speed_filters

        vf, af = build_speed_filters('', 0)
        assert vf is None
        assert af is None


# ── audio.py ─────────────────────────────────────────────────────────


class TestAudioFilters:
    """Test audio filter/args generation."""

    def test_normal_volume(self):
        from videoeditor.processing.audio import get_audio_args

        args = get_audio_args(1.0)
        assert args == ['-c:a', 'copy']

    def test_mute(self):
        from videoeditor.processing.audio import get_audio_args

        args = get_audio_args(0.0)
        assert args == ['-an']

    def test_half_volume(self):
        from videoeditor.processing.audio import get_audio_args

        args = get_audio_args(0.5)
        assert '-af' in args
        assert any('volume=0.5' in a for a in args)

    def test_clamp_max(self):
        from videoeditor.processing.audio import build_audio_filter

        filt, muted = build_audio_filter(3.0)
        # Should clamp to 2.0
        assert filt is not None
        assert '2.0' in filt
        assert not muted


# ── text_overlay.py ──────────────────────────────────────────────────


class TestTextOverlay:
    """Test drawtext filter generation."""

    def test_single_overlay(self):
        from videoeditor.processing.text_overlay import build_drawtext_filters

        overlays = json.dumps([{
            "text": "Hello",
            "x": "center",
            "y": "bottom",
            "font_size": 48,
            "color": "white",
        }])
        filters = build_drawtext_filters(overlays)
        assert len(filters) == 1
        assert 'drawtext' in filters[0]
        assert 'Hello' in filters[0]

    def test_empty_overlays(self):
        from videoeditor.processing.text_overlay import build_drawtext_filters

        assert build_drawtext_filters('[]') == []
        assert build_drawtext_filters('') == []

    def test_time_range(self):
        from videoeditor.processing.text_overlay import build_drawtext_filters

        overlays = json.dumps([{
            "text": "Timed",
            "x": "center",
            "y": "center",
            "font_size": 32,
            "color": "white",
            "start_time": 1.0,
            "end_time": 5.0,
        }])
        filters = build_drawtext_filters(overlays)
        assert len(filters) == 1
        assert 'enable' in filters[0]
        assert 'between' in filters[0]


# ── transitions.py ──────────────────────────────────────────────────


class TestTransitions:
    """Test transition config parsing."""

    def test_parse_valid(self):
        from videoeditor.processing.transitions import parse_transitions

        data = json.dumps([
            {"after_segment": 0, "type": "crossfade", "duration": 0.5},
        ])
        result = parse_transitions(data)
        assert len(result) == 1
        assert result[0]["type"] == "crossfade"
        assert result[0]["duration"] == 0.5

    def test_parse_empty(self):
        from videoeditor.processing.transitions import parse_transitions

        assert parse_transitions('') == []
        assert parse_transitions('[]') == []

    def test_parse_clamps_duration(self):
        from videoeditor.processing.transitions import parse_transitions

        data = json.dumps([
            {"after_segment": 0, "type": "crossfade", "duration": 100},
        ])
        result = parse_transitions(data)
        assert result[0]["duration"] == 5.0  # clamped to max

    def test_parse_invalid_type_defaults(self):
        from videoeditor.processing.transitions import parse_transitions

        data = json.dumps([
            {"after_segment": 0, "type": "nonexistent", "duration": 0.5},
        ])
        result = parse_transitions(data)
        assert result[0]["type"] == "crossfade"  # default


# ── export.py ──────────────────────────────────────────────────────


class TestExportHelpers:
    """Test export pipeline helper functions."""

    def test_has_speed_changes_empty(self):
        from videoeditor.processing.export import _has_speed_changes

        assert not _has_speed_changes('')
        assert not _has_speed_changes('{}')
        assert not _has_speed_changes('{"0": 1.0}')

    def test_has_speed_changes_true(self):
        from videoeditor.processing.export import _has_speed_changes

        assert _has_speed_changes('{"0": 2.0}')
        assert _has_speed_changes('{"1": 0.5}')

    def test_parse_segments(self):
        from videoeditor.processing.export import _parse_segments

        result = _parse_segments('[[0, 5], [7, 10]]')
        assert result == [(0, 5), (7, 10)]

    def test_error_dict(self):
        from videoeditor.processing.export import _error

        result = _error("test error")
        assert not result["success"]
        assert result["error"] == "test error"
