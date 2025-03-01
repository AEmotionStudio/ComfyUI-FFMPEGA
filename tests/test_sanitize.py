"""Tests for core.sanitize module."""

import os
import tempfile

import pytest

# We can't use relative imports in tests, so mock the import path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.sanitize import (
    validate_video_path, validate_output_path, sanitize_text_param,
    redact_secret, sanitize_api_key,
)


class TestValidateVideoPath:
    """Tests for validate_video_path."""

    def test_empty_path_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_video_path("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_video_path("   ")

    def test_traversal_raises(self):
        with pytest.raises(ValueError, match="traversal"):
            validate_video_path("/tmp/../etc/passwd")

    def test_nonexistent_file_raises(self):
        with pytest.raises(ValueError, match="not found"):
            validate_video_path("/tmp/definitely_does_not_exist_12345.mp4")

    def test_valid_file_returns_resolved(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake video data")
            tmp_path = f.name
        try:
            result = validate_video_path(tmp_path)
            assert os.path.isabs(result)
            assert result == os.path.realpath(tmp_path)
        finally:
            os.remove(tmp_path)

    def test_must_exist_false_allows_missing(self):
        result = validate_video_path("/tmp/nonexistent_ok.mp4", must_exist=False)
        assert result.endswith("nonexistent_ok.mp4")

    def test_directory_path_raises(self):
        # /tmp fails extension check first
        with pytest.raises(ValueError, match="Invalid file extension"):
            validate_video_path("/tmp")

    def test_directory_masquerading_as_file_raises(self):
        with tempfile.TemporaryDirectory(suffix=".mp4") as tmp_dir:
            with pytest.raises(ValueError, match="not a file"):
                validate_video_path(tmp_dir)

    def test_invalid_extension_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"secret data")
            tmp_path = f.name
        try:
            with pytest.raises(ValueError, match="Invalid file extension"):
                validate_video_path(tmp_path)
        finally:
            os.remove(tmp_path)

    def test_valid_extensions(self):
        extensions = [".mp4", ".MKV", ".png", ".WAV"]
        for ext in extensions:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(b"fake media")
                tmp_path = f.name
            try:
                # Should not raise
                validate_video_path(tmp_path)
            finally:
                os.remove(tmp_path)


class TestValidateOutputPath:
    """Tests for validate_output_path."""

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_output_path("")

    def test_traversal_raises(self):
        with pytest.raises(ValueError, match="traversal"):
            validate_output_path("/tmp/../output.mp4")

    def test_valid_path_returns_resolved(self):
        result = validate_output_path("/tmp/my_output.mp4")
        assert os.path.isabs(result)
        assert result.endswith("my_output.mp4")


class TestSanitizeTextParam:
    """Tests for sanitize_text_param."""

    def test_empty_string(self):
        assert sanitize_text_param("") == ""

    def test_none_returns_none(self):
        # sanitize_text_param should handle None/falsy gracefully
        assert sanitize_text_param("") == ""

    def test_plain_text_unchanged(self):
        assert sanitize_text_param("Hello World") == "Hello World"

    def test_escapes_colon(self):
        assert sanitize_text_param("Time: 12:00") == "Time\\: 12\\:00"

    def test_escapes_semicolon(self):
        assert sanitize_text_param("a;b") == "a\\;b"

    def test_escapes_single_quote(self):
        assert sanitize_text_param("it's") == "it\\'s"

    def test_escapes_backslash(self):
        assert sanitize_text_param("a\\b") == "a\\\\b"

    def test_escapes_percent(self):
        assert sanitize_text_param("100%") == "100%%"

    def test_escapes_comma(self):
        assert sanitize_text_param("a,b") == "a\\,b"

    def test_combined_escaping(self):
        result = sanitize_text_param("Time: it's 50% done; next\\step")
        assert "\\:" in result
        assert "\\'" in result
        assert "%%" in result
        assert "\\;" in result
        assert "\\\\" in result


class TestRedactSecret:
    """Tests for redact_secret."""

    def test_empty_string(self):
        assert redact_secret("") == ""

    def test_short_key_fully_redacted(self):
        assert redact_secret("abc") == "****"

    def test_normal_key_shows_last_4(self):
        result = redact_secret("sk-1234567890abcdef")
        assert result == "****cdef"
        assert "sk-1234567890ab" not in result

    def test_custom_visible_chars(self):
        result = redact_secret("sk-1234567890abcdef", visible_chars=6)
        assert result == "****abcdef"


class TestSanitizeApiKey:
    """Tests for sanitize_api_key."""

    def test_empty_text(self):
        assert sanitize_api_key("", "key123") == ""

    def test_empty_key(self):
        assert sanitize_api_key("some text", "") == "some text"

    def test_key_removed_from_text(self):
        key = "sk-secret1234abcd"
        text = f"Error: auth failed with key {key} on request"
        result = sanitize_api_key(text, key)
        assert key not in result
        assert "****abcd" in result

    def test_multiple_occurrences_removed(self):
        key = "sk-secret1234abcd"
        text = f"Key={key} Header={key}"
        result = sanitize_api_key(text, key)
        assert key not in result
        assert result.count("****abcd") == 2

    def test_no_key_in_text_unchanged(self):
        text = "normal error message"
        assert sanitize_api_key(text, "sk-nothere") == text
