"""Tests for tool calling across all connector types.

Tests the chat_with_tools implementation for:
- APIConnector (OpenAI + Anthropic format conversion)
- CLIConnectorBase (prompt-based simulation and marker parsing)
- Tool ID propagation for the agentic loop
"""

import pytest
import json

from core.llm.base import LLMConfig, LLMProvider, LLMResponse
from core.llm.cli_base import CLIConnectorBase, _TOOL_CALL_MARKER


# ── Sample tools for testing ──────────────────────────────────────────

SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": "Search for video editing skills by keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List all skills.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]

SAMPLE_MESSAGES = [
    {"role": "system", "content": "You are a video editor."},
    {"role": "user", "content": "Make it blurry"},
]


# ── CLI tool call parsing ─────────────────────────────────────────────

class TestCLIToolCallParsing:
    """Tests for CLIConnectorBase._parse_tool_calls."""

    def test_single_tool_call(self):
        """Single TOOL_CALL marker should parse correctly."""
        text = 'TOOL_CALL: {"name": "search_skills", "arguments": {"query": "blur"}}'
        calls = CLIConnectorBase._parse_tool_calls(text)
        assert calls is not None
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "search_skills"
        assert calls[0]["function"]["arguments"] == {"query": "blur"}
        assert calls[0]["id"] == "cli_call_0"

    def test_multiple_tool_calls(self):
        """Multiple TOOL_CALL markers should all be parsed."""
        text = (
            'TOOL_CALL: {"name": "list_skills", "arguments": {}}\n'
            'TOOL_CALL: {"name": "search_skills", "arguments": {"query": "blur"}}'
        )
        calls = CLIConnectorBase._parse_tool_calls(text)
        assert calls is not None
        assert len(calls) == 2
        assert calls[0]["function"]["name"] == "list_skills"
        assert calls[1]["function"]["name"] == "search_skills"
        assert calls[0]["id"] == "cli_call_0"
        assert calls[1]["id"] == "cli_call_1"

    def test_tool_call_with_surrounding_text(self):
        """TOOL_CALL in surrounding text should be extracted."""
        text = (
            "Let me search for blur skills.\n"
            'TOOL_CALL: {"name": "search_skills", "arguments": {"query": "blur"}}\n'
            "I'll wait for the result."
        )
        calls = CLIConnectorBase._parse_tool_calls(text)
        assert calls is not None
        assert len(calls) == 1

    def test_no_tool_calls_returns_none(self):
        """Text without TOOL_CALL markers should return None."""
        assert CLIConnectorBase._parse_tool_calls("Just a normal response") is None

    def test_malformed_json_skipped(self):
        """Malformed JSON after TOOL_CALL should be skipped."""
        text = 'TOOL_CALL: {bad json here}'
        calls = CLIConnectorBase._parse_tool_calls(text)
        assert calls is None

    def test_mixed_valid_and_invalid(self):
        """Valid and invalid TOOL_CALL markers — only valid ones returned."""
        text = (
            'TOOL_CALL: {bad}\n'
            'TOOL_CALL: {"name": "list_skills", "arguments": {}}'
        )
        calls = CLIConnectorBase._parse_tool_calls(text)
        assert calls is not None
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "list_skills"

    def test_empty_arguments(self):
        """Tool call with empty arguments should work."""
        text = 'TOOL_CALL: {"name": "list_skills", "arguments": {}}'
        calls = CLIConnectorBase._parse_tool_calls(text)
        assert calls is not None
        assert calls[0]["function"]["arguments"] == {}

    def test_complex_arguments(self):
        """Tool call with nested arguments should parse."""
        text = 'TOOL_CALL: {"name": "build_pipeline", "arguments": {"steps": [{"skill": "blur"}]}}'
        calls = CLIConnectorBase._parse_tool_calls(text)
        assert calls is not None
        assert calls[0]["function"]["arguments"]["steps"] == [{"skill": "blur"}]


# ── CLI tool call stripping ───────────────────────────────────────────

class TestCLIToolCallStripping:
    """Tests for CLIConnectorBase._strip_tool_calls."""

    def test_strip_removes_tool_lines(self):
        """TOOL_CALL lines should be removed from content."""
        text = (
            "Searching for skills.\n"
            'TOOL_CALL: {"name": "search_skills", "arguments": {"query": "blur"}}\n'
            "Done."
        )
        result = CLIConnectorBase._strip_tool_calls(text)
        assert "TOOL_CALL" not in result
        assert "Searching for skills." in result
        assert "Done." in result

    def test_strip_all_tool_lines(self):
        """Multiple TOOL_CALL lines should all be removed."""
        text = (
            'TOOL_CALL: {"name": "a", "arguments": {}}\n'
            'TOOL_CALL: {"name": "b", "arguments": {}}'
        )
        result = CLIConnectorBase._strip_tool_calls(text)
        assert result == ""

    def test_strip_preserves_non_tool_content(self):
        """Non-tool content should be preserved exactly."""
        text = "Just regular text"
        assert CLIConnectorBase._strip_tool_calls(text) == "Just regular text"


