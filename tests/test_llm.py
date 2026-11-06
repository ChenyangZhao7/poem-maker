import json

import httpx
import pytest

from eh_poem_style.config import ModelProfile
from eh_poem_style.llm import LLMError, OpenAICompatClient


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
