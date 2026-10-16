"""Tests for the OpenAI-compatible connector (LM Studio, Unsloth Studio, llama.cpp, vLLM)."""

import importlib
import json
import os

import httpx
import pytest

from core.llm.base import LLMConfig, LLMProvider
from core.llm.openai_compat import OpenAICompatConnector

API_KEY = "sk-unsloth-SECRET_KEY_12345"


def _connector(handler=None, api_key=None) -> OpenAICompatConnector:
    connector = OpenAICompatConnector(LLMConfig(
        provider=LLMProvider.OPENAI_COMPAT,
        model="qwen/qwen3-8b",
        base_url="http://localhost:1234/v1",
        api_key=api_key,
    ))
    if handler is not None:
        connector._client = httpx.AsyncClient(
            base_url=connector.config.base_url,
            headers=connector.client.headers,
            transport=httpx.MockTransport(handler),
        )
    return connector


def _completion(message: dict) -> dict:
    return {
        "model": "qwen/qwen3-8b",
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_auth_header_only_with_key():
    assert _connector(api_key=API_KEY).client.headers["Authorization"] == f"Bearer {API_KEY}"
    assert "Authorization" not in _connector().client.headers


async def test_generate():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion({"role": "assistant", "content": '{"pipeline": []}'}))

    resp = await _connector(handler).generate("make it blue", "be terse")

    assert seen["url"] == "http://localhost:1234/v1/chat/completions"
    assert seen["body"]["model"] == "qwen/qwen3-8b"
    assert seen["body"]["messages"] == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "make it blue"},
    ]
    assert resp.content == '{"pipeline": []}'
    assert resp.provider == LLMProvider.OPENAI_COMPAT
    assert resp.total_tokens == 15


async def test_chat_with_tools_normalizes_history():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_abc",
                "type": "function",
                "function": {"name": "search_skills", "arguments": '{"query": "blur"}'},
            }],
        }))

    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    history = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "blur the background"},
        # Ollama-style dict arguments and no "type", as the agent loop builds them
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_0", "function": {"name": "extract_frames", "arguments": {"fps": 1}}},
            {"id": "call_1", "function": {"name": "list_luts", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_0", "content": [{"type": "text", "text": '{"paths": []}'}, image]},
        {"role": "tool", "tool_call_id": "call_1", "content": '{"luts": []}'},
    ]
    tools = [{"type": "function", "function": {"name": "search_skills", "parameters": {}}}]

    resp = await _connector(handler).chat_with_tools(history, tools)

    sent = seen["body"]["messages"]
    assert sent[2]["tool_calls"] == [
        {"id": "call_0", "type": "function", "function": {"name": "extract_frames", "arguments": '{"fps": 1}'}},
        {"id": "call_1", "type": "function", "function": {"name": "list_luts", "arguments": "{}"}},
    ]
    # Both tool results directly follow the assistant turn; frames come after them
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool", "tool", "user"]
    assert sent[3]["content"] == '{"paths": []}'
    assert sent[5]["content"][1:] == [image]
    assert seen["body"]["tools"] == tools
    assert history[2]["tool_calls"][0]["function"]["arguments"] == {"fps": 1}

    assert resp.content == ""
    assert resp.tool_calls == [
        {"id": "call_abc", "function": {"name": "search_skills", "arguments": '{"query": "blur"}'}},
    ]


async def test_chat_with_tools_omits_empty_tools():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion({"role": "assistant", "content": "done"}))

    resp = await _connector(handler).chat_with_tools([{"role": "user", "content": "hi"}], [])

    assert "tools" not in seen["body"]
    assert resp.tool_calls is None


async def test_error_keeps_server_reason_and_redacts_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": f"Model does not support images ({API_KEY})"})

    with pytest.raises(RuntimeError) as excinfo:
        await _connector(handler, api_key=API_KEY).generate("hi")

    assert "Model does not support images" in str(excinfo.value)
    assert "400" in str(excinfo.value)
    assert API_KEY not in str(excinfo.value)


async def test_stream_error_keeps_server_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="model 'qwen/qwen3-8b' not found")

    with pytest.raises(RuntimeError, match="not found"):
        async for _ in _connector(handler).generate_stream("hi"):
            pass


async def test_generate_stream():
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        events = [
            {"choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo"}}]},
        ]
        body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    chunks = [c async for c in _connector(handler).generate_stream("hi")]
    assert "".join(chunks) == "Hello"


async def test_list_models_and_availability():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"object": "list", "data": [{"id": "qwen/qwen3-8b"}, {"id": "google/gemma-3-12b"}]})

    connector = _connector(handler)
    assert await connector.list_models() == ["qwen/qwen3-8b", "google/gemma-3-12b"]
    assert await connector.is_available() is True


def test_create_connector_routes_by_url(monkeypatch):
    # Import through the root package so create_connector's relative imports resolve
    pkg = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    PipelineGenerator = importlib.import_module(f"{pkg}.core.pipeline_generator").PipelineGenerator
    monkeypatch.setenv("FFMPEGA_LLM_API_KEY", API_KEY)

    lm_studio = PipelineGenerator.create_connector("qwen/qwen3-8b", "http://localhost:1234/v1/")
    assert type(lm_studio).__name__ == "OpenAICompatConnector"
    assert lm_studio.config.api_key == API_KEY
    assert lm_studio.config.base_url == "http://localhost:1234/v1/"

    ollama = PipelineGenerator.create_connector("qwen3:8b", "http://localhost:11434")
    assert type(ollama).__name__ == "OllamaConnector"
    assert ollama.config.api_key is None
