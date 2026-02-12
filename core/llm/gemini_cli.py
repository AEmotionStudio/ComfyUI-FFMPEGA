"""Gemini CLI connector — runs the `gemini` binary in headless mode."""

from typing import Optional

from .base import LLMConfig, LLMProvider
from .cli_base import CLIConnectorBase


class GeminiCLIConnector(CLIConnectorBase):
    """Connector that invokes the Gemini CLI in non-interactive (headless) mode.

    Uses ``gemini -p <prompt> -o text`` to generate responses.
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
        return [binary_path, "-p", "", "-o", "text"]

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
