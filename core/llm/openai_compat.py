"""OpenAI-compatible LLM connector for local servers.

Covers LM Studio, Unsloth Studio, llama.cpp's llama-server, vLLM and any
other server that speaks /v1/chat/completions. The base URL includes the
/v1 suffix, e.g. http://localhost:1234/v1.
"""

import json
from collections.abc import AsyncIterator

import httpx  # type: ignore[import-not-found]

from ..sanitize import sanitize_api_key
from .base import LLMConfig, LLMConnector, LLMProvider, LLMResponse  # type: ignore[import-not-found]


class OpenAICompatConnector(LLMConnector):
    """Connector for a local OpenAI-compatible server."""

    def __init__(self, config: LLMConfig):
        super().__init__(config)  # type: ignore[misc]
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers=headers,
                timeout=httpx.Timeout(
                    connect=30.0,
                    read=self.config.timeout,
                    write=30.0,
                    pool=30.0,
                ),
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()  # type: ignore[union-attr]
            self._client = None

    @property
    def supports_vision(self) -> bool:
        """Vision models accept image_url parts; text-only ones reject them."""
        return True

    def _error(self, e: httpx.HTTPError) -> RuntimeError:
        """Build a sanitized error that keeps the server's own reason."""
        if isinstance(e, httpx.HTTPStatusError):
            detail = f"HTTP {e.response.status_code}: {e.response.text[:500]}"
        else:
            detail = str(e)
        msg = sanitize_api_key(detail, self.config.api_key or "")
        return RuntimeError(f"OpenAI-compatible server error ({self.config.base_url}): {msg}")

    async def _post(self, payload: dict) -> dict:
        try:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise self._error(e) from None
        return response.json()

    def _payload(self, messages: list[dict]) -> dict:
        return {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

    def _response(self, data: dict, tool_calls: list[dict] | None = None) -> LLMResponse:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return LLMResponse(
            content=message.get("content") or "",
            model=data.get("model", self.config.model),
            provider=LLMProvider.OPENAI_COMPAT,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            finish_reason=choice.get("finish_reason"),
            raw_response=data,
            tool_calls=tool_calls,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Generate a response.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.

        Returns:
            LLMResponse with generated content.
        """
        data = await self._post(self._payload(self.format_messages(prompt, system_prompt)))
        return self._response(data)

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.

        Yields:
            Response content chunks.
        """
        payload = self._payload(self.format_messages(prompt, system_prompt))
        payload["stream"] = True

        try:
            async with self.client.stream("POST", "/chat/completions", json=payload) as response:
                if response.is_error:
                    await response.aread()
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    choices = json.loads(data_str).get("choices") or [{}]
                    content = (choices[0].get("delta") or {}).get("content")
                    if content:
                        yield content
        except httpx.HTTPError as e:
            raise self._error(e) from None

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        """Chat with tool/function-calling support.

        Args:
            messages: Conversation history.
            tools: Tool definitions in OpenAI-compatible format.

        Returns:
            LLMResponse with content and/or tool_calls.
        """
        payload = self._payload(_to_openai_messages(messages))
        if tools:
            payload["tools"] = tools

        data = await self._post(payload)
        message = ((data.get("choices") or [{}])[0].get("message")) or {}

        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = []
            for i, tc in enumerate(message["tool_calls"]):
                func = tc.get("function") or {}
                arguments = func.get("arguments") or "{}"
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments)
                tool_calls.append({
                    "id": tc.get("id") or f"call_{i}",
                    "function": {"name": func.get("name", ""), "arguments": arguments},
                })

        return self._response(data, tool_calls)

    async def list_models(self) -> list[str]:
        """List the model ids the server reports.

        Returns:
            List of model ids.
        """
        response = await self.client.get("/models")
        response.raise_for_status()
        return [m["id"] for m in response.json().get("data", [])]

    async def is_available(self) -> bool:
        """Check if the server is reachable.

        Returns:
            True if GET /models succeeds, False otherwise.
        """
        try:
            response = await self.client.get("/models")
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False


def _to_openai_messages(messages: list[dict]) -> list[dict]:
    """Convert the agent loop's message history to strict OpenAI format.

    Assistant tool calls need ``type: "function"`` and string arguments.
    Tool messages may only carry text, and every tool result must directly
    follow its assistant turn, so frames attached to tool results are moved
    into one user message after the run of tool messages.
    """
    out: list[dict] = []
    frames: list[dict] = []
    for msg in messages:
        if frames and msg.get("role") != "tool":
            out.append(_frames_message(frames))
            frames = []
        if msg.get("tool_calls"):
            out.append({**msg, "tool_calls": [
                _tool_call(tc, i) for i, tc in enumerate(msg["tool_calls"])
            ]})
        elif msg.get("role") == "tool" and isinstance(msg.get("content"), list):
            parts: list[dict] = msg["content"]
            text = "\n".join(str(p.get("text", "")) for p in parts if p.get("type") == "text")
            out.append({**msg, "content": text})
            frames.extend(p for p in parts if p.get("type") == "image_url")
        else:
            out.append(msg)
    if frames:
        out.append(_frames_message(frames))
    return out


def _tool_call(tc: dict, index: int) -> dict:
    arguments = tc["function"]["arguments"]
    return {
        "id": tc.get("id") or f"call_{index}",
        "type": "function",
        "function": {
            "name": tc["function"]["name"],
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
        },
    }


def _frames_message(frames: list[dict]) -> dict:
    return {
        "role": "user",
        "content": [{"type": "text", "text": "Frames returned by the tool calls above:"}, *frames],
    }
