"""OpenAI/Anthropic compatible API connector."""

import json
from typing import Optional, AsyncIterator
import httpx

from .base import LLMConnector, LLMConfig, LLMResponse, LLMProvider
from ..sanitize import sanitize_api_key


class APIConnector(LLMConnector):
    """Connector for OpenAI/Anthropic compatible APIs."""

    # Provider-specific configurations
    PROVIDER_CONFIGS = {
        LLMProvider.OPENAI: {
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            "chat_endpoint": "/chat/completions",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer",
        },
        LLMProvider.ANTHROPIC: {
            "base_url": "https://api.anthropic.com/v1",
            "models": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
            "chat_endpoint": "/messages",
            "auth_header": "x-api-key",
            "auth_prefix": "",
        },
        LLMProvider.GEMINI: {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "models": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"],
            "chat_endpoint": "/chat/completions",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer",
        },
        LLMProvider.QWEN: {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": ["qwen-max", "qwen-plus", "qwen-turbo"],
            "chat_endpoint": "/chat/completions",
            "auth_header": "Authorization",
            "auth_prefix": "Bearer",
        },
    }

    def __init__(self, config: LLMConfig):
        """Initialize API connector.

        Args:
            config: LLM configuration with provider and API key.
        """
        super().__init__(config)
        self._client = None

        # Set up provider-specific settings
        provider_config = self.PROVIDER_CONFIGS.get(config.provider, {})
        if not config.base_url and provider_config:
            config.base_url = provider_config.get("base_url", "")

        self._chat_endpoint = provider_config.get("chat_endpoint", "/chat/completions")
        self._auth_header = provider_config.get("auth_header", "Authorization")
        self._auth_prefix = provider_config.get("auth_prefix", "Bearer")

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {}
            if self.config.api_key:
                if self._auth_prefix:
                    headers[self._auth_header] = f"{self._auth_prefix} {self.config.api_key}"
                else:
                    headers[self._auth_header] = self.config.api_key

            # Anthropic requires version header
            if self.config.provider == LLMProvider.ANTHROPIC:
                headers["anthropic-version"] = "2023-06-01"

            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers=headers,
                timeout=self.config.timeout,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Generate a response from the API.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.

        Returns:
            LLMResponse with generated content.
        """
        try:
            if self.config.provider == LLMProvider.ANTHROPIC:
                return await self._generate_anthropic(prompt, system_prompt)
            else:
                # OpenAI, Gemini, and other compatible APIs
                return await self._generate_openai(prompt, system_prompt)
        except httpx.HTTPStatusError as e:
            # Sanitize error to prevent API key leakage via headers
            msg = sanitize_api_key(str(e), self.config.api_key or "")
            raise httpx.HTTPStatusError(
                msg, request=e.request, response=e.response
            ) from None
        except httpx.HTTPError as e:
            msg = sanitize_api_key(str(e), self.config.api_key or "")
            raise RuntimeError(f"LLM API error: {msg}") from None

    async def _generate_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Generate using OpenAI-compatible API."""
        messages = self.format_messages(prompt, system_prompt)

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        response = await self.client.post(self._chat_endpoint, json=payload)
        response.raise_for_status()

        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        return LLMResponse(
            content=message.get("content", ""),
            model=data.get("model", self.config.model),
            provider=self.config.provider,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            finish_reason=choice.get("finish_reason"),
            raw_response=data,
        )

    async def _generate_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Generate using Anthropic API."""
        messages = [{"role": "user", "content": prompt}]

        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
        }

        if system_prompt:
            payload["system"] = system_prompt

        response = await self.client.post(self._chat_endpoint, json=payload)
        response.raise_for_status()

        data = response.json()
        content = data.get("content", [{}])
        text_content = next(
            (c.get("text", "") for c in content if c.get("type") == "text"),
            ""
        )
        usage = data.get("usage", {})

        return LLMResponse(
            content=text_content,
            model=data.get("model", self.config.model),
            provider=LLMProvider.ANTHROPIC,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            total_tokens=(
                (usage.get("input_tokens") or 0) +
                (usage.get("output_tokens") or 0)
            ) or None,
            finish_reason=data.get("stop_reason"),
            raw_response=data,
        )

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the API.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.

        Yields:
            Response content chunks.
        """
        if self.config.provider == LLMProvider.ANTHROPIC:
            async for chunk in self._stream_anthropic(prompt, system_prompt):
                yield chunk
        else:
            async for chunk in self._stream_openai(prompt, system_prompt):
                yield chunk

    async def _stream_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Stream using OpenAI-compatible API."""
        messages = self.format_messages(prompt, system_prompt)

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        async with self.client.stream("POST", self._chat_endpoint, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta:
                        yield delta["content"]

    async def _stream_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Stream using Anthropic API."""
        messages = [{"role": "user", "content": prompt}]

        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        if system_prompt:
            payload["system"] = system_prompt

        async with self.client.stream("POST", self._chat_endpoint, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    event_type = data.get("type")
                    if event_type == "content_block_delta":
                        delta = data.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")

    async def list_models(self) -> list[str]:
        """List available models.

        Returns:
            List of model names.
        """
        # For API providers, return the known models
        provider_config = self.PROVIDER_CONFIGS.get(self.config.provider, {})
        return provider_config.get("models", [])

    async def is_available(self) -> bool:
        """Check if the API is available.

        Returns:
            True if API is reachable, False otherwise.
        """
        try:
            # Try a simple models list request
            if self.config.provider == LLMProvider.OPENAI:
                response = await self.client.get("/models")
            else:
                # For Anthropic, we can't easily check without making a request
                # Just check if we have an API key
                return bool(self.config.api_key)
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False


def create_openai_connector(
    api_key: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
) -> APIConnector:
    """Create an OpenAI connector.

    Args:
        api_key: OpenAI API key.
        model: Model to use.
        temperature: Generation temperature.

    Returns:
        Configured APIConnector.
    """
    config = LLMConfig(
        provider=LLMProvider.OPENAI,
        model=model,
        api_key=api_key,
        temperature=temperature,
    )
    return APIConnector(config)


def create_anthropic_connector(
    api_key: str,
    model: str = "claude-3-5-haiku-20241022",
    temperature: float = 0.3,
) -> APIConnector:
    """Create an Anthropic connector.

    Args:
        api_key: Anthropic API key.
        model: Model to use.
        temperature: Generation temperature.

    Returns:
        Configured APIConnector.
    """
    config = LLMConfig(
        provider=LLMProvider.ANTHROPIC,
        model=model,
        api_key=api_key,
        temperature=temperature,
    )
    return APIConnector(config)
