from __future__ import annotations

import httpx

from eh_poem_style.config import ModelProfile


class LLMError(Exception):
    """模型调用失败。"""


_OLLAMA_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "genre": {"type": "string"},
        "cipai": {"type": ["string", "null"]},
        "lines": {"type": "array", "items": {"type": "string"}},
        "rhyme": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "genre", "lines"],
}


class OpenAICompatClient:
    def __init__(
        self,
        profile: ModelProfile,
        transport: httpx.BaseTransport | None = None,
    ):
        self.profile = profile
        self._client = httpx.Client(transport=transport, timeout=profile.timeout)

    def _post(self, payload: dict):
        try:
            return self._client.post(
                f"{self.profile.base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.profile.api_key}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.profile.name} 请求失败：{exc}") from exc

    def complete(self, messages: list[dict], **opts) -> str:
        payload = {
            "model": self.profile.model,
            "messages": messages,
            "temperature": opts.pop("temperature", self.profile.temperature),
            "max_tokens": opts.pop("max_tokens", self.profile.max_tokens),
        }
        payload.update(self.profile.extra)
        payload.update(opts)
        response = self._post(payload)
        if response.status_code >= 400 and "response_format" in payload:
            payload.pop("response_format", None)
            response = self._post(payload)
        if response.status_code >= 400:
            raise LLMError(
                f"{self.profile.name} HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

        content = self._extract(response)
        if content is None and "response_format" in payload:
            payload.pop("response_format", None)
            retry = self._post(payload)
            if retry.status_code < 400:
                content = self._extract(retry)
        if content is None:
            raise LLMError(f"{self.profile.name} 返回空内容或缺少 content")
        return content

    def _extract(self, response: httpx.Response) -> str | None:
        try:
            data = response.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            return None
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning.strip()
        return None

    def close(self) -> None:
        self._client.close()


class OllamaClient:
    """Ollama 原生 /api/chat；用 think=false + JSON schema 避免 4B 模型把预算花在思考上。"""

    def __init__(
        self,
        profile: ModelProfile,
        transport: httpx.BaseTransport | None = None,
    ):
        self.profile = profile
        self._client = httpx.Client(transport=transport, timeout=profile.timeout)

    def complete(self, messages: list[dict], **opts) -> str:
        base = self.profile.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        payload = {
            "model": self.profile.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "format": _OLLAMA_SCHEMA,
            "options": {
                "temperature": opts.pop("temperature", self.profile.temperature),
                "num_predict": opts.pop("max_tokens", self.profile.max_tokens),
            },
        }
        payload.update(self.profile.extra)
        try:
            response = self._client.post(f"{base}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.profile.name} 请求失败：{exc}") from exc
        if response.status_code >= 400:
            raise LLMError(
                f"{self.profile.name} HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError(f"{self.profile.name} 响应缺少 content") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError(f"{self.profile.name} 返回空内容")
        return content.strip()

    def close(self) -> None:
        self._client.close()

