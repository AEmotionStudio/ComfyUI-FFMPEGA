"""Comprehensive tests for all LLM agent connectors.

Tests cover:
- LLMConfig/LLMResponse data classes
- CLIConnectorBase (parse/strip/build prompt/generate/chat_with_tools)
- CLI subclass hooks (Gemini, Claude, Cursor, Qwen)
- APIConnector (OpenAI + Anthropic tool calling, API key sanitization)
- OllamaConnector config defaults
- cli_utils binary resolution
- PipelineGenerator agentic loop integration
"""

import asyncio
import json
import logging
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from core.llm.base import LLMConfig, LLMProvider, LLMResponse, LLMConnector
from core.llm.cli_base import CLIConnectorBase, _TOOL_CALL_MARKER
import core.llm.cli_base as _cli_base_mod
import core.llm.cli_utils as _cli_utils_mod
from core.llm.cli_utils import resolve_cli_binary
from core.llm.gemini_cli import GeminiCLIConnector
from core.llm.claude_cli import ClaudeCodeCLIConnector
from core.llm.cursor_agent import CursorAgentConnector
from core.llm.qwen_cli import QwenCodeCLIConnector
from core.llm.ollama import OllamaConnector
from core.llm.api import APIConnector, create_openai_connector, create_anthropic_connector


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data classes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestLLMConfig:
    """Tests for LLMConfig data class."""

    def test_defaults(self):
        """Default LLMConfig should use Ollama with sensible defaults."""
        cfg = LLMConfig()
        assert cfg.provider == LLMProvider.OLLAMA
        assert cfg.model == "llama3.1:8b"
        assert cfg.temperature == 0.3
        assert cfg.max_tokens == 4096
        assert cfg.timeout == 300.0
        assert cfg.api_key is None
        assert cfg.extra_options == {}

    def test_custom_config(self):
        """Custom values should be stored correctly."""
        cfg = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o",
            api_key="sk-test1234567890",
            temperature=0.7,
        )
        assert cfg.provider == LLMProvider.OPENAI
        assert cfg.model == "gpt-4o"
        assert cfg.api_key == "sk-test1234567890"
        assert cfg.temperature == 0.7

    def test_repr_redacts_api_key(self):
        """API key should be partially redacted in repr."""
        cfg = LLMConfig(api_key="sk-abcdefghijklmnop")
        r = repr(cfg)
        assert "sk-abcdefghijklmnop" not in r
        assert "mnop" in r  # Last 4 chars visible
        assert "****" in r

    def test_repr_short_key_fully_redacted(self):
        """Short keys (≤4 chars) should be fully redacted."""
        cfg = LLMConfig(api_key="abcd")
        r = repr(cfg)
        assert "abcd" not in r
        assert "****" in r

    def test_repr_no_key(self):
        """No API key should show empty string in repr."""
        cfg = LLMConfig()
        r = repr(cfg)
        assert "api_key=''" in r


class TestLLMResponse:
    """Tests for LLMResponse data class."""

    def test_basic_response(self):
        """Response should store all provided fields."""
        resp = LLMResponse(
            content="Hello world",
            model="gpt-4o",
            provider=LLMProvider.OPENAI,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            finish_reason="stop",
        )
        assert resp.content == "Hello world"
        assert resp.model == "gpt-4o"
        assert resp.provider == LLMProvider.OPENAI
        assert resp.total_tokens == 15

    def test_optional_fields_default_none(self):
        """Optional fields should default to None."""
        resp = LLMResponse(content="test", model="m", provider=LLMProvider.OLLAMA)
        assert resp.prompt_tokens is None
        assert resp.completion_tokens is None
        assert resp.tool_calls is None
        assert resp.raw_response is None

    def test_tool_calls_stored(self):
        """Tool calls should be stored when provided."""
        calls = [{"id": "1", "function": {"name": "search_skills", "arguments": {}}}]
        resp = LLMResponse(
            content="",
            model="m",
            provider=LLMProvider.GEMINI_CLI,
            tool_calls=calls,
        )
        assert resp.tool_calls == calls


