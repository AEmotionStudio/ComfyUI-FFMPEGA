"""Tests for videoeditor.processing.export_settings module."""

import json
import pytest

from videoeditor.processing.export_settings import (
    parse_export_settings,
    build_video_codec_args,
    build_audio_codec_args,
    build_resolution_filter,
    has_export_settings,
)


class TestParseExportSettings:
    """Test settings JSON parsing."""

    def test_empty_returns_defaults(self):
        result = parse_export_settings("")
        assert result["video_codec"] == "h264"
        assert result["crf"] == 18
        assert result["preset"] == "fast"
        assert result["format"] == "mp4"
        assert result["audio_codec"] == "aac"
        assert result["audio_bitrate"] == "192k"
        assert result["resolution"] == "source"
        assert result["extension"] == ".mp4"

    def test_custom_settings(self):
        data = {"video_codec": "h265", "crf": 23, "format": "mkv"}
        result = parse_export_settings(json.dumps(data))
        assert result["video_codec"] == "h265"
        assert result["crf"] == 23
        assert result["format"] == "mkv"
        assert result["extension"] == ".mkv"

    def test_crf_clamped(self):
        data = {"crf": 100}
        assert parse_export_settings(json.dumps(data))["crf"] == 51
        data = {"crf": -5}
        assert parse_export_settings(json.dumps(data))["crf"] == 0

    def test_webm_extension(self):
        data = {"format": "webm"}
        assert parse_export_settings(json.dumps(data))["extension"] == ".webm"

    def test_invalid_json(self):
        result = parse_export_settings("not json")
        assert result["crf"] == 18  # defaults


class TestBuildVideoCodecArgs:
    def test_h264_default(self):
        settings = parse_export_settings("{}")
        args = build_video_codec_args(settings)
        assert args[:2] == ["-c:v", "libx264"]
        assert "-crf" in args
        assert "-preset" in args
        assert "yuv420p" in args

    def test_h265(self):
        settings = parse_export_settings(json.dumps({"video_codec": "h265"}))
        args = build_video_codec_args(settings)
        assert args[1] == "libx265"

    def test_vp9(self):
        settings = parse_export_settings(json.dumps({"video_codec": "vp9"}))
        args = build_video_codec_args(settings)
        assert args[1] == "libvpx-vp9"
        assert "-b:v" in args
        assert "-deadline" in args

    def test_av1(self):
        settings = parse_export_settings(json.dumps({"video_codec": "av1"}))
        args = build_video_codec_args(settings)
        assert args[1] == "libaom-av1"
        assert "-cpu-used" in args


class TestBuildAudioCodecArgs:
    def test_aac_default(self):
        settings = parse_export_settings("{}")
        args = build_audio_codec_args(settings)
        assert args[:2] == ["-c:a", "aac"]
        assert "-b:a" in args

    def test_copy(self):
        settings = {"audio_codec": "copy"}
        args = build_audio_codec_args(settings)
        assert args == ["-c:a", "copy"]

    def test_flac(self):
        settings = {"audio_codec": "flac"}
        args = build_audio_codec_args(settings)
        assert args == ["-c:a", "flac"]

    def test_opus_with_bitrate(self):
        settings = {"audio_codec": "opus", "audio_bitrate": "256k"}
        args = build_audio_codec_args(settings)
        assert args == ["-c:a", "libopus", "-b:a", "256k"]


class TestBuildResolutionFilter:
    def test_source_returns_none(self):
        settings = {"resolution": "source"}
        assert build_resolution_filter(settings) is None

    def test_1080p(self):
        settings = {"resolution": "1080p"}
        result = build_resolution_filter(settings)
        assert result == "scale=1920:-2"

    def test_720p(self):
        settings = {"resolution": "720p"}
        assert build_resolution_filter(settings) == "scale=1280:-2"

    def test_4k(self):
        settings = {"resolution": "4k"}
        assert build_resolution_filter(settings) == "scale=3840:-2"

    def test_custom_resolution(self):
        settings = {"resolution": "1280x720"}
        assert build_resolution_filter(settings) == "scale=1280:720"

    def test_invalid_returns_none(self):
        settings = {"resolution": "foobar"}
        assert build_resolution_filter(settings) is None


class TestHasExportSettings:
    def test_empty_returns_false(self):
        assert has_export_settings("") is False
        assert has_export_settings("{}") is False

    def test_defaults_returns_false(self):
        data = {"resolution": "source", "video_codec": "h264", "crf": 18}
        assert has_export_settings(json.dumps(data)) is False

    def test_non_default_returns_true(self):
        data = {"video_codec": "h265"}
        assert has_export_settings(json.dumps(data)) is True
        data = {"crf": 23}
        assert has_export_settings(json.dumps(data)) is True

    def test_invalid_returns_false(self):
        assert has_export_settings("not json") is False
