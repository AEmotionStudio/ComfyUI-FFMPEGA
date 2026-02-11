"""Gemini CLI connector — runs the `gemini` binary in headless mode."""

import asyncio
import shutil
import logging
from typing import Optional, AsyncIterator

from .base import LLMConnector, LLMConfig, LLMResponse, LLMProvider
from .cli_utils import resolve_cli_binary

logger = logging.getLogger("ffmpega")


class GeminiCLIConnector(LLMConnector):
    """Connector that invokes the Gemini CLI in non-interactive (headless) mode.

    Uses ``gemini -p <prompt> -o text`` to generate responses.
    Requires the ``gemini`` binary to be installed and authenticated
    (e.g. via a Google Ultra subscription for free Gemini 3 Pro access).
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        if config is None:
            config = LLMConfig(
                provider=LLMProvider.GEMINI_CLI,
                model="gemini-cli",
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
        """Run ``gemini -p`` and capture text output."""

        # Combine system + user prompt into a single string.
        # The CLI has no separate --system-instruction flag in headless mode.
        full_prompt = ""
        if system_prompt:
            full_prompt += (
                "=== SYSTEM INSTRUCTIONS ===\n"
                f"{system_prompt}\n"
                "=== END SYSTEM INSTRUCTIONS ===\n\n"
            )
        full_prompt += prompt

        # Resolve the full path — shutil.which may fail inside a venv.
        gemini_bin = resolve_cli_binary("gemini", "gemini.cmd")
        if not gemini_bin:
            raise RuntimeError(
                "Gemini CLI binary not found. Install it with:\n"
                "  npm install -g @google/gemini-cli\n"
                "Or see: https://github.com/google-gemini/gemini-cli"
            )

        cmd = [gemini_bin, "-p", "", "-o", "text"]

        logger.debug("[GeminiCLI] Running: %s -p (stdin) -o text", gemini_bin)

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
                f"Gemini CLI timed out after {self.config.timeout}s"
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Gemini CLI binary not found. Install it with:\n"
                "  npm install -g @google/gemini-cli\n"
                "Or see: https://github.com/google-gemini/gemini-cli"
            )

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Gemini CLI failed (exit {proc.returncode}): {err}")

        content = stdout.decode("utf-8", errors="replace").strip()

        return LLMResponse(
            content=content,
            model="gemini-cli",
            provider=LLMProvider.GEMINI_CLI,
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
        return ["gemini-cli"]

    async def is_available(self) -> bool:
        """Check if the gemini binary is findable."""
        return resolve_cli_binary("gemini", "gemini.cmd") is not None