class TestLLMProvider:
    """Tests for LLMProvider enum."""

    def test_all_providers_exist(self):
        """All expected providers should be defined."""
        expected = {
            "ollama", "openai", "anthropic", "gemini", "qwen",
            "gemini_cli", "claude_cli", "cursor_agent", "qwen_cli",
            "custom",
        }
        actual = {p.value for p in LLMProvider}
        assert expected == actual

    def test_provider_is_string(self):
        """Provider values should be usable as strings."""
        assert LLMProvider.OPENAI.value == "openai"
        assert LLMProvider.OLLAMA == "ollama"
        assert LLMProvider.GEMINI_CLI.value == "gemini_cli"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLIConnectorBase — shared logic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestParseToolCalls:
    """Tests for CLIConnectorBase._parse_tool_calls."""

    def test_single_tool_call(self):
        """Single TOOL_CALL: line should be parsed."""
        text = 'TOOL_CALL: {"name": "search_skills", "arguments": {"query": "blur"}}'
        result = CLIConnectorBase._parse_tool_calls(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["function"]["name"] == "search_skills"
        assert result[0]["function"]["arguments"] == {"query": "blur"}
        assert result[0]["id"] == "cli_call_0"

    def test_multiple_tool_calls(self):
        """Multiple TOOL_CALL: lines should all be parsed."""
        text = (
            'Thinking about it...\n'
            'TOOL_CALL: {"name": "search_skills", "arguments": {"query": "blur"}}\n'
            'TOOL_CALL: {"name": "get_skill_details", "arguments": {"skill_name": "blur"}}'
        )
        result = CLIConnectorBase._parse_tool_calls(text)
        assert result is not None
        assert len(result) == 2
        assert result[0]["function"]["name"] == "search_skills"
        assert result[1]["function"]["name"] == "get_skill_details"
        assert result[0]["id"] == "cli_call_0"
        assert result[1]["id"] == "cli_call_1"

    def test_no_tool_calls(self):
        """Text without TOOL_CALL markers should return None."""
        text = '{"pipeline": [{"skill": "blur", "params": {}}]}'
        assert CLIConnectorBase._parse_tool_calls(text) is None

    def test_malformed_json(self):
        """Malformed JSON after TOOL_CALL: should be skipped."""
        text = 'TOOL_CALL: {invalid json here}'
        result = CLIConnectorBase._parse_tool_calls(text)
        assert result is None

    def test_mixed_valid_and_invalid(self):
        """Valid tool calls should be kept, invalid ones skipped."""
        text = (
            'TOOL_CALL: {invalid}\n'
            'TOOL_CALL: {"name": "analyze_video", "arguments": {}}'
        )
        result = CLIConnectorBase._parse_tool_calls(text)
        assert result is not None
        assert len(result) == 1
        assert result[0]["function"]["name"] == "analyze_video"

    def test_tool_call_with_extra_whitespace(self):
        """TOOL_CALL with extra whitespace before JSON should parse."""
        text = 'TOOL_CALL:   {"name": "list_skills", "arguments": {"category": "visual"}}'
        result = CLIConnectorBase._parse_tool_calls(text)
        assert result is not None
        assert result[0]["function"]["name"] == "list_skills"


class TestStripToolCalls:
    """Tests for CLIConnectorBase._strip_tool_calls."""

    def test_removes_tool_call_lines(self):
        """TOOL_CALL lines should be removed, other content preserved."""
        text = (
            'I will search for relevant skills.\n'
            'TOOL_CALL: {"name": "search_skills", "arguments": {"query": "blur"}}\n'
            'Let me get more details.'
        )
        result = CLIConnectorBase._strip_tool_calls(text)
        assert "TOOL_CALL" not in result
        assert "I will search for relevant skills." in result
        assert "Let me get more details." in result

    def test_all_tool_calls_stripped(self):
        """When text is all TOOL_CALL lines, result should be empty."""
        text = 'TOOL_CALL: {"name": "a", "arguments": {}}\nTOOL_CALL: {"name": "b", "arguments": {}}'
        result = CLIConnectorBase._strip_tool_calls(text)
        assert result == ""

    def test_no_tool_calls_unchanged(self):
        """Text without TOOL_CALL lines should remain unchanged."""
        text = "Just some regular output here."
        assert CLIConnectorBase._strip_tool_calls(text) == text


class TestBuildToolPrompt:
    """Tests for CLIConnectorBase._build_tool_prompt."""

    def test_system_and_user_messages(self):
        """System messages go to system prompt, user messages to user prompt."""
        messages = [
            {"role": "system", "content": "You are a helper."},
            {"role": "user", "content": "Make it blurry"},
        ]
        system, user = CLIConnectorBase._build_tool_prompt(messages, [])
        assert "You are a helper." in system
        assert "USER: Make it blurry" in user

    def test_tool_definitions_embedded(self):
        """Tool definitions should appear in system prompt."""
        tools = [{
            "type": "function",
            "function": {
                "name": "search_skills",
                "description": "Search for skills",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search term"}
                    },
                    "required": ["query"],
                },
            },
        }]
        system, _ = CLIConnectorBase._build_tool_prompt(
            [{"role": "user", "content": "test"}], tools
        )
        assert "AVAILABLE TOOLS" in system
        assert "search_skills" in system
        assert "Search for skills" in system
        assert "(required)" in system
        assert "TOOL_CALL:" in system

    def test_tool_result_message(self):
        """Tool result messages should be formatted as TOOL_RESULT."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "tool", "content": '{"result": "ok"}'},
        ]
        _, user = CLIConnectorBase._build_tool_prompt(messages, [])
        assert "TOOL_RESULT:" in user

    def test_assistant_message(self):
        """Assistant messages should be formatted with ASSISTANT prefix."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        _, user = CLIConnectorBase._build_tool_prompt(messages, [])
        assert "ASSISTANT: Hello!" in user

    def test_no_system_messages(self):
        """When there are no system messages and no tools, system prompt should be None."""
        messages = [{"role": "user", "content": "Hi"}]
        system, _ = CLIConnectorBase._build_tool_prompt(messages, [])
        assert system is None

    def test_empty_tools_no_tool_section(self):
        """Empty tools list should not add AVAILABLE TOOLS section."""
        messages = [
            {"role": "system", "content": "You are a helper."},
            {"role": "user", "content": "Hi"},
        ]
        system, _ = CLIConnectorBase._build_tool_prompt(messages, [])
        assert "AVAILABLE TOOLS" not in system


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI connector subclass hooks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestGeminiCLIConnector:
    """Tests for GeminiCLIConnector hook methods."""

    def test_default_config(self):
        """Default config should have Gemini CLI provider."""
        c = GeminiCLIConnector()
        assert c.config.provider == LLMProvider.GEMINI_CLI
        assert c.config.model == "gemini-cli"

    def test_binary_names(self):
        """Should search for gemini and gemini.cmd."""
        c = GeminiCLIConnector()
        names = c._binary_names()
        assert "gemini" in names
        assert "gemini.cmd" in names

    def test_build_cmd(self):
        """Command should include -p and -o json flags."""
        c = GeminiCLIConnector()
        cmd = c._build_cmd("/usr/bin/gemini", "test prompt", None)
        assert cmd[0] == "/usr/bin/gemini"
        assert "-p" in cmd
        assert "-o" in cmd
        assert "json" in cmd

    def test_prepare_stdin_with_system(self):
        """Stdin should include system instructions wrapper."""
        c = GeminiCLIConnector()
        data = c._prepare_stdin("make it fast", "you are helpful")
        text = data.decode("utf-8")
        assert "SYSTEM INSTRUCTIONS" in text
        assert "you are helpful" in text
        assert "make it fast" in text

    def test_prepare_stdin_without_system(self):
        """Without system prompt, stdin should be just the user prompt."""
        c = GeminiCLIConnector()
        data = c._prepare_stdin("make it fast", None)
        text = data.decode("utf-8")
        assert text == "make it fast"
        assert "SYSTEM" not in text

    def test_model_name(self):
        c = GeminiCLIConnector()
        assert c._model_name() == "gemini-cli"

    def test_provider(self):
        c = GeminiCLIConnector()
        assert c._provider() == LLMProvider.GEMINI_CLI

    def test_install_hint(self):
        c = GeminiCLIConnector()
        hint = c._install_hint()
        assert "gemini-cli" in hint.lower() or "gemini" in hint.lower()
        assert "pnpm" in hint or "npm" in hint

    def test_log_tag(self):
        c = GeminiCLIConnector()
        assert c._log_tag() == "GeminiCLI"