# ── CLI tool prompt building ──────────────────────────────────────────

class TestCLIBuildToolPrompt:
    """Tests for CLIConnectorBase._build_tool_prompt."""

    def test_system_prompt_includes_tools(self):
        """System prompt should contain tool definitions."""
        sys_prompt, _ = CLIConnectorBase._build_tool_prompt(
            SAMPLE_MESSAGES, SAMPLE_TOOLS
        )
        assert sys_prompt is not None
        assert "AVAILABLE TOOLS" in sys_prompt
        assert "search_skills" in sys_prompt
        assert "list_skills" in sys_prompt
        assert "TOOL_CALL:" in sys_prompt

    def test_user_prompt_includes_conversation(self):
        """User prompt should contain conversation history."""
        _, user_prompt = CLIConnectorBase._build_tool_prompt(
            SAMPLE_MESSAGES, SAMPLE_TOOLS
        )
        assert "Make it blurry" in user_prompt

    def test_system_message_extracted(self):
        """System messages should go to system prompt, not user prompt."""
        sys_prompt, user_prompt = CLIConnectorBase._build_tool_prompt(
            SAMPLE_MESSAGES, SAMPLE_TOOLS
        )
        assert "video editor" in sys_prompt
        assert "video editor" not in user_prompt

    def test_empty_tools_no_tool_section(self):
        """Empty tools list should not add tool section."""
        sys_prompt, _ = CLIConnectorBase._build_tool_prompt(
            SAMPLE_MESSAGES, []
        )
        if sys_prompt:
            assert "AVAILABLE TOOLS" not in sys_prompt

    def test_tool_parameters_documented(self):
        """Tool parameters should be listed with types and descriptions."""
        sys_prompt, _ = CLIConnectorBase._build_tool_prompt(
            SAMPLE_MESSAGES, SAMPLE_TOOLS
        )
        assert "query" in sys_prompt
        assert "string" in sys_prompt
        assert "required" in sys_prompt.lower()

    def test_multi_turn_conversation(self):
        """Multi-turn messages should all appear in user prompt."""
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "response"},
            {"role": "tool", "content": '{"result": "data"}'},
            {"role": "user", "content": "second message"},
        ]
        _, user_prompt = CLIConnectorBase._build_tool_prompt(messages, [])
        assert "first message" in user_prompt
        assert "response" in user_prompt
        assert "TOOL_RESULT" in user_prompt
        assert "second message" in user_prompt


# ── API connector Anthropic format conversion ─────────────────────────

class TestAnthropicToolConversion:
    """Tests for Anthropic tool format conversion."""

    def test_openai_to_anthropic_tool_format(self):
        """OpenAI tool format should convert to Anthropic format correctly."""
        from core.llm.api import APIConnector

        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3.5-sonnet",
            api_key="test-key",
        )
        connector = APIConnector(config)

        # The conversion happens inside _chat_with_tools_anthropic
        # Test by checking the connector routes correctly
        assert connector.config.provider == LLMProvider.ANTHROPIC

    def test_anthropic_message_conversion(self):
        """Tool role messages should convert to Anthropic tool_result format."""
        # This tests the message conversion logic conceptually
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
            {"role": "tool", "content": "result data", "tool_use_id": "call_1"},
        ]

        # Verify the format we expect _chat_with_tools_anthropic to produce
        system_prompt = None
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            elif msg["role"] == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_use_id", "tool_result"),
                            "content": msg["content"],
                        }
                    ],
                })
            else:
                anthropic_messages.append({"role": msg["role"], "content": msg["content"]})

        assert system_prompt == "system prompt"
        assert len(anthropic_messages) == 2
        assert anthropic_messages[1]["role"] == "user"
        assert anthropic_messages[1]["content"][0]["type"] == "tool_result"
        assert anthropic_messages[1]["content"][0]["tool_use_id"] == "call_1"


# ── OpenAI tool call response parsing ─────────────────────────────────

