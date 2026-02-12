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
import json
import logging
import re
from abc import abstractmethod
from typing import Optional, AsyncIterator

from .base import LLMConnector, LLMConfig, LLMResponse, LLMProvider
from .cli_utils import resolve_cli_binary

logger = logging.getLogger("ffmpega")

# Marker the LLM uses to request a tool call
_TOOL_CALL_MARKER = "TOOL_CALL:"


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

    # ------------------------------------------------------------------
    # Tool calling (prompt-based simulation)
    # ------------------------------------------------------------------

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        """Simulate tool calling via prompt engineering.

        Since CLI binaries only accept text in/out, we embed tool
        definitions in the prompt and parse structured markers from
        the response.

        Args:
            messages: Conversation history.
            tools: Tool definitions in OpenAI-compatible format.

        Returns:
            LLMResponse with content and/or tool_calls.
        """
        # Build the full prompt from message history
        system_prompt, user_prompt = self._build_tool_prompt(messages, tools)
        response = await self.generate(user_prompt, system_prompt)

        # Try to parse tool calls from the response
        tool_calls = self._parse_tool_calls(response.content)

        if tool_calls:
            # Strip TOOL_CALL lines from content to keep it clean
            clean_content = self._strip_tool_calls(response.content)
            return LLMResponse(
                content=clean_content,
                model=response.model,
                provider=response.provider,
                tool_calls=tool_calls,
            )

        return response

    @staticmethod
    def _build_tool_prompt(
        messages: list[dict],
        tools: list[dict],
    ) -> tuple[Optional[str], str]:
        """Convert messages + tool defs into a single system/user prompt pair.

        Returns:
            (system_prompt, user_prompt) tuple.
        """
        system_parts = []
        conversation_parts = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role == "user":
                conversation_parts.append(f"USER: {content}")
            elif role == "assistant":
                conversation_parts.append(f"ASSISTANT: {content}")
            elif role == "tool":
                conversation_parts.append(f"TOOL_RESULT: {content}")

        # Embed tool definitions in the system prompt
        if tools:
            tool_descriptions = []
            for tool in tools:
                func = tool.get("function", {})
                name = func.get("name", "")
                desc = func.get("description", "")
                params = func.get("parameters", {})
                props = params.get("properties", {})
                required = params.get("required", [])

                param_strs = []
                for pname, pinfo in props.items():
                    req_marker = " (required)" if pname in required else ""
                    ptype = pinfo.get("type", "string")
                    pdesc = pinfo.get("description", "")
                    param_strs.append(f"    - {pname} ({ptype}{req_marker}): {pdesc}")

                param_block = "\n".join(param_strs) if param_strs else "    (no parameters)"
                tool_descriptions.append(
                    f"  {name}: {desc}\n  Parameters:\n{param_block}"
                )

            tool_section = (
                "\n\n=== AVAILABLE TOOLS ===\n"
                "You have the following tools available. To call a tool, output a line "
                "in this exact format (one per line):\n"
                f'{_TOOL_CALL_MARKER} {{"name": "tool_name", "arguments": {{"key": "value"}}}}\n\n'
                "You may call multiple tools by putting each on its own line.\n"
                "When you have enough information, output the final JSON pipeline directly "
                "(without any TOOL_CALL markers).\n\n"
                "Tools:\n" + "\n\n".join(tool_descriptions) +
                "\n=== END TOOLS ===\n"
            )
            system_parts.append(tool_section)

        system_prompt = "\n\n".join(system_parts) if system_parts else None
        user_prompt = "\n\n".join(conversation_parts)

        return system_prompt, user_prompt

    @staticmethod
    def _parse_tool_calls(text: str) -> Optional[list[dict]]:
        """Parse TOOL_CALL: markers from CLI output.

        Returns:
            List of tool call dicts, or None if no tool calls found.
        """
        pattern = re.compile(
            r'TOOL_CALL:\s*(\{.*?\})\s*$',
            re.MULTILINE,
        )
        matches = pattern.findall(text)

        if not matches:
            return None

        tool_calls = []
        for i, match in enumerate(matches):
            try:
                parsed = json.loads(match)
                tool_calls.append({
                    "id": f"cli_call_{i}",
                    "function": {
                        "name": parsed.get("name", ""),
                        "arguments": parsed.get("arguments", {}),
                    }
                })
            except json.JSONDecodeError:
                logger.warning("Failed to parse tool call JSON: %s", match)
                continue

        return tool_calls if tool_calls else None

    @staticmethod
    def _strip_tool_calls(text: str) -> str:
        """Remove TOOL_CALL: lines from text, returning remaining content."""
        lines = text.split("\n")
        clean = [
            line for line in lines
            if not line.strip().startswith(_TOOL_CALL_MARKER)
        ]
        return "\n".join(clean).strip()

