"""Gemini CLI connector — runs the `gemini` binary in headless mode."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from .base import LLMConfig, LLMResponse, LLMProvider
from .cli_base import CLIConnectorBase

logger = logging.getLogger("ffmpega")


class GeminiCLIConnector(CLIConnectorBase):
    """Connector that invokes the Gemini CLI in non-interactive (headless) mode.

    Uses ``gemini -p <prompt> -o json`` to generate responses with token
    stats.  Falls back to ``-o text`` and char-based estimation if JSON
    parsing fails.

    Requires the ``gemini`` binary to be installed and authenticated
    with any Google account (free tier: 1,000 requests/day).
    Pro/Ultra subscribers receive higher rate limits.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        if config is None:
            config = LLMConfig(
                provider=LLMProvider.GEMINI_CLI,
                model="gemini-cli",
                temperature=0.3,
            )
        super().__init__(config)

    # --- CLIConnectorBase hooks ---

    def _binary_names(self) -> tuple[str, ...]:
        return ("gemini", "gemini.cmd")

    def _build_cmd(self, binary_path: str, prompt: str,
                   system_prompt: Optional[str]) -> list[str]:
        return [binary_path, "-p", "", "-o", "json"]

    def _prepare_stdin(self, prompt: str,
                       system_prompt: Optional[str]) -> Optional[bytes]:
        full_prompt = ""
        if system_prompt:
            full_prompt += (
                "=== SYSTEM INSTRUCTIONS ===\n"
                f"{system_prompt}\n"
                "=== END SYSTEM INSTRUCTIONS ===\n\n"
            )
        full_prompt += prompt
        return full_prompt.encode("utf-8")

    def _model_name(self) -> str:
        return "gemini-cli"

    def _provider(self) -> LLMProvider:
        return LLMProvider.GEMINI_CLI

    def _install_hint(self) -> str:
        return (
            "Gemini CLI binary not found. Install it with:\n"
            "  pnpm add -g @google/gemini-cli\n"
            "Or see: https://github.com/google-gemini/gemini-cli"
        )

    def _log_tag(self) -> str:
        return "GeminiCLI"

    # --- Override _parse_raw_output to extract JSON token stats ---

    def _parse_raw_output(
        self,
        raw_output: str,
        stdin_data: Optional[bytes] = None,
    ) -> LLMResponse:
        """Parse Gemini CLI JSON output for content and native token stats."""
        return self._parse_json_output(raw_output)

    def _parse_json_output(self, raw_output: str) -> LLMResponse:
        """Parse Gemini CLI JSON output, extracting content and token stats.

        The JSON output may contain a list of response objects. Each object
        can have a 'response' field with the text content, and a 'stats'
        or 'usage' field with token counts.

        Falls back to treating output as plain text if JSON parsing fails.
        """
        def _first(a: Optional[int], b: Optional[int]) -> Optional[int]:
            """Return first non-None value (0 is valid)."""
            return a if a is not None else b

        prompt_tokens: Optional[int] = None
        completion_tokens: Optional[int] = None
        total_tokens: Optional[int] = None
        content = raw_output  # fallback

        try:
            data = json.loads(raw_output)

            # Handle various JSON structures Gemini CLI may return
            if isinstance(data, list):
                # Array of response objects
                text_parts = []
                for item in data:
                    if isinstance(item, dict):
                        text_parts.append(self._extract_text(item))
                content = "\n".join(p for p in text_parts if p) or raw_output
                # Extract usage from the last item (most complete)
                if data and isinstance(data[-1], dict):
                    usage = self._find_usage_dict(data[-1])
                    if usage:
                        prompt_tokens = _first(usage.get("input_tokens"), usage.get("prompt_tokens"))
                        completion_tokens = _first(usage.get("output_tokens"), usage.get("completion_tokens"))
            elif isinstance(data, dict):
                content = self._extract_text(data) or raw_output
                usage = self._find_usage_dict(data)
                if usage:
                    prompt_tokens = _first(usage.get("input_tokens"), usage.get("prompt_tokens"))
                    completion_tokens = _first(usage.get("output_tokens"), usage.get("completion_tokens"))

            if prompt_tokens is not None or completion_tokens is not None:
                total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

            logger.debug(
                "[GeminiCLI] Token stats: prompt=%s completion=%s total=%s",
                prompt_tokens, completion_tokens, total_tokens,
            )

        except (json.JSONDecodeError, ValueError, TypeError):
            # Not valid JSON — treat as plain text (fallback to text mode)
            logger.debug("[GeminiCLI] JSON parse failed, treating as plain text")

        return LLMResponse(
            content=content,
            model=self._model_name(),
            provider=self._provider(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _extract_text(obj: dict) -> str:
        """Extract text content from a Gemini CLI JSON response object."""
        # Try common fields where response text might be
        for key in ("response", "text", "content", "message", "result"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                # Nested content
                inner = val.get("text") or val.get("content", "")
                if isinstance(inner, str) and inner.strip():
                    return inner.strip()
        return ""

    @staticmethod
    def _find_usage_dict(obj: dict) -> Optional[dict]:
        """Find token usage dictionary within a response object."""
        # Check common locations for usage data
        for key in ("stats", "usage", "usageMetadata", "usage_metadata",
                     "tokenUsage", "token_usage"):
            val = obj.get(key)
            if isinstance(val, dict):
                return val
        # Check nested under 'metadata'
        metadata = obj.get("metadata")
        if isinstance(metadata, dict):
            for key in ("usage", "stats", "tokenUsage"):
                val = metadata.get(key)
                if isinstance(val, dict):
                    return val
        return None

