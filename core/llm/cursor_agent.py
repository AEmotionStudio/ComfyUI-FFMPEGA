"""Cursor Agent CLI connector — runs the `agent` binary in non-interactive mode."""

import asyncio
import shutil
import logging
from typing import Optional, AsyncIterator

from .base import LLMConnector, LLMConfig, LLMResponse, LLMProvider
from .cli_utils import resolve_cli_binary

logger = logging.getLogger("ffmpega")


class CursorAgentConnector(LLMConnector):
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

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Run ``agent -p`` and capture text output."""

        # Combine system + user prompt into a single string.
        # The Cursor CLI has no separate --system-prompt flag.
        full_prompt = ""
        if system_prompt:
            full_prompt += (
                "=== SYSTEM INSTRUCTIONS ===\n"
                f"{system_prompt}\n"
                "=== END SYSTEM INSTRUCTIONS ===\n\n"
            )
        full_prompt += prompt

        # Resolve the full path — shutil.which may fail inside a venv.
        agent_bin = resolve_cli_binary("agent", "agent.cmd")
        if not agent_bin:
            raise RuntimeError(
                "Cursor Agent CLI binary ('agent') not found. Install it from:\n"
                "  Cursor IDE → Command Palette → 'Install cursor command'\n"
                "Or see: https://docs.cursor.com/cli"
            )

        cmd = [agent_bin, "-p"]

        logger.debug("[CursorAgent] Running: %s -p (stdin)", agent_bin)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=full_prompt.encode("utf-8")),
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
                f"Cursor Agent CLI timed out after {self.config.timeout}s"
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Cursor Agent CLI binary ('agent') not found. Install it from:\n"
                "  Cursor IDE → Command Palette → 'Install cursor command'\n"
                "Or see: https://docs.cursor.com/cli"
            )

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Cursor Agent CLI failed (exit {proc.returncode}): {err}")

        content = stdout.decode("utf-8", errors="replace").strip()

        return LLMResponse(
            content=content,
            model="cursor-agent",
            provider=LLMProvider.CURSOR_AGENT,
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
        return ["cursor-agent"]

    async def is_available(self) -> bool:
        """Check if the agent binary is on PATH."""
        return (
            shutil.which("agent") is not None
            or shutil.which("agent.cmd") is not None  # Windows shim
        )
