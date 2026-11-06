from __future__ import annotations

import httpx

from eh_poem_style.config import ModelProfile


class LLMError(Exception):
    """模型调用失败。"""


class OpenAICompatClient:
    def __init__(
        self,
        profile: ModelProfile,
        transport: httpx.BaseTransport | None = None,
    ):
        self.profile = profile
        self._client = httpx.Client(transport=transport, timeout=profile.timeout)

    def complete(self, messages: list[dict], **opts) -> str:
        payload = {
            "model": self.profile.model,
            "messages": messages,
            "temperature": opts.pop("temperature", self.profile.temperature),
            "max_tokens": opts.pop("max_tokens", self.profile.max_tokens),
        }
        payload.update(opts)
        try:
            response = self._client.post(
                f"{self.profile.base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.profile.api_key}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.profile.name} 请求失败：{exc}") from exc

        if response.status_code >= 400:
            raise LLMError(
                f"{self.profile.name} HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.profile.name} 响应缺少 content") from exc
        if not isinstance(content, str) or not content.strip():
            reasoning = ""
            try:
                reasoning = data["choices"][0]["message"].get("reasoning_content") or ""
            except (KeyError, IndexError, TypeError):
                pass
            if reasoning.strip():
                return reasoning.strip()
            raise LLMError(f"{self.profile.name} 返回空内容")
        return content.strip()

    def close(self) -> None:
        self._client.close()
