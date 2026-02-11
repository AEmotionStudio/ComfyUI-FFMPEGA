"""Claude Code CLI connector — runs the `claude` binary in non-interactive mode."""

import asyncio
import shutil
import logging
from typing import Optional, AsyncIterator

from .base import LLMConnector, LLMConfig, LLMResponse, LLMProvider

logger = logging.getLogger("ffmpega")


class ClaudeCodeCLIConnector(LLMConnector):
    """Connector that invokes Claude Code CLI in non-interactive (print) mode.

    Uses ``claude -p <prompt> --output-format text`` to generate responses.
    Requires the ``claude`` binary to be installed and authenticated
    (e.g. via ``npm install -g @anthropic-ai/claude-code``).
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        if config is None:
            config = LLMConfig(
                provider=LLMProvider.CLAUDE_CLI,
                model="claude-cli",
                temperature=0.3,
            )
        super().__init__(config)

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Run ``claude -p`` and capture text output."""

        cmd = [
            "claude", "-p",
            "--output-format", "text",
            "--no-session-persistence",
        ]

        # Claude Code natively supports --system-prompt
        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        logger.debug("[ClaudeCLI] Running: claude -p (stdin) --output-format text")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=self.config.timeout,
            )
        except asyncio.TimeoutError:
            # Kill the subprocess to prevent resource leak
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            raise TimeoutError(
                f"Claude Code CLI timed out after {self.config.timeout}s"
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Claude Code CLI binary not found. Install it with:\n"
                "  npm install -g @anthropic-ai/claude-code\n"
                "Or see: https://docs.anthropic.com/en/docs/claude-code"
            )

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Claude Code CLI failed (exit {proc.returncode}): {err}")

        content = stdout.decode("utf-8", errors="replace").strip()

        return LLMResponse(
            content=content,
            model="claude-cli",
            provider=LLMProvider.CLAUDE_CLI,
        )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Streaming not supported — falls back to single generate call."""
        response = await self.generate(prompt, system_prompt)
        yield response.content

    async def list_models(self) -> list[str]:
        """Return the single CLI model identifier."""
        return ["claude-cli"]

    async def is_available(self) -> bool:
        """Check if the claude binary is on PATH."""
        return (
            shutil.which("claude") is not None
            or shutil.which("claude.cmd") is not None  # Windows npm shim
        )