class TestClaudeCodeCLIConnector:
    """Tests for ClaudeCodeCLIConnector hook methods."""

    def test_default_config(self):
        c = ClaudeCodeCLIConnector()
        assert c.config.provider == LLMProvider.CLAUDE_CLI
        assert c.config.model == "claude-cli"

    def test_binary_names(self):
        c = ClaudeCodeCLIConnector()
        names = c._binary_names()
        assert "claude" in names
        assert "claude.cmd" in names

    def test_build_cmd_with_system_prompt(self):
        """Claude should use --system-prompt flag."""
        c = ClaudeCodeCLIConnector()
        cmd = c._build_cmd("/usr/bin/claude", "test", "be helpful")
        assert "--system-prompt" in cmd
        assert "be helpful" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--no-session-persistence" in cmd

    def test_build_cmd_without_system_prompt(self):
        """Without system prompt, --system-prompt flag should be absent."""
        c = ClaudeCodeCLIConnector()
        cmd = c._build_cmd("/usr/bin/claude", "test", None)
        assert "--system-prompt" not in cmd

    def test_prepare_stdin(self):
        """Claude pipes only user prompt via stdin (system via flag)."""
        c = ClaudeCodeCLIConnector()
        data = c._prepare_stdin("make it blurry", "be helpful")
        text = data.decode("utf-8")
        assert text == "make it blurry"
        assert "SYSTEM" not in text

    def test_model_name(self):
        c = ClaudeCodeCLIConnector()
        assert c._model_name() == "claude-cli"

    def test_provider(self):
        c = ClaudeCodeCLIConnector()
        assert c._provider() == LLMProvider.CLAUDE_CLI

    def test_log_tag(self):
        c = ClaudeCodeCLIConnector()
        assert c._log_tag() == "ClaudeCLI"


