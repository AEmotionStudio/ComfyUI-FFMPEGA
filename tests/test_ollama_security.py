import pytest
import httpx
from core.llm.ollama import create_ollama_connector
from core.llm.base import LLMConfig, LLMProvider
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_ollama_error_leakage():
    # Setup configuration with a fake API key
    api_key = "sk_test_SECRET_KEY_12345"
    config = LLMConfig(
        provider=LLMProvider.OLLAMA,
        model="llama3.1:8b",
        base_url="http://localhost:11434",
        api_key=api_key,
    )
    connector = create_ollama_connector(model="llama3.1:8b", base_url="http://localhost:11434")
    connector.config = config

    # Mock the response to simulate an error containing the sensitive header
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.request = MagicMock(spec=httpx.Request)
    mock_response.request.headers = {"Authorization": f"Bearer {api_key}"}
    mock_response.text = "Internal Server Error"

    # Let's force the error message to contain the key to prove sanitization works
    error_with_key = httpx.HTTPStatusError(
        f"500 Internal Server Error with key {api_key}",
        request=mock_response.request,
        response=mock_response
    )

    # Mock the client's post method to raise the error
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = error_with_key

    # Inject the mock client
    connector._client = mock_client

    # Test generate() leakage
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await connector.generate("test prompt")

    # Check if the API key is LEAKED (should fail if leaked)
    assert api_key not in str(excinfo.value), "API Key LEAKED in generate() error"
    assert "****" in str(excinfo.value), "API Key should be redacted"

@pytest.mark.asyncio
async def test_ollama_stream_error_leakage():
    api_key = "sk_test_SECRET_KEY_12345"
    config = LLMConfig(
        provider=LLMProvider.OLLAMA,
        model="llama3.1:8b",
        base_url="http://localhost:11434",
        api_key=api_key,
    )
    connector = create_ollama_connector()
    connector.config = config

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.request = MagicMock(spec=httpx.Request)
    mock_response.request.headers = {"Authorization": f"Bearer {api_key}"}

    # Simulate error during stream
    error_with_key = httpx.HTTPStatusError(
        f"Stream Error with key {api_key}",
        request=mock_response.request,
        response=mock_response
    )

    # Mock stream context manager
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_stream = AsyncMock()
    mock_stream.__aenter__.return_value = mock_response
    # The code calls raise_for_status() inside the `async with` block
    mock_response.raise_for_status.side_effect = error_with_key

    mock_client.stream.return_value = mock_stream
    connector._client = mock_client

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        async for _ in connector.generate_stream("test"):
            pass

    assert api_key not in str(excinfo.value), "API Key LEAKED in stream error"
    assert "****" in str(excinfo.value), "API Key should be redacted"

@pytest.mark.asyncio
async def test_ollama_auth_header():
    api_key = "sk_test_SECRET_KEY_12345"
    config = LLMConfig(
        provider=LLMProvider.OLLAMA,
        model="llama3.1:8b",
        base_url="http://localhost:11434",
        api_key=api_key,
    )
    connector = create_ollama_connector()
    connector.config = config

    client = connector.client
    assert client.headers["Authorization"] == f"Bearer {api_key}"
