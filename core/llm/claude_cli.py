"""Claude Code CLI connector — runs the `claude` binary in non-interactive mode."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from .base import LLMConfig, LLMResponse, LLMProvider
from .cli_base import CLIConnectorBase

logger = logging.getLogger("ffmpega")


class ClaudeCodeCLIConnector(CLIConnectorBase):
    """Connector that invokes Claude Code CLI in non-interactive (print) mode.

    Uses ``claude -p --output-format json`` to generate responses with token
    stats.  Falls back to plain text if JSON parsing fails.

    Requires the ``claude`` binary to be installed and authenticated
    (e.g. via ``pnpm add -g @anthropic-ai/claude-code``).
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        if config is None:
            config = LLMConfig(
                provider=LLMProvider.CLAUDE_CLI,
                model="claude-cli",
                temperature=0.3,
            )
        super().__init__(config)

    # --- CLIConnectorBase hooks ---

    def _binary_names(self) -> tuple[str, ...]:
        return ("claude", "claude.cmd")

    def _build_cmd(self, binary_path: str, prompt: str,
                   system_prompt: Optional[str]) -> list[str]:
        cmd = [
            binary_path, "-p",
            "--output-format", "json",
            "--no-session-persistence",
        ]
        # Claude Code natively supports --system-prompt
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])
        return cmd

    def _prepare_stdin(self, prompt: str,
                       system_prompt: Optional[str]) -> Optional[bytes]:
        # System prompt is handled via --system-prompt flag, so only
        # the user prompt is piped via stdin.
        return prompt.encode("utf-8")

    def _model_name(self) -> str:
        return "claude-cli"

    def _provider(self) -> LLMProvider:
        return LLMProvider.CLAUDE_CLI

    def _install_hint(self) -> str:
        return (
            "Claude Code CLI binary not found. Install it with:\n"
            "  pnpm add -g @anthropic-ai/claude-code\n"
            "Or see: https://docs.anthropic.com/en/docs/claude-code"
        )

    def _log_tag(self) -> str:
        return "ClaudeCLI"

    def _parse_json_output(self, raw_output: str) -> Optional[LLMResponse]:
        """Parse Claude CLI JSON output, extracting content and token stats.

        Claude CLI JSON output typically contains:
        - result: the text response
        - session_id: session identifier
        - usage/cost_usd: token usage and cost info

        Returns None if JSON parsing fails (base class falls back to
        char-based estimation).
        """
        _first = self._first_not_none

        prompt_tokens: Optional[int] = None
        completion_tokens: Optional[int] = None
        total_tokens: Optional[int] = None
        content = raw_output  # fallback

        try:
            data = json.loads(raw_output)

            if isinstance(data, dict):
                # Extract text content
                content = (
                    data.get("result", "")
                    or data.get("response", "")
                    or data.get("content", "")
                    or data.get("text", "")
                    or raw_output
                )

                # Extract token usage from various possible locations
                usage = (
                    data.get("usage")
                    or data.get("stats")
                    or data.get("token_usage")
                    or {}
                )

                if isinstance(usage, dict):
                    prompt_tokens = _first(
                        usage.get("input_tokens"),
                        usage.get("prompt_tokens"),
                    )
                    completion_tokens = _first(
                        usage.get("output_tokens"),
                        usage.get("completion_tokens"),
                    )

                # Also check top-level fields
                if prompt_tokens is None:
                    prompt_tokens = data.get("input_tokens")
                if completion_tokens is None:
                    completion_tokens = data.get("output_tokens")

                if prompt_tokens is not None or completion_tokens is not None:
                    total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

                logger.debug(
                    "[ClaudeCLI] Token stats: prompt=%s completion=%s total=%s",
                    prompt_tokens, completion_tokens, total_tokens,
                )

            elif isinstance(data, list):
                # Some CLI versions may return an array of response objects
                text_parts = []
                for item in data:
                    if isinstance(item, dict):
                        text_parts.append(
                            item.get("result", "")
                            or item.get("content", "")
                            or item.get("text", "")
                        )
                content = "\n".join(p for p in text_parts if p) or raw_output
                # Extract usage from the last item (most complete)
                if data and isinstance(data[-1], dict):
                    usage = (
                        data[-1].get("usage")
                        or data[-1].get("stats")
                        or data[-1].get("token_usage")
                    )
                    if isinstance(usage, dict):
                        prompt_tokens = _first(
                            usage.get("input_tokens"),
                            usage.get("prompt_tokens"),
                        )
                        completion_tokens = _first(
                            usage.get("output_tokens"),
                            usage.get("completion_tokens"),
                        )
                    if prompt_tokens is not None or completion_tokens is not None:
                        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

        except (json.JSONDecodeError, ValueError, TypeError):
            # Not valid JSON — signal base class to use char-based fallback
            logger.debug("[ClaudeCLI] JSON parse failed, treating as plain text")
            return None

        return LLMResponse(
            content=content,
            model=self._model_name(),
            provider=self._provider(),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