class TestCursorAgentConnector:
    """Tests for CursorAgentConnector hook methods."""

    def test_default_config(self):
        c = CursorAgentConnector()
        assert c.config.provider == LLMProvider.CURSOR_AGENT
        assert c.config.model == "cursor-agent"

    def test_binary_names(self):
        c = CursorAgentConnector()
        names = c._binary_names()
        assert "agent" in names
        assert "agent.cmd" in names

    def test_build_cmd(self):
        c = CursorAgentConnector()
        cmd = c._build_cmd("/usr/bin/agent", "test", None)
        assert cmd == ["/usr/bin/agent", "--trust", "-p"]

    def test_prepare_stdin_with_system(self):
        """Cursor pipes system + user via stdin."""
        c = CursorAgentConnector()
        data = c._prepare_stdin("edit video", "sys instructions")
        text = data.decode("utf-8")
        assert "SYSTEM INSTRUCTIONS" in text
        assert "sys instructions" in text
        assert "edit video" in text

    def test_model_name(self):
        c = CursorAgentConnector()
        assert c._model_name() == "cursor-agent"

    def test_provider(self):
        c = CursorAgentConnector()
        assert c._provider() == LLMProvider.CURSOR_AGENT

    def test_log_tag(self):
        c = CursorAgentConnector()
        assert c._log_tag() == "CursorAgent"


