"""Tests for CLI connector retry logic and error message extraction.

Tests the _is_retryable_error and _extract_clean_error static methods
on CLIConnectorBase, plus the retry-loop behaviour in generate().
"""

import pytest

from core.llm.cli_base import CLIConnectorBase


# ── _is_retryable_error ──────────────────────────────────────────────


class TestIsRetryableError:
    """Tests for CLIConnectorBase._is_retryable_error."""

    def test_http_429_detected(self):
        """stderr containing '429' should be retryable."""
        stderr = "status: 429, statusText: 'Too Many Requests'"
        assert CLIConnectorBase._is_retryable_error(stderr) is True

    def test_resource_exhausted_detected(self):
        """stderr containing RESOURCE_EXHAUSTED should be retryable."""
        stderr = '"status": "RESOURCE_EXHAUSTED"'
        assert CLIConnectorBase._is_retryable_error(stderr) is True

    def test_capacity_exhausted_detected(self):
        """stderr containing MODEL_CAPACITY_EXHAUSTED should be retryable."""
        stderr = '"reason": "MODEL_CAPACITY_EXHAUSTED"'
        assert CLIConnectorBase._is_retryable_error(stderr) is True

    def test_rate_limit_exceeded_detected(self):
        """stderr containing rateLimitExceeded should be retryable."""
        stderr = '"reason": "rateLimitExceeded"'
        assert CLIConnectorBase._is_retryable_error(stderr) is True

    def test_no_capacity_detected(self):
        """stderr containing 'No capacity available' should be retryable."""
        stderr = "No capacity available for model gemini-3-flash-preview"
        assert CLIConnectorBase._is_retryable_error(stderr) is True

    def test_quota_detected(self):
        """stderr containing 'quota' should be retryable."""
        stderr = "RetryableQuotaError: quota exceeded"
        assert CLIConnectorBase._is_retryable_error(stderr) is True

    def test_generic_error_not_retryable(self):
        """Random error messages should NOT be retryable."""
        stderr = "SyntaxError: Unexpected token in JSON"
        assert CLIConnectorBase._is_retryable_error(stderr) is False

    def test_file_not_found_not_retryable(self):
        """File-not-found stderr should NOT be retryable."""
        stderr = "Error: Cannot find module 'gemini'"
        assert CLIConnectorBase._is_retryable_error(stderr) is False

    def test_empty_string_not_retryable(self):
        """Empty stderr should NOT be retryable."""
        assert CLIConnectorBase._is_retryable_error("") is False

    def test_case_insensitive(self):
        """Detection should be case-insensitive."""
        assert CLIConnectorBase._is_retryable_error("RATE LIMIT hit") is True
        assert CLIConnectorBase._is_retryable_error("Quota exceeded") is True


# ── _extract_clean_error ─────────────────────────────────────────────


class TestExtractCleanError:
    """Tests for CLIConnectorBase._extract_clean_error."""

    def test_extracts_json_message(self):
        """Should extract the 'message' field from JSON error in stderr."""
        stderr = (
            '{"error": {"code": 429, '
            '"message": "No capacity available for model gemini-3-flash-preview on the server"}}'
        )
        result = CLIConnectorBase._extract_clean_error(stderr)
        assert result == "No capacity available for model gemini-3-flash-preview on the server"

    def test_extracts_from_multiline_json(self):
        """Should extract message from multiline JSON-like stderr."""
        stderr = (
            'Some preamble\n'
            '  "message": "Model overloaded, try again later",\n'
            '  "code": 429\n'
            'at SomeStack.trace (file:///foo/bar.js:123:45)'
        )
        result = CLIConnectorBase._extract_clean_error(stderr)
        assert result == "Model overloaded, try again later"

    def test_extracts_error_line_without_json(self):
        """Should find an error-keyword line when no JSON message exists."""
        stderr = (
            "(node:12345) [DEP0040] DeprecationWarning: punycode module\n"
            "at Object.<anonymous> (node:internal/something:1:1)\n"
            "Error: Connection refused to API endpoint\n"
            "at processTicksAndRejections (node:internal/process/task_queues:104:5)"
        )
        result = CLIConnectorBase._extract_clean_error(stderr)
        assert "Connection refused" in result

    def test_skips_deprecation_warnings(self):
        """Should skip DeprecationWarning lines."""
        stderr = (
            "(node:12345) [DEP0040] DeprecationWarning: the punycode module\n"
            "Fatal error: out of memory"
        )
        result = CLIConnectorBase._extract_clean_error(stderr)
        assert "DeprecationWarning" not in result
        assert "error" in result.lower()

    def test_skips_stack_frames(self):
        """Should skip 'at ...' stack trace lines."""
        stderr = (
            "at Gaxios._request (file:///cli/bundle.js:79556:19)\n"
            "Failed with status 429\n"
        )
        result = CLIConnectorBase._extract_clean_error(stderr)
        assert "at Gaxios" not in result
        assert "429" in result

    def test_fallback_to_truncated_stderr(self):
        """Should fall back to first 200 chars when no clean message found."""
        stderr = "x" * 500
        result = CLIConnectorBase._extract_clean_error(stderr)
        assert len(result) == 200

    def test_empty_stderr(self):
        """Should handle empty stderr gracefully."""
        result = CLIConnectorBase._extract_clean_error("")
        assert result == ""

    def test_real_gemini_error_message(self):
        """Should extract clean message from real Gemini CLI error output."""
        # Simplified version of the actual error from Errors.md
        stderr = (
            '(node:53516) [DEP0040] DeprecationWarning: The `punycode` module is deprecated.\n'
            'Attempt 1 failed with status 429. Retrying with backoff...\n'
            '_GaxiosError: [{\n'
            '  "error": {\n'
            '    "code": 429,\n'
            '    "message": "No capacity available for model gemini-3-flash-preview on the server",\n'
            '    "status": "RESOURCE_EXHAUSTED"\n'
            '  }\n'
            '}]\n'
            '    at Gaxios._request (file:///usr/lib/gemini-cli/bundle.js:79556:19)\n'
        )
        result = CLIConnectorBase._extract_clean_error(stderr)
        assert result == "No capacity available for model gemini-3-flash-preview on the server"


# ── Retry constants ──────────────────────────────────────────────────

class TestRetryConstants:
    """Verify retry configuration values."""

    def test_max_retries(self):
        assert CLIConnectorBase._MAX_RETRIES == 3

    def test_initial_backoff(self):
        assert CLIConnectorBase._INITIAL_BACKOFF == 5.0

    def test_backoff_multiplier(self):
        assert CLIConnectorBase._BACKOFF_MULTIPLIER == 3.0

    def test_backoff_jitter(self):
        assert CLIConnectorBase._BACKOFF_JITTER == 0.25
