import json

import httpx
import pytest

from eh_poem_style.config import ModelProfile
from eh_poem_style.llm import LLMError, OllamaClient, OpenAICompatClient


def profile():
    return ModelProfile("x", "https://api.example/v1", "k", "m", timeout=5)


def test_client_posts_chat_completions():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    client = OpenAICompatClient(profile(), transport=httpx.MockTransport(handler))
    assert client.complete([{"role": "user", "content": "hi"}]) == "ok"
    assert seen["url"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "m"
    assert seen["body"]["messages"][0]["content"] == "hi"


def test_client_passes_response_format():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "{}"}}]}
        )

    client = OpenAICompatClient(profile(), transport=httpx.MockTransport(handler))
    client.complete([], response_format={"type": "json_object"})
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_profile_extra_is_merged():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    profile_with_extra = ModelProfile(
        "x", "https://api.example/v1", "k", "m", timeout=5, extra={"think": False}
    )
    client = OpenAICompatClient(
        profile_with_extra, transport=httpx.MockTransport(handler)
    )
    client.complete([])
    assert seen["body"]["think"] is False


def test_ollama_client_uses_native_chat_and_schema():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"message": {"content": '{"title":"t","genre":"七绝","lines":[]}'}}
        )

    profile_ollama = ModelProfile(
        "local",
        "http://127.0.0.1:11434/v1",
        "local",
        "qwen3.5:4b",
        timeout=5,
        backend="ollama",
    )
    client = OllamaClient(
        profile_ollama, transport=httpx.MockTransport(handler)
    )
    assert client.complete([]).startswith("{")
    assert seen["url"].endswith("/api/chat")
    assert seen["body"]["think"] is False
    assert isinstance(seen["body"]["format"], dict)


def test_retries_without_response_format_when_empty():
    bodies = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = OpenAICompatClient(profile(), transport=httpx.MockTransport(handler))
    assert client.complete([], response_format={"type": "json_object"}) == "ok"
    assert "response_format" in bodies[0]
    assert "response_format" not in bodies[1]


def test_non_2xx_raises():
    def handler(request: httpx.Request):
        return httpx.Response(500, text="boom")

    client = OpenAICompatClient(profile(), transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError):
        client.complete([])


def test_missing_content_raises():
    def handler(request: httpx.Request):
        return httpx.Response(200, json={"choices": []})

    client = OpenAICompatClient(profile(), transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError):
        client.complete([])
