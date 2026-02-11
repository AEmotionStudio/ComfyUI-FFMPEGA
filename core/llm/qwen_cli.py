"""Qwen Code CLI connector — runs the `qwen` binary in non-interactive mode."""

from typing import Optional

from .base import LLMConfig, LLMProvider
from .cli_base import CLIConnectorBase


class QwenCodeCLIConnector(CLIConnectorBase):
    """Connector that invokes Qwen Code CLI in non-interactive (print) mode.

    Uses ``qwen -p --output-format text`` with prompt piped via stdin.
    Requires the ``qwen`` binary to be installed and authenticated
    (e.g. via ``pnpm install -g @qwen-code/qwen-code@latest``).

    Free tier: 2,000 requests/day via Qwen OAuth (no credit card required).
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        if config is None:
            config = LLMConfig(
                provider=LLMProvider.QWEN_CLI,
                model="qwen-cli",
                temperature=0.3,
            )
        super().__init__(config)

    # --- CLIConnectorBase hooks ---

    def _binary_names(self) -> tuple[str, ...]:
        return ("qwen", "qwen.cmd")

    def _build_cmd(self, binary_path: str, prompt: str,
                   system_prompt: Optional[str]) -> list[str]:
        return [binary_path, "--output-format", "text", "-p"]

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
        return "qwen-cli"

    def _provider(self) -> LLMProvider:
        return LLMProvider.QWEN_CLI

    def _install_hint(self) -> str:
        return (
            "Qwen Code CLI binary not found. Install it with:\n"
            "  npm install -g @qwen-code/qwen-code@latest\n"
            "Or see: https://qwenlm.github.io/qwen-code-docs/"
        )

    def _log_tag(self) -> str:
        return "QwenCLI"