class TestQwenCodeCLIConnector:
    """Tests for QwenCodeCLIConnector hook methods."""

    def test_default_config(self):
        c = QwenCodeCLIConnector()
        assert c.config.provider == LLMProvider.QWEN_CLI
        assert c.config.model == "qwen-cli"

    def test_binary_names(self):
        c = QwenCodeCLIConnector()
        names = c._binary_names()
        assert "qwen" in names
        assert "qwen.cmd" in names

    def test_build_cmd(self):
        c = QwenCodeCLIConnector()
        cmd = c._build_cmd("/usr/bin/qwen", "test", None)
        assert "--output-format" in cmd
        assert "text" in cmd
        assert "-p" in cmd

    def test_prepare_stdin_with_system(self):
        c = QwenCodeCLIConnector()
        data = c._prepare_stdin("edit", "sys")
        text = data.decode("utf-8")
        assert "SYSTEM INSTRUCTIONS" in text
        assert "sys" in text
        assert "edit" in text

    def test_model_name(self):
        c = QwenCodeCLIConnector()
        assert c._model_name() == "qwen-cli"

    def test_provider(self):
        c = QwenCodeCLIConnector()
        assert c._provider() == LLMProvider.QWEN_CLI

    def test_log_tag(self):
        c = QwenCodeCLIConnector()
        assert c._log_tag() == "QwenCLI"

    def test_install_hint_contains_url(self):
        c = QwenCodeCLIConnector()
        hint = c._install_hint()
        assert "qwen" in hint.lower()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLIConnectorBase generate / chat_with_tools
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestCLIGenerate:
    """Tests for CLIConnectorBase.generate (mocked subprocess)."""

    @pytest.fixture
    def connector(self):
        """Use GeminiCLIConnector as a concrete subclass."""
        return GeminiCLIConnector()

    @pytest.mark.asyncio
    async def test_generate_success(self, connector):
        """Successful subprocess should return LLMResponse with content."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"Generated response text", b"")
        )
        mock_proc.returncode = 0

        with patch.object(connector, "_resolve_binary", return_value="/usr/bin/gemini"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc), \
             patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = (b"Generated response text", b"")
            mock_proc.communicate = AsyncMock(
                return_value=(b"Generated response text", b"")
            )

            # Directly mock at a higher level
            mock_wait.return_value = (b"Generated response text", b"")

            response = await connector.generate("test prompt")

        assert response.content == "Generated response text"
        assert response.model == "gemini-cli"
        assert response.provider == LLMProvider.GEMINI_CLI

    @pytest.mark.asyncio
    async def test_generate_sandboxes_cwd_to_node_dir(self, connector):
        """Subprocess should run with cwd= set to the node directory (security sandbox)."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"response", b"")
        )
        mock_proc.returncode = 0

        with patch.object(connector, "_resolve_binary", return_value="/usr/bin/gemini"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec, \
             patch("asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = (b"response", b"")
            await connector.generate("test prompt")

        # Verify cwd was passed and points to the node root (3 parents up from cli_base.py)
        mock_exec.assert_called_once()
        call_kwargs = mock_exec.call_args
        cwd = call_kwargs.kwargs.get("cwd") or call_kwargs[1].get("cwd")
        assert cwd is not None, "create_subprocess_exec must be called with cwd="
        assert cwd.endswith("ComfyUI-FFMPEGA"), f"cwd should be the node dir, got: {cwd}"

    @pytest.mark.asyncio
    async def test_generate_binary_not_found(self, connector):
        """Missing binary should raise RuntimeError with install hint."""
        with patch.object(connector, "_resolve_binary", side_effect=RuntimeError("not found")):
            with pytest.raises(RuntimeError, match="not found"):
                await connector.generate("test")

    @pytest.mark.asyncio
    async def test_is_available_true(self, connector):
        """is_available returns True when binary is found."""
        with patch.object(_cli_base_mod, "resolve_cli_binary", return_value="/usr/bin/gemini"):
            assert await connector.is_available() is True

    @pytest.mark.asyncio
    async def test_is_available_false(self, connector):
        """is_available returns False when binary is not found."""
        with patch.object(_cli_base_mod, "resolve_cli_binary", return_value=None):
            assert await connector.is_available() is False

    @pytest.mark.asyncio
    async def test_list_models(self, connector):
        """list_models should return the single model identifier."""
        models = await connector.list_models()
        assert models == ["gemini-cli"]


class TestCLIChatWithTools:
    """Tests for CLIConnectorBase.chat_with_tools."""

    @pytest.fixture
    def connector(self):
        return GeminiCLIConnector()

    @pytest.mark.asyncio
    async def test_chat_with_tool_calls_parsed(self, connector):
        """When LLM output has TOOL_CALL markers, they should be parsed."""
        tool_output = (
            'Let me search for skills.\n'
            'TOOL_CALL: {"name": "search_skills", "arguments": {"query": "blur"}}'
        )
        mock_response = LLMResponse(
            content=tool_output,
            model="gemini-cli",
            provider=LLMProvider.GEMINI_CLI,
        )
        with patch.object(connector, "generate", new_callable=AsyncMock, return_value=mock_response):
            result = await connector.chat_with_tools(
                messages=[{"role": "user", "content": "blur video"}],
                tools=[],
            )
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["function"]["name"] == "search_skills"
        # Content should have TOOL_CALL stripped
        assert "TOOL_CALL" not in result.content
        assert "Let me search for skills." in result.content

    @pytest.mark.asyncio
    async def test_chat_without_tool_calls(self, connector):
        """When LLM returns no TOOL_CALL markers, tool_calls should be None."""
        final_output = '{"pipeline": [{"skill": "blur"}]}'
        mock_response = LLMResponse(
            content=final_output,
            model="gemini-cli",
            provider=LLMProvider.GEMINI_CLI,
        )
        with patch.object(connector, "generate", new_callable=AsyncMock, return_value=mock_response):
            result = await connector.chat_with_tools(
                messages=[{"role": "user", "content": "blur"}],
                tools=[],
            )
        assert result.tool_calls is None
        assert result.content == final_output


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# cli_utils
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestResolveCLIBinary:
    """Tests for cli_utils.resolve_cli_binary."""

    def test_found_on_path(self):
        """Binary found via shutil.which should be returned."""
        with patch("shutil.which", return_value="/usr/bin/gemini"):
            result = resolve_cli_binary("gemini", "gemini.cmd")
        assert result == "/usr/bin/gemini"

    def test_not_found(self):
        """When binary is not on PATH or fallback dirs, return None."""
        with patch("shutil.which", return_value=None):
            result = resolve_cli_binary("nonexistent_binary_xyz")
        # May or may not be None depending on fallback dir contents,
        # but the binary definitely doesn't exist
        # We test the shutil.which path specifically
        assert result is None or "nonexistent_binary_xyz" not in str(result)

    def test_multiple_names_first_match_wins(self):
        """First matching name should be returned."""
        def mock_which(name):
            if name == "gemini.cmd":
                return "/usr/bin/gemini.cmd"
            return None

        with patch("shutil.which", side_effect=mock_which):
            result = resolve_cli_binary("gemini", "gemini.cmd")
        assert result == "/usr/bin/gemini.cmd"

    def test_fallback_to_search_dirs(self, tmp_path):
        """Binary found in fallback search dirs should be returned."""
        # Create a fake binary
        fake_binary = tmp_path / "gemini"
        fake_binary.touch()

        with patch("shutil.which", return_value=None), \
             patch.object(_cli_utils_mod, "_EXTRA_SEARCH_DIRS", [tmp_path]):
            result = resolve_cli_binary("gemini")
        assert result == str(fake_binary)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OllamaConnector
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestOllamaConnector:
    """Tests for OllamaConnector."""

    def test_default_config(self):
        """Default Ollama config should have sensible defaults."""
        c = OllamaConnector()
        assert c.config.provider == LLMProvider.OLLAMA
        assert c.config.base_url == "http://localhost:11434"

    def test_custom_config(self):
        """Custom config should override defaults."""
        cfg = LLMConfig(model="qwen3:8b", base_url="http://gpu-node:11434")
        c = OllamaConnector(config=cfg)
        assert c.config.model == "qwen3:8b"
        assert c.config.base_url == "http://gpu-node:11434"

    def test_recommended_models(self):
        """Recommended models list should be populated."""
        assert len(OllamaConnector.RECOMMENDED_MODELS) > 0
        assert any("llama" in m for m in OllamaConnector.RECOMMENDED_MODELS)

    def test_format_messages(self):
        """format_messages should produce correct structure."""
        c = OllamaConnector()
        msgs = c.format_messages("test prompt", "system prompt")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "system prompt"
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "test prompt"

    def test_format_messages_no_system(self):
        """Without system prompt, only user message should be returned."""
        c = OllamaConnector()
        msgs = c.format_messages("test prompt")
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# APIConnector
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestAPIConnector:
    """Tests for APIConnector."""

    def test_openai_config_routing(self):
        """OpenAI provider should set correct base_url."""
        cfg = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o",
            api_key="sk-test",
        )
        c = APIConnector(cfg)
        assert "openai.com" in c.config.base_url

    def test_anthropic_config_routing(self):
        """Anthropic provider should set correct base_url and auth."""
        cfg = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-20241022",
            api_key="sk-ant-test",
        )
        c = APIConnector(cfg)
        assert "anthropic.com" in c.config.base_url
        assert c._auth_header == "x-api-key"
        assert c._auth_prefix == ""

    def test_gemini_api_config_routing(self):
        """Gemini API provider should set correct base_url."""
        cfg = LLMConfig(
            provider=LLMProvider.GEMINI,
            model="gemini-2.0-flash",
            api_key="test-key",
        )
        c = APIConnector(cfg)
        assert "generativelanguage.googleapis.com" in c.config.base_url


