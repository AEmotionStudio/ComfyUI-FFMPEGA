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
    timeout: float = 30.0
    extra_options: dict = field(default_factory=dict)


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
        pass

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
        pass

    @abstractmethod
    async def list_models(self) -> list[str]:
        """List available models.

        Returns:
            List of model names.
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the LLM service is available.

        Returns:
            True if available, False otherwise.
        """
        pass

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
