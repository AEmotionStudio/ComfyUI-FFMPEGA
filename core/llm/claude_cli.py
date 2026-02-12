"""Claude Code CLI connector — runs the `claude` binary in non-interactive mode."""

from typing import Optional

from .base import LLMConfig, LLMProvider
from .cli_base import CLIConnectorBase


class ClaudeCodeCLIConnector(CLIConnectorBase):
    """Connector that invokes Claude Code CLI in non-interactive (print) mode.

    Uses ``claude -p <prompt> --output-format text`` to generate responses.
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
            "--output-format", "text",
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
