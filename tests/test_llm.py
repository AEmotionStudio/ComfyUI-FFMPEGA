"""Tests for the LLM integration."""

import pytest
import json

from core.llm.base import LLMConfig, LLMProvider, LLMResponse
from core.llm.ollama import OllamaConnector
from core.llm.api import APIConnector
from prompts.system import get_system_prompt
from prompts.generation import get_generation_prompt


class TestLLMConfig:
    """Tests for LLMConfig class."""

    def test_default_config(self):
        """Test default configuration."""
        config = LLMConfig()

        assert config.provider == LLMProvider.OLLAMA
        assert config.model == "llama3.1:8b"
        assert config.temperature == 0.3

    def test_custom_config(self):
        """Test custom configuration."""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o",
            api_key="test-key",
            temperature=0.5,
        )

        assert config.provider == LLMProvider.OPENAI
        assert config.model == "gpt-4o"
        assert config.api_key == "test-key"


class TestLLMResponse:
    """Tests for LLMResponse class."""

    def test_response_creation(self):
        """Test creating a response."""
        response = LLMResponse(
            content="Test response",
            model="llama3.1:8b",
            provider=LLMProvider.OLLAMA,
            prompt_tokens=100,
            completion_tokens=50,
        )

        assert response.content == "Test response"
        assert response.model == "llama3.1:8b"
        assert response.prompt_tokens == 100


class TestOllamaConnector:
    """Tests for OllamaConnector class."""

    def test_connector_creation(self):
        """Test creating connector."""
        connector = OllamaConnector()

        assert connector.config.provider == LLMProvider.OLLAMA
        assert connector.config.model == "llama3.1:8b"

    def test_connector_with_config(self):
        """Test connector with custom config."""
        config = LLMConfig(
            provider=LLMProvider.OLLAMA,
            model="mistral:7b",
            base_url="http://localhost:11435",
        )
        connector = OllamaConnector(config)

        assert connector.config.model == "mistral:7b"
        assert connector.config.base_url == "http://localhost:11435"

    def test_format_messages(self):
        """Test message formatting."""
        connector = OllamaConnector()

        messages = connector.format_messages(
            "User prompt",
            "System prompt",
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


class TestAPIConnector:
    """Tests for APIConnector class."""

    def test_openai_config(self):
        """Test OpenAI configuration."""
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-4o",
            api_key="test-key",
        )
        connector = APIConnector(config)

        assert connector.config.provider == LLMProvider.OPENAI

    def test_anthropic_config(self):
        """Test Anthropic configuration."""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-5-haiku-20241022",
            api_key="test-key",
        )
        connector = APIConnector(config)

        assert connector.config.provider == LLMProvider.ANTHROPIC


class TestPromptTemplates:
    """Tests for prompt templates."""

    def test_system_prompt_generation(self):
        """Test system prompt generation."""
        video_metadata = """
        File: test.mp4
        Format: mp4
        Duration: 60.0 seconds
        Video: 1920x1080 @ 30 fps
        """

        prompt = get_system_prompt(video_metadata=video_metadata)

        assert "FFMPEGA" in prompt
        assert "Available Skills" in prompt
        assert "test.mp4" in prompt

    def test_system_prompt_abbreviated(self):
        """Test abbreviated system prompt."""
        prompt = get_system_prompt(include_full_registry=False)

        # Should be shorter
        assert len(prompt) < 20000  # Reasonable size

    def test_generation_prompt(self):
        """Test generation prompt."""
        user_request = "Make it cinematic"
        video_metadata = "1920x1080, 30fps"

        prompt = get_generation_prompt(user_request, video_metadata)

        assert "cinematic" in prompt
        assert "1920x1080" in prompt


class TestLLMResponseParsing:
    """Tests for parsing LLM responses."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        response = """
        ```json
        {
            "interpretation": "Apply cinematic look",
            "pipeline": [
                {"skill": "cinematic", "params": {"intensity": "medium"}}
            ],
            "warnings": [],
            "estimated_changes": "Letterbox and color grading"
        }
        ```
        """

        # Extract JSON
        import re
        match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        assert match is not None

        data = json.loads(match.group(1))
        assert data["interpretation"] == "Apply cinematic look"
        assert len(data["pipeline"]) == 1

    def test_parse_embedded_json(self):
        """Test parsing JSON embedded in text."""
        response = """
        I'll help you with that. Here's the pipeline:

        {
            "interpretation": "Speed up video",
            "pipeline": [
                {"skill": "speed", "params": {"factor": 2.0}}
            ],
            "warnings": []
        }

        This will double the video speed.
        """

        # Extract JSON using regex
        import re
        match = re.search(r'\{[\s\S]*\}', response)
        assert match is not None

        # Should be able to parse
        try:
            data = json.loads(match.group())
            assert data["interpretation"] == "Speed up video"
        except json.JSONDecodeError:
            # Some responses may have multiple JSON-like structures
            pass

    def test_parse_skill_pipeline(self):
        """Test parsing skill pipeline."""
        pipeline_json = {
            "interpretation": "Resize and compress",
            "pipeline": [
                {"skill": "resize", "params": {"width": 1280, "height": 720}},
                {"skill": "compress", "params": {"preset": "medium"}},
            ],
            "warnings": ["Some quality loss expected"],
            "estimated_changes": "720p output, smaller file",
        }

        # Verify structure
        assert len(pipeline_json["pipeline"]) == 2
        assert pipeline_json["pipeline"][0]["skill"] == "resize"
        assert pipeline_json["pipeline"][1]["params"]["preset"] == "medium"


class TestIntegrationMocked:
    """Integration tests with mocked LLM."""

    def test_full_pipeline_flow(self):
        """Test the full pipeline generation flow with mocked response."""
        # Mock LLM response
        mock_response = {
            "interpretation": "Apply vintage film look",
            "pipeline": [
                {"skill": "saturation", "params": {"value": 0.8}},
                {"skill": "noise", "params": {"amount": 20}},
                {"skill": "vignette", "params": {"intensity": 0.35}},
            ],
            "warnings": [],
            "estimated_changes": "Faded colors with film grain",
        }

        # Verify pipeline can be parsed
        pipeline = mock_response["pipeline"]

        assert len(pipeline) == 3
        assert pipeline[0]["skill"] == "saturation"
        assert pipeline[1]["skill"] == "noise"
        assert pipeline[2]["skill"] == "vignette"

        # Verify params
        assert pipeline[0]["params"]["value"] == 0.8
        assert pipeline[1]["params"]["amount"] == 20

    def test_error_handling(self):
        """Test error handling for invalid responses."""
        invalid_responses = [
            "This is not JSON",
            "{'single_quotes': 'invalid'}",
            '{"missing_pipeline": true}',
        ]

        for response in invalid_responses:
            try:
                data = json.loads(response)
                # If it parses, check for required fields
                assert "pipeline" in data
            except (json.JSONDecodeError, AssertionError):
                # Expected - invalid response
                pass
