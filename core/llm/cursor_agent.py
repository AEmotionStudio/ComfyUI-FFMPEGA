"""Cursor Agent CLI connector — runs the `agent` binary in non-interactive mode."""

from typing import Optional

from .base import LLMConfig, LLMProvider
from .cli_base import CLIConnectorBase


class CursorAgentConnector(CLIConnectorBase):
    """Connector that invokes Cursor's CLI in non-interactive agent mode.

    Uses ``agent -p <prompt>`` (piped via stdin) to generate responses.
    The binary is named ``agent`` and is installed via:
    Cursor IDE → Command Palette → "Install 'cursor' command".
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        if config is None:
            config = LLMConfig(
                provider=LLMProvider.CURSOR_AGENT,
                model="cursor-agent",
                temperature=0.3,
            )
        super().__init__(config)

    # --- CLIConnectorBase hooks ---

    def _binary_names(self) -> tuple[str, ...]:
        return ("agent", "agent.cmd")

    def _build_cmd(self, binary_path: str, prompt: str,
                   system_prompt: Optional[str]) -> list[str]:
        return [binary_path, "--trust", "-p"]

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
        return "cursor-agent"

    def _provider(self) -> LLMProvider:
        return LLMProvider.CURSOR_AGENT

    def _install_hint(self) -> str:
        return (
            "Cursor Agent CLI binary ('agent') not found. Install it from:\n"
            "  Cursor IDE → Command Palette → 'Install cursor command'\n"
            "Or see: https://docs.cursor.com/cli"
        )

    def _log_tag(self) -> str:
        return "CursorAgent"