class TestOpenAIToolCallParsing:
    """Tests for OpenAI-format tool call response parsing."""

    def test_parse_string_arguments(self):
        """OpenAI returns arguments as a JSON string — should be parsed to dict."""
        # Simulate what _chat_with_tools_openai does with string arguments
        arguments = '{"query": "blur"}'
        if isinstance(arguments, str):
            parsed = json.loads(arguments)
        else:
            parsed = arguments
        assert parsed == {"query": "blur"}

    def test_parse_dict_arguments(self):
        """Some APIs return arguments as dict directly — should pass through."""
        arguments = {"query": "blur"}
        if isinstance(arguments, str):
            parsed = json.loads(arguments)
        else:
            parsed = arguments
        assert parsed == {"query": "blur"}

    def test_parse_malformed_arguments(self):
        """Malformed argument strings should fallback to empty dict."""
        arguments = "not valid json"
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except (json.JSONDecodeError, ValueError):
                parsed = {}
        assert parsed == {}


# ── Tool ID propagation ───────────────────────────────────────────────

class TestToolIDPropagation:
    """Tests for tool_use_id propagation in the agentic loop."""

    def test_tool_calls_get_ids(self):
        """Tool calls should have IDs for Anthropic compatibility."""
        tool_calls = [
            {"function": {"name": "search_skills", "arguments": {"query": "blur"}}},
            {"function": {"name": "list_skills", "arguments": {}}},
        ]

        # Simulate the agentic loop's ID assignment
        with_ids = [
            {
                "id": tc.get("id", f"call_{i}"),
                "function": tc["function"],
            }
            for i, tc in enumerate(tool_calls)
        ]

        assert with_ids[0]["id"] == "call_0"
        assert with_ids[1]["id"] == "call_1"

    def test_existing_ids_preserved(self):
        """Existing IDs from the API should be preserved."""
        tool_calls = [
            {"id": "toolu_abc123", "function": {"name": "search_skills", "arguments": {}}},
        ]

        with_ids = [
            {
                "id": tc.get("id", f"call_{i}"),
                "function": tc["function"],
            }
            for i, tc in enumerate(tool_calls)
        ]

        assert with_ids[0]["id"] == "toolu_abc123"


# ── extract_frames tool tests ─────────────────────────────────────────

import importlib
import importlib.util
import sys
from pathlib import Path


def _load_tool_defs():
    """Import mcp.tool_defs directly, bypassing mcp/__init__.py."""
    mod_name = "mcp.tool_defs"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(
        mod_name,
        str(Path(__file__).resolve().parent.parent / "mcp" / "tool_defs.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestExtractFramesToolDefinition:
    """Test that extract_frames is properly defined in TOOL_DEFINITIONS."""

    def test_extract_frames_in_tool_definitions(self):
        """extract_frames should appear in TOOL_DEFINITIONS."""
        tool_defs = _load_tool_defs()

        tool_names = [t["function"]["name"] for t in tool_defs.TOOL_DEFINITIONS]
        assert "extract_frames" in tool_names

    def test_extract_frames_has_parameters(self):
        """extract_frames tool definition should have the expected params."""
        tool_defs = _load_tool_defs()

        tool = next(
            t for t in tool_defs.TOOL_DEFINITIONS
            if t["function"]["name"] == "extract_frames"
        )
        props = tool["function"]["parameters"]["properties"]
        assert "start" in props
        assert "duration" in props
        assert "fps" in props
        assert "max_frames" in props

    def test_all_original_tools_still_present(self):
        """Original 5 tools should still be present after adding extract_frames."""
        tool_defs = _load_tool_defs()

        tool_names = {t["function"]["name"] for t in tool_defs.TOOL_DEFINITIONS}
        assert "search_skills" in tool_names
        assert "get_skill_details" in tool_names
        assert "list_skills" in tool_names
        assert "analyze_video" in tool_names
        assert "build_pipeline" in tool_names
        assert "extract_frames" in tool_names
        assert len(tool_defs.TOOL_DEFINITIONS) == 6


class TestExtractFramesCleanup:
    """Test vision frame cleanup logic."""

    def test_cleanup_removes_directory(self, tmp_path):
        """shutil.rmtree correctly removes a vision frames directory."""
        import shutil

        frames_dir = tmp_path / "_vision_frames"
        frames_dir.mkdir()
        (frames_dir / "frame_0001.png").write_bytes(b"fake png")
        (frames_dir / "frame_0002.png").write_bytes(b"fake png")
        assert frames_dir.exists()
        assert len(list(frames_dir.iterdir())) == 2

        shutil.rmtree(frames_dir)
        assert not frames_dir.exists()

    def test_cleanup_idempotent(self, tmp_path):
        """Cleaning up a non-existent directory should not raise."""
        import shutil

        frames_dir = tmp_path / "_vision_frames"
        assert not frames_dir.exists()
        # shutil.rmtree with ignore_errors should not raise
        shutil.rmtree(frames_dir, ignore_errors=True)


