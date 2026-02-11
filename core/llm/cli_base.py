"""Base class for CLI-based LLM connectors.

Consolidates the shared subprocess boilerplate (process creation,
timeout handling, error handling, return-code checking) so that
individual CLI connectors only need to specify:

- Binary names to search for
- How to build the command list
- How to prepare the stdin payload
- Install instructions for the error message
"""

import asyncio
import logging
from abc import abstractmethod
from typing import Optional, AsyncIterator

from .base import LLMConnector, LLMConfig, LLMResponse, LLMProvider
from .cli_utils import resolve_cli_binary

logger = logging.getLogger("ffmpega")


class CLIConnectorBase(LLMConnector):
    """Abstract base for connectors that invoke a CLI binary via subprocess.

    Subclasses must implement :meth:`_binary_names`, :meth:`_build_cmd`,
    :meth:`_prepare_stdin`, :meth:`_model_name`, :meth:`_provider`,
    and :meth:`_install_hint`.
    """

    # ------------------------------------------------------------------
    # Subclass hooks (override these)
    # ------------------------------------------------------------------

    @abstractmethod
    def _binary_names(self) -> tuple[str, ...]:
        """Return candidate binary names, e.g. ``("qwen", "qwen.cmd")``."""

    @abstractmethod
    def _build_cmd(self, binary_path: str, prompt: str,
                   system_prompt: Optional[str]) -> list[str]:
        """Build the full command list including resolved binary path."""

    @abstractmethod
    def _prepare_stdin(self, prompt: str,
                       system_prompt: Optional[str]) -> Optional[bytes]:
        """Return bytes to pipe to stdin, or ``None`` for no stdin."""

    @abstractmethod
    def _model_name(self) -> str:
        """Return the model identifier string, e.g. ``"qwen-cli"``."""

    @abstractmethod
    def _provider(self) -> LLMProvider:
        """Return the LLMProvider enum value."""

    @abstractmethod
    def _install_hint(self) -> str:
        """Return a multi-line install instruction for the error message."""

    def _log_tag(self) -> str:
        """Short tag for log messages.  Defaults to class name."""
        return self.__class__.__name__

    # ------------------------------------------------------------------
    # Shared implementation
    # ------------------------------------------------------------------

    def _resolve_binary(self) -> str:
        """Resolve the full path to the binary, or raise RuntimeError."""
        path = resolve_cli_binary(*self._binary_names())
        if not path:
            raise RuntimeError(self._install_hint())
        return path

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Run the CLI binary and capture text output."""

        binary_path = self._resolve_binary()
        cmd = self._build_cmd(binary_path, prompt, system_prompt)
        stdin_data = self._prepare_stdin(prompt, system_prompt)

        logger.debug("[%s] Running: %s", self._log_tag(), " ".join(cmd[:3]))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=self.config.timeout,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            raise TimeoutError(
                f"{self._log_tag()} timed out after {self.config.timeout}s"
            )
        except FileNotFoundError:
            raise RuntimeError(self._install_hint())

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"{self._log_tag()} failed (exit {proc.returncode}): {err}"
            )

        content = stdout.decode("utf-8", errors="replace").strip()

        return LLMResponse(
            content=content,
            model=self._model_name(),
            provider=self._provider(),
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
        return [self._model_name()]

    async def is_available(self) -> bool:
        """Check if the binary is findable."""
        return resolve_cli_binary(*self._binary_names()) is not None
