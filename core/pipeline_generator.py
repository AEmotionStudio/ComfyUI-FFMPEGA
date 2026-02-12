"""Pipeline generation via LLM, extracted from FFMPEGAgentNode.

Handles LLM connector creation, single-shot and agentic pipeline
generation, JSON parsing, and retry logic.
"""

import json
import logging
import re
from typing import Optional

logger = logging.getLogger("ffmpega")


class PipelineGenerator:
    """Generate FFMPEG pipelines from natural language using LLMs."""

    def __init__(self, registry=None):
        """Initialize the generator.

        Args:
            registry: Optional SkillRegistry for retry prompts and agentic tools.
        """
        self._registry = registry

    @property
    def registry(self):
        if self._registry is None:
            from ..skills.registry import get_registry  # type: ignore[import-not-found]
            self._registry = get_registry()
        return self._registry

    # ------------------------------------------------------------------ #
    #  Connector factory                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def create_connector(model: str, ollama_url: str, api_key: str):
        """Create appropriate LLM connector based on model selection."""
        from ..core.llm.base import LLMConfig, LLMProvider  # type: ignore[import-not-found]
        from ..core.llm.ollama import OllamaConnector  # type: ignore[import-not-found]
        from ..core.llm.api import APIConnector  # type: ignore[import-not-found]
        from ..core.llm.gemini_cli import GeminiCLIConnector  # type: ignore[import-not-found]

        # Provider is detected by model name prefix.
        # No need to maintain a hardcoded list — any model with a
        # recognised prefix is routed to the right API connector.

        # Gemini CLI — uses local binary, no API key needed
        if model == "gemini-cli":
            config = LLMConfig(
                provider=LLMProvider.GEMINI_CLI,
                model=model,
                temperature=0.3,
            )
            return GeminiCLIConnector(config)

        # Claude Code CLI — uses local binary, no API key needed
        if model == "claude-cli":
            from ..core.llm.claude_cli import ClaudeCodeCLIConnector  # type: ignore[import-not-found]
            config = LLMConfig(
                provider=LLMProvider.CLAUDE_CLI,
                model=model,
                temperature=0.3,
            )
            return ClaudeCodeCLIConnector(config)

        # Cursor Agent CLI — uses local binary, no API key needed
        if model == "cursor-agent":
            from ..core.llm.cursor_agent import CursorAgentConnector  # type: ignore[import-not-found]
            config = LLMConfig(
                provider=LLMProvider.CURSOR_AGENT,
                model=model,
                temperature=0.3,
            )
            return CursorAgentConnector(config)

        # Qwen Code CLI — uses local binary, free OAuth auth
        if model == "qwen-cli":
            from ..core.llm.qwen_cli import QwenCodeCLIConnector  # type: ignore[import-not-found]
            config = LLMConfig(
                provider=LLMProvider.QWEN_CLI,
                model=model,
                temperature=0.3,
            )
            return QwenCodeCLIConnector(config)

        if model.startswith("gpt"):
            config = LLMConfig(
                provider=LLMProvider.OPENAI,
                model=model,
                api_key=api_key,
                temperature=0.3,
            )
            return APIConnector(config)

        if model.startswith("claude"):
            config = LLMConfig(
                provider=LLMProvider.ANTHROPIC,
                model=model,
                api_key=api_key,
                temperature=0.3,
            )
            return APIConnector(config)

        if model.startswith("gemini"):
            config = LLMConfig(
                provider=LLMProvider.GEMINI,
                model=model,
                api_key=api_key,
                temperature=0.3,
            )
            return APIConnector(config)

        # Qwen API models use dash format: qwen-max, qwen-plus, qwen-turbo
        # Ollama Qwen models use colon format: qwen3:8b, qwen2.5:7b
        # Only match dash-prefixed names to avoid hijacking Ollama models.
        if model.startswith("qwen-") and model != "qwen-cli":
            config = LLMConfig(
                provider=LLMProvider.QWEN,
                model=model,
                api_key=api_key,
                temperature=0.3,
            )
            return APIConnector(config)

        # Default: treat as Ollama model
        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model=model,
            base_url=ollama_url,
            temperature=0.3,
        )
        return OllamaConnector(config)

    # ------------------------------------------------------------------ #
    #  High-level generate (with retry)                                    #
    # ------------------------------------------------------------------ #

    async def generate(
        self,
        connector,
        prompt: str,
        video_metadata: str,
        connected_inputs: str = "",
    ) -> dict:
        """Generate a pipeline spec, with auto-retry on invalid JSON.

        Args:
            connector: LLM connector instance.
            prompt: User's editing prompt.
            video_metadata: Video analysis string.
            connected_inputs: Summary of connected inputs.

        Returns:
            Parsed pipeline dict.

        Raises:
            ValueError: If pipeline generation fails after retry.
        """
        # Try agentic mode first, fall back to single-shot
        try:
            raw_response = await self._generate_agentic(
                connector, prompt, video_metadata, connected_inputs
            )
        except NotImplementedError:
            raw_response = await self._generate_single_shot(
                connector, prompt, video_metadata, connected_inputs
            )

        spec = self.parse_response(raw_response)

        if spec is None:
            # Auto-retry: send the bad response back asking for JSON only
            logger.warning("LLM returned non-JSON, attempting correction retry...")
            spec = await self._retry_for_json(connector, prompt)

        if spec is None:
            preview = raw_response[:300] if raw_response else "(empty)"
            raise ValueError(
                f"Failed to parse LLM response as JSON.\n"
                f"LLM returned: {preview}\n"
                f"Tip: Try running the prompt again or use a different model."
            )

        return spec

    async def _retry_for_json(self, connector, prompt: str) -> Optional[dict]:
        """Send a correction prompt asking for JSON-only output."""
        try:
            skill_names = sorted([s.name for s in self.registry.list_all()])
            skill_list = ", ".join(skill_names)

            correction_prompt = (
                "Your previous response was not valid JSON. Please respond with "
                "ONLY a JSON object in this exact format, nothing else:\n"
                '{"interpretation": "...", "pipeline": [{"skill": "name", "params": {}}], '
                '"warnings": [], "estimated_changes": "..."}\n\n'
                f"Available skills (use ONLY these names): {skill_list}\n\n"
                f"Original request: {prompt}"
            )
            retry_response = await connector.generate(
                correction_prompt,
                "You are a JSON-only assistant. Respond with ONLY valid JSON, "
                "no markdown, no explanation. Use ONLY skill names from the provided list.",
            )
            return self.parse_response(retry_response.content)
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  Single-shot generation                                              #
    # ------------------------------------------------------------------ #

    async def _generate_single_shot(
        self, connector, prompt: str, video_metadata: str,
        connected_inputs: str = "",
    ) -> str:
        """Single-shot generation: full registry in system prompt."""
        from ..prompts.system import get_system_prompt  # type: ignore[import-not-found]
        from ..prompts.generation import get_generation_prompt  # type: ignore[import-not-found]

        system_prompt = get_system_prompt(
            video_metadata=video_metadata,
            include_full_registry=True,
            connected_inputs=connected_inputs,
        )
        user_prompt = get_generation_prompt(prompt, video_metadata, connected_inputs)
        response = await connector.generate(user_prompt, system_prompt)
        return response.content

    # ------------------------------------------------------------------ #
    #  Agentic generation (tool-calling)                                   #
    # ------------------------------------------------------------------ #

    async def _generate_agentic(
        self,
        connector,
        prompt: str,
        video_metadata: str,
        connected_inputs: str = "",
        max_iterations: int = 10,
    ) -> str:
        """Agentic pipeline generation with tool calling.

        Raises:
            NotImplementedError: If connector doesn't support tool calling.
        """
        from ..prompts.system import get_agentic_system_prompt  # type: ignore[import-not-found]
        from ..prompts.generation import get_generation_prompt  # type: ignore[import-not-found]
        from ..mcp.tool_defs import TOOL_DEFINITIONS  # type: ignore[import-not-found]
        from ..mcp.tools import (  # type: ignore[import-not-found]
            analyze_video,
            build_pipeline,
            list_skills,
            search_skills,
            get_skill_details,
        )

        system_prompt = get_agentic_system_prompt(
            video_metadata=video_metadata,
            connected_inputs=connected_inputs,
        )
        user_prompt = get_generation_prompt(prompt, video_metadata, connected_inputs)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        tool_handlers = {
            "list_skills": lambda args: list_skills(args.get("category")),
            "search_skills": lambda args: search_skills(args.get("query", "")),
            "get_skill_details": lambda args: get_skill_details(args.get("skill_name", "")),
            "analyze_video": lambda args: analyze_video(args.get("video_path", "")),
            "build_pipeline": lambda args: build_pipeline(
                skills=args.get("skills", []),
                input_path=args.get("input_path", "/tmp/input.mp4"),
                output_path=args.get("output_path", "/tmp/output.mp4"),
            ),
        }

        for iteration in range(max_iterations):
            response = await connector.chat_with_tools(messages, TOOL_DEFINITIONS)

            if not response.tool_calls:
                parsed = self.parse_response(response.content)
                if parsed is not None:
                    return response.content

                logger.warning(
                    f"Agentic iteration {iteration+1}: model returned "
                    f"non-JSON, requesting correction..."
                )
                messages.append({"role": "assistant", "content": response.content or ""})
                messages.append({
                    "role": "user",
                    "content": (
                        "That response was not valid JSON. You MUST respond with "
                        "ONLY a JSON object like: "
                        '{"interpretation": "...", "pipeline": '
                        '[{"skill": "skill_name", "params": {}}], '
                        '"warnings": [], "estimated_changes": "..."}\n'
                        "Use get_skill_details to confirm exact skill names "
                        "before outputting the pipeline. Do NOT explain — "
                        "just output the JSON."
                    ),
                })
                continue

            # Process tool calls
            assistant_msg = {"role": "assistant", "content": response.content or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.get("id", f"call_{i}"),
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    }
                }
                for i, tc in enumerate(response.tool_calls)
            ]
            messages.append(assistant_msg)

            for i, tool_call in enumerate(response.tool_calls):
                func_name = tool_call["function"]["name"]
                func_args = tool_call["function"]["arguments"]
                # OpenAI returns arguments as JSON string; handlers expect dict
                if isinstance(func_args, str):
                    try:
                        func_args = json.loads(func_args)
                    except (json.JSONDecodeError, ValueError):
                        func_args = {}

                logger.info(f"Tool call [{iteration+1}]: {func_name}({func_args})")

                handler = tool_handlers.get(func_name)
                if handler:
                    try:
                        result = handler(func_args)
                        result_str = json.dumps(result, indent=2)
                    except Exception as e:
                        result_str = json.dumps({"error": str(e)})
                        logger.warning(f"Tool error: {func_name} -> {e}")
                else:
                    result_str = json.dumps({"error": f"Unknown tool: {func_name}"})

                tool_result_msg = {
                    "role": "tool",
                    "content": result_str,
                    "tool_call_id": tool_call.get("id", f"call_{i}"),
                }
                messages.append(tool_result_msg)

        # Exhausted iterations
        logger.warning(f"Agentic loop hit max iterations ({max_iterations})")
        messages.append({
            "role": "user",
            "content": (
                "You have used all available tool calls. Based on "
                "what you've learned, please output the final JSON "
                "pipeline now."
            ),
        })
        response = await connector.chat_with_tools(messages, [])
        return response.content

    # ------------------------------------------------------------------ #
    #  JSON parsing                                                        #
    # ------------------------------------------------------------------ #

    def parse_response(self, text: str) -> Optional[dict]:
        """Parse a pipeline response, trying direct JSON then extraction."""
        if not text or not text.strip():
            return None
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return self._extract_json(text)

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """Try to extract JSON from text that may contain other content."""
        # 1. Try fenced JSON blocks first
        for pattern in [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
        ]:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    result = json.loads(match)
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    continue

        # 2. Try to find a JSON object containing "pipeline"
        pipeline_match = re.search(
            r'(\{[^{}]*"pipeline"[^{}]*\[.*?\][^{}]*\})',
            text, re.DOTALL
        )
        if pipeline_match:
            try:
                return json.loads(pipeline_match.group(1))
            except json.JSONDecodeError:
                pass

        # 3. Find the outermost {...} using brace matching
        start = text.find('{')
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i+1])
                        except json.JSONDecodeError:
                            break

        return None