class TestAPIConnectorToolCalling:
    """Tests for APIConnector tool calling response parsing."""

    @pytest.mark.asyncio
    async def test_openai_tool_call_response(self):
        """OpenAI tool call response should be parsed correctly."""
        cfg = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o",
            api_key="sk-test",
        )
        c = APIConnector(cfg)

        mock_response_data = {
            "model": "gpt-4o",
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_abc123",
                        "function": {
                            "name": "search_skills",
                            "arguments": '{"query": "blur"}',
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            },
        }

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = mock_response_data

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch.object(type(c), "client", new_callable=lambda: property(lambda self: mock_client)):
            result = await c._chat_with_tools_openai(
                messages=[{"role": "user", "content": "blur"}],
                tools=[],
            )

        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["id"] == "call_abc123"
        assert result.tool_calls[0]["function"]["name"] == "search_skills"
        assert result.tool_calls[0]["function"]["arguments"] == '{"query": "blur"}'
        assert result.prompt_tokens == 100

    @pytest.mark.asyncio
    async def test_anthropic_tool_call_response(self):
        """Anthropic tool_use blocks should be parsed correctly."""
        cfg = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-20241022",
            api_key="sk-ant-test",
        )
        c = APIConnector(cfg)

        mock_response_data = {
            "model": "claude-3-5-haiku-20241022",
            "content": [
                {"type": "text", "text": "Let me search for that."},
                {
                    "type": "tool_use",
                    "id": "toolu_abc123",
                    "name": "search_skills",
                    "input": {"query": "blur"},
                },
            ],
            "usage": {
                "input_tokens": 50,
                "output_tokens": 30,
            },
            "stop_reason": "tool_use",
        }

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = mock_response_data

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch.object(type(c), "client", new_callable=lambda: property(lambda self: mock_client)):
            result = await c._chat_with_tools_anthropic(
                messages=[{"role": "user", "content": "blur"}],
                tools=[{
                    "type": "function",
                    "function": {
                        "name": "search_skills",
                        "description": "Search",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }],
            )

        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["id"] == "toolu_abc123"
        assert result.tool_calls[0]["function"]["name"] == "search_skills"
        assert result.tool_calls[0]["function"]["arguments"] == {"query": "blur"}
        assert result.content == "Let me search for that."
        assert result.prompt_tokens == 50

    @pytest.mark.asyncio
    async def test_anthropic_tool_result_conversion(self):
        """Anthropic should convert tool role messages to tool_result blocks."""
        cfg = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-20241022",
            api_key="sk-ant-test",
        )
        c = APIConnector(cfg)

        messages = [
            {"role": "user", "content": "blur"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "toolu_1",
                    "function": {
                        "name": "search_skills",
                        "arguments": '{"query": "blur"}',
                    },
                }],
            },
            {
                "role": "tool",
                "tool_call_id": "toolu_1",
                "content": '{"results": ["gaussian_blur"]}',
            },
        ]

        mock_response_data = {
            "model": "claude-3-5-haiku-20241022",
            "content": [{"type": "text", "text": "Found blur skill."}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = mock_response_data

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch.object(type(c), "client", new_callable=lambda: property(lambda self: mock_client)):
            result = await c._chat_with_tools_anthropic(messages, tools=[])

        # Verify the request payload was formed correctly
        call_args = mock_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload is not None

        # Check that tool result was converted properly
        anthropic_msgs = payload["messages"]
        # Find messages that contain tool_result blocks
        tool_result_msgs = []
        for m in anthropic_msgs:
            if m["role"] == "user" and isinstance(m.get("content"), list):
                for block in m["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_result_msgs.append(block)
        assert len(tool_result_msgs) > 0
        assert tool_result_msgs[0]["tool_use_id"] == "toolu_1"


class TestAPIConnectorFactories:
    """Tests for convenience factory functions."""

    def test_create_openai_connector(self):
        """create_openai_connector should create properly configured connector."""
        c = create_openai_connector(api_key="sk-test", model="gpt-4o-mini")
        assert c.config.provider == LLMProvider.OPENAI
        assert c.config.model == "gpt-4o-mini"
        assert c.config.api_key == "sk-test"

    def test_create_anthropic_connector(self):
        """create_anthropic_connector should create properly configured connector."""
        c = create_anthropic_connector(api_key="sk-ant-test")
        assert c.config.provider == LLMProvider.ANTHROPIC
        assert c.config.model == "claude-3-5-haiku-20241022"
        assert c.config.api_key == "sk-ant-test"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LLMConnector base class
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestLLMConnectorBase:
    """Tests for LLMConnector abstract base class."""

    def test_format_messages_with_system(self):
        """format_messages should include system + user messages."""
        c = GeminiCLIConnector()  # concrete subclass
        msgs = c.format_messages("test prompt", "system prompt")
        assert len(msgs) == 2
        assert msgs[0] == {"role": "system", "content": "system prompt"}
        assert msgs[1] == {"role": "user", "content": "test prompt"}

    def test_format_messages_without_system(self):
        """Without system prompt, only user message."""
        c = GeminiCLIConnector()
        msgs = c.format_messages("just a prompt")
        assert len(msgs) == 1
        assert msgs[0] == {"role": "user", "content": "just a prompt"}

    @pytest.mark.asyncio
    async def test_chat_with_tools_not_implemented_by_default(self):
        """Base LLMConnector.chat_with_tools should raise NotImplementedError."""
        class MinimalConnector(LLMConnector):
            async def generate(self, prompt, system_prompt=None):
                pass
            async def generate_stream(self, prompt, system_prompt=None):
                pass
            async def list_models(self):
                return []
            async def is_available(self):
                return True

        c = MinimalConnector(LLMConfig())
        with pytest.raises(NotImplementedError):
            await c.chat_with_tools([], [])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PipelineGenerator agentic loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPipelineGeneratorAgentic:
    """Tests for PipelineGenerator's agentic pipeline generation."""

    @staticmethod
    def _import_pipeline_generator():
        try:
            from core.pipeline_generator import PipelineGenerator
        except (ImportError, ModuleNotFoundError):
            import importlib.util, os
            _spec = importlib.util.spec_from_file_location(
                "core.pipeline_generator",
                os.path.join(os.path.dirname(__file__), "..", "core", "pipeline_generator.py"),
            )
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            PipelineGenerator = _mod.PipelineGenerator
        return PipelineGenerator

    def test_pipeline_generator_creation(self):
        """PipelineGenerator should be instantiable without args."""
        PipelineGenerator = self._import_pipeline_generator()
        gen = PipelineGenerator()
        assert gen is not None

    def test_parse_response_with_tool_calls_text(self):
        """Text containing TOOL_CALL markers should not parse as valid JSON pipeline."""
        PipelineGenerator = self._import_pipeline_generator()
        gen = PipelineGenerator()

        text = 'TOOL_CALL: {"name": "search_skills", "arguments": {"query": "blur"}}'
        result = gen.parse_response(text)
        # TOOL_CALL text is not valid pipeline JSON
        assert result is None or "pipeline" not in result

    def test_parse_response_with_valid_pipeline(self):
        """Valid pipeline JSON should parse correctly."""
        PipelineGenerator = self._import_pipeline_generator()
        gen = PipelineGenerator()

        pipeline = {
            "interpretation": "Apply blur effect",
            "pipeline": [{"skill": "blur", "params": {"radius": 5}}],
            "warnings": [],
            "estimated_changes": "blur effect",
        }
        result = gen.parse_response(json.dumps(pipeline))
        assert result is not None
        assert result["pipeline"][0]["skill"] == "blur"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Marker constant
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestToolCallMarker:
    """Test the TOOL_CALL marker constant."""

    def test_marker_value(self):
        """TOOL_CALL marker should be 'TOOL_CALL:'."""
        assert _TOOL_CALL_MARKER == "TOOL_CALL:"

    def test_marker_used_in_build_prompt(self):
        """_build_tool_prompt should reference the TOOL_CALL marker."""
        tools = [{
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "A test tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        system, _ = CLIConnectorBase._build_tool_prompt(
            [{"role": "user", "content": "test"}], tools
        )
        assert _TOOL_CALL_MARKER in system
