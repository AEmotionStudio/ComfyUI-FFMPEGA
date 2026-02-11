"""Qwen Code CLI connector — runs the `qwen` binary in non-interactive mode."""

import asyncio
import shutil
import logging
from typing import Optional, AsyncIterator

from .base import LLMConnector, LLMConfig, LLMResponse, LLMProvider
from .cli_utils import resolve_cli_binary

logger = logging.getLogger("ffmpega")


class QwenCodeCLIConnector(LLMConnector):
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

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Run ``qwen -p`` with prompt piped via stdin."""

        # Combine system + user prompt into a single string.
        # The Qwen CLI has no separate --system-prompt flag.
        full_prompt = ""
        if system_prompt:
            full_prompt += (
                "=== SYSTEM INSTRUCTIONS ===\n"
                f"{system_prompt}\n"
                "=== END SYSTEM INSTRUCTIONS ===\n\n"
            )
        full_prompt += prompt

        # Resolve the full path — shutil.which may fail inside a venv.
        qwen_bin = resolve_cli_binary("qwen", "qwen.cmd")
        if not qwen_bin:
            raise RuntimeError(
                "Qwen Code CLI binary not found. Install it with:\n"
                "  npm install -g @qwen-code/qwen-code@latest\n"
                "Or see: https://qwenlm.github.io/qwen-code-docs/"
            )

        # Use stdin + -p flag (no arg) to avoid OS arg-length limits.
        # The -p flag with positional prompt is deprecated; piping via
        # stdin is the preferred way for large prompts.
        cmd = [
            qwen_bin,
            "--output-format", "text",
            "-p",
        ]

        logger.debug("[QwenCLI] Running: %s -p (stdin) --output-format text", qwen_bin)

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
                f"Qwen Code CLI timed out after {self.config.timeout}s"
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Qwen Code CLI binary not found. Install it with:\n"
                "  npm install -g @qwen-code/qwen-code@latest\n"
                "Or see: https://qwenlm.github.io/qwen-code-docs/"
            )

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Qwen Code CLI failed (exit {proc.returncode}): {err}")

        content = stdout.decode("utf-8", errors="replace").strip()

        return LLMResponse(
            content=content,
            model="qwen-cli",
            provider=LLMProvider.QWEN_CLI,
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
        return ["qwen-cli"]

    async def is_available(self) -> bool:
        """Check if the qwen binary is findable."""
        return resolve_cli_binary("qwen", "qwen.cmd") is not None
