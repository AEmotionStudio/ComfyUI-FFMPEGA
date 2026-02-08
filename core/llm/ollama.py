"""Ollama LLM connector."""

import json
from typing import Optional, AsyncIterator
import httpx  # type: ignore[import-not-found]

from .base import LLMConnector, LLMConfig, LLMResponse, LLMProvider  # type: ignore[import-not-found]


class OllamaConnector(LLMConnector):
    """Connector for local Ollama instance."""

    # Recommended models for video editing tasks
    RECOMMENDED_MODELS = [
        "qwen3:8b",
        "qwen2.5:7b",
        "llama3.1:8b",
        "llama3.1:70b",
        "mistral:7b",
    ]

    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize Ollama connector.

        Args:
            config: LLM configuration. Uses defaults if not provided.
        """
        if config is None:
            config = LLMConfig(
                provider=LLMProvider.OLLAMA,
                model="llama3.1:8b",
                base_url="http://localhost:11434",
            )
        super().__init__(config)  # type: ignore[misc]
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
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

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Generate a response from Ollama.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.

        Returns:
            LLMResponse with generated content.
        """
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        # Merge extra options
        if self.config.extra_options:
            options: dict = payload["options"]  # type: ignore[assignment]
            options.update(self.config.extra_options)

        response = await self.client.post("/api/generate", json=payload)
        response.raise_for_status()

        data = response.json()

        return LLMResponse(
            content=data.get("response", ""),
            model=data.get("model", self.config.model),
            provider=LLMProvider.OLLAMA,
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            total_tokens=(
                (data.get("prompt_eval_count") or 0) +
                (data.get("eval_count") or 0)
            ) or None,
            finish_reason="stop" if data.get("done") else None,
            raw_response=data,
        )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from Ollama.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.

        Yields:
            Response content chunks.
        """
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        if self.config.extra_options:
            options: dict = payload["options"]  # type: ignore[assignment]
            options.update(self.config.extra_options)

        async with self.client.stream("POST", "/api/generate", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    data = json.loads(line)
                    if "response" in data:
                        yield data["response"]

    async def chat(
        self,
        messages: list[dict],
    ) -> LLMResponse:
        """Chat completion with message history.

        Args:
            messages: List of message dicts with 'role' and 'content'.

        Returns:
            LLMResponse with generated content.
        """
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        if self.config.extra_options:
            options: dict = payload["options"]  # type: ignore[assignment]
            options.update(self.config.extra_options)

        response = await self.client.post("/api/chat", json=payload)
        response.raise_for_status()

        data = response.json()
        message = data.get("message", {})

        return LLMResponse(
            content=message.get("content", ""),
            model=data.get("model", self.config.model),
            provider=LLMProvider.OLLAMA,
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            total_tokens=(
                (data.get("prompt_eval_count") or 0) +
                (data.get("eval_count") or 0)
            ) or None,
            finish_reason="stop" if data.get("done") else None,
            raw_response=data,
        )

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        """Chat with tool/function-calling support.

        Sends tool definitions to Ollama's /api/chat endpoint.
        The model may respond with tool_calls requesting function invocations.

        Args:
            messages: Conversation history.
            tools: Tool definitions in OpenAI-compatible format.

        Returns:
            LLMResponse with content and/or tool_calls.
        """
        payload = {
            "model": self.config.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        if self.config.extra_options:
            options: dict = payload["options"]  # type: ignore[assignment]
            options.update(self.config.extra_options)

        response = await self.client.post("/api/chat", json=payload)
        response.raise_for_status()

        data = response.json()
        message = data.get("message", {})

        # Extract tool calls if present
        raw_tool_calls = message.get("tool_calls")
        tool_calls = None
        if raw_tool_calls:
            tool_calls = [
                {
                    "function": {
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", {}),
                    }
                }
                for tc in raw_tool_calls
            ]

        return LLMResponse(
            content=message.get("content", ""),
            model=data.get("model", self.config.model),
            provider=LLMProvider.OLLAMA,
            prompt_tokens=data.get("prompt_eval_count"),
            completion_tokens=data.get("eval_count"),
            total_tokens=(
                (data.get("prompt_eval_count") or 0) +
                (data.get("eval_count") or 0)
            ) or None,
            finish_reason="stop" if data.get("done") else None,
            raw_response=data,
            tool_calls=tool_calls,
        )

    async def list_models(self) -> list[str]:
        """List available Ollama models.

        Returns:
            List of model names.
        """
        response = await self.client.get("/api/tags")
        response.raise_for_status()

        data = response.json()
        return [model["name"] for model in data.get("models", [])]

    async def is_available(self) -> bool:
        """Check if Ollama is available.

        Returns:
            True if Ollama is running, False otherwise.
        """
        try:
            response = await self.client.get("/api/tags")
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def pull_model(self, model: str) -> AsyncIterator[dict]:
        """Pull a model from Ollama registry.

        Args:
            model: Model name to pull.

        Yields:
            Progress information dicts.
        """
        payload = {"name": model, "stream": True}

        async with self.client.stream("POST", "/api/pull", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    yield json.loads(line)

    async def get_model_info(self, model: str) -> dict:
        """Get information about a specific model.

        Args:
            model: Model name.

        Returns:
            Model information dict.
        """
        response = await self.client.post(
            "/api/show",
            json={"name": model}
        )
        response.raise_for_status()
        return response.json()


def create_ollama_connector(
    model: str = "llama3.1:8b",
    base_url: str = "http://localhost:11434",
    temperature: float = 0.3,
) -> OllamaConnector:
    """Create an Ollama connector with common settings.

    Args:
        model: Model to use.
        base_url: Ollama server URL.
        temperature: Generation temperature.

    Returns:
        Configured OllamaConnector.
    """
    config = LLMConfig(
        provider=LLMProvider.OLLAMA,
        model=model,
        base_url=base_url,
        temperature=temperature,
    )
    return OllamaConnector(config)
