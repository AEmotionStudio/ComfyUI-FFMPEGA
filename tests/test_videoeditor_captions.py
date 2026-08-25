"""Tests for videoeditor.processing.captions converter."""

import json
import pytest

from videoeditor.processing.captions import (
    segments_to_overlays,
    parse_srt_to_segments,
)


class TestSegmentsToOverlays:
    """Test segment → TextOverlay conversion."""

    def test_empty_returns_empty(self):
        assert segments_to_overlays([]) == []

    def test_single_segment(self):
        segs = [{"text": "Hello", "start": 1.0, "end": 3.0}]
        result = segments_to_overlays(segs)
        assert len(result) == 1
        assert result[0]["text"] == "Hello"
        assert result[0]["start_time"] == 1.0
        assert result[0]["end_time"] == 3.0

    def test_default_styling(self):
        segs = [{"text": "Test", "start": 0, "end": 1}]
        result = segments_to_overlays(segs)
        ov = result[0]
        assert ov["font_size"] == 32
        assert ov["color"] == "#ffffff"
        assert ov["alignment"] == "center"
        assert ov["x"] == "center"
        assert ov["y"] == "bottom"
        assert ov["backgroundColor"] == "#000000"

    def test_custom_styling(self):
        segs = [{"text": "Test", "start": 0, "end": 1}]
        result = segments_to_overlays(segs, style={"font_size": 48, "color": "#ff0000"})
        assert result[0]["font_size"] == 48
        assert result[0]["color"] == "#ff0000"

    def test_merge_nearby_segments(self):
        segs = [
            {"text": "Hello", "start": 0.0, "end": 1.0},
            {"text": "world", "start": 1.1, "end": 2.0},  # 0.1s gap
        ]
        result = segments_to_overlays(segs, merge_gap=0.3)
        assert len(result) == 1
        assert result[0]["text"] == "Hello world"
        assert result[0]["start_time"] == 0.0
        assert result[0]["end_time"] == 2.0

    def test_no_merge_large_gap(self):
        segs = [
            {"text": "Hello", "start": 0.0, "end": 1.0},
            {"text": "world", "start": 3.0, "end": 4.0},  # 2s gap
        ]
        result = segments_to_overlays(segs, merge_gap=0.3)
        assert len(result) == 2

    def test_skip_empty_text(self):
        segs = [
            {"text": "Hello", "start": 0, "end": 1},
            {"text": "", "start": 1, "end": 2},
            {"text": "World", "start": 2, "end": 3},
        ]
        result = segments_to_overlays(segs, merge_gap=0)
        texts = [r["text"] for r in result]
        assert "" not in texts

    def test_max_chars_prevents_merge(self):
        segs = [
            {"text": "A" * 50, "start": 0.0, "end": 1.0},
            {"text": "B" * 50, "start": 1.1, "end": 2.0},
        ]
        result = segments_to_overlays(segs, merge_gap=0.3, max_chars=60)
        assert len(result) == 2  # Too long to merge

    def test_rounding(self):
        segs = [{"text": "Hi", "start": 1.12345, "end": 3.67891}]
        result = segments_to_overlays(segs)
        assert result[0]["start_time"] == 1.12
        assert result[0]["end_time"] == 3.68


class TestParseSrtToSegments:
    """Test SRT parsing."""

    def test_empty_returns_empty(self):
        assert parse_srt_to_segments("") == []
        assert parse_srt_to_segments("  ") == []

    def test_single_subtitle(self):
        srt = "1\n00:00:01,000 --> 00:00:03,500\nHello world"
        result = parse_srt_to_segments(srt)
        assert len(result) == 1
        assert result[0]["text"] == "Hello world"
        assert abs(result[0]["start"] - 1.0) < 0.01
        assert abs(result[0]["end"] - 3.5) < 0.01

    def test_multiple_subtitles(self):
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\nFirst\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\nSecond"
        )
        result = parse_srt_to_segments(srt)
        assert len(result) == 2
        assert result[0]["text"] == "First"
        assert result[1]["text"] == "Second"

    def test_multiline_subtitle(self):
        srt = "1\n00:00:01,000 --> 00:00:03,000\nLine one\nLine two"
        result = parse_srt_to_segments(srt)
        assert result[0]["text"] == "Line one\nLine two"

    def test_timestamp_parsing(self):
        srt = "1\n01:30:45,123 --> 02:15:30,456\nTest"
        result = parse_srt_to_segments(srt)
        # 1*3600 + 30*60 + 45.123 = 5445.123
        assert abs(result[0]["start"] - 5445.123) < 0.01
