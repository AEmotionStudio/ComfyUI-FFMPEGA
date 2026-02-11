"""Base classes for LLM integration."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, AsyncIterator


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    QWEN = "qwen"
    GEMINI_CLI = "gemini_cli"
    CLAUDE_CLI = "claude_cli"
    CURSOR_AGENT = "cursor_agent"
    QWEN_CLI = "qwen_cli"
    CUSTOM = "custom"


@dataclass
class LLMConfig:
    """Configuration for LLM connection."""
    provider: LLMProvider = LLMProvider.OLLAMA
    model: str = "llama3.1:8b"
    base_url: str = "http://localhost:11434"
    api_key: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: float = 300.0
    extra_options: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        """Redact api_key in string representation."""
        key_display = ""
        if self.api_key:
            visible = self.api_key[-4:] if len(self.api_key) > 4 else "****"
            key_display = f"****{visible}"
        return (
            f"LLMConfig(provider={self.provider!r}, model={self.model!r}, "
            f"base_url={self.base_url!r}, api_key={key_display!r}, "
            f"temperature={self.temperature}, max_tokens={self.max_tokens})"
        )


@dataclass
class LLMResponse:
    """Response from an LLM."""
    content: str
    model: str
    provider: LLMProvider
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    finish_reason: Optional[str] = None
    raw_response: Optional[dict] = None
    tool_calls: Optional[list[dict]] = None


class LLMConnector(ABC):
    """Abstract base class for LLM connectors."""

    def __init__(self, config: LLMConfig):
        """Initialize connector with configuration.

        Args:
            config: LLM configuration.
        """
        self.config = config

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.

        Returns:
            LLMResponse with generated content.
        """
        ...

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the LLM.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.

        Yields:
            Response content chunks.
        """
        ...

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> LLMResponse:
        """Chat with tool/function-calling support.

        Models that support tool calling can request tool invocations.
        The response will contain tool_calls if the model wants to call tools,
        or content if it's providing a final answer.

        Args:
            messages: Conversation history (role/content dicts).
            tools: Tool definitions in OpenAI-compatible format.

        Returns:
            LLMResponse with content and/or tool_calls.

        Raises:
            NotImplementedError: If the provider doesn't support tool calling.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support tool calling"
        )

    @abstractmethod
    async def list_models(self) -> list[str]:
        """List available models.

        Returns:
            List of model names.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the LLM service is available.

        Returns:
            True if available, False otherwise.
        """
        ...

    def format_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> list[dict]:
        """Format prompt into message list.

        Args:
            prompt: User prompt.
            system_prompt: Optional system prompt.

        Returns:
            List of message dictionaries.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages
