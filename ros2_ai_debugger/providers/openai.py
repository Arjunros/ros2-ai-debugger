"""OpenAI (and OpenAI-compatible) provider over the REST API; no SDK required."""
from __future__ import annotations

import os

from ros2_ai_debugger.providers._http import HttpPost, post_json
from ros2_ai_debugger.providers.base import AIProvider, ProviderError


class OpenAIProvider(AIProvider):
    name = "openai"
    default_model = "gpt-4o-mini"
    api_key_env = "OPENAI_API_KEY"

    def __init__(self, model: str | None = None, timeout: float = 120.0,
                 http_post: HttpPost = post_json) -> None:
        super().__init__(model or os.environ.get("OPENAI_MODEL"))
        self._timeout = timeout
        self._post = http_post
        self._base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def is_configured(self) -> bool:
        return bool(os.environ.get(self.api_key_env))

    def config_help(self) -> str:
        return f"set {self.api_key_env} (optionally OPENAI_BASE_URL / OPENAI_MODEL)"

    def complete(self, system: str, user: str) -> str:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ProviderError(f"{self.api_key_env} is not set")
        if not self._base.startswith(("https://", "http://")):
            raise ProviderError("OPENAI_BASE_URL must start with http:// or https://")
        data = self._post(
            f"{self._base}/chat/completions",
            {"model": self.model, "temperature": 0,
             "response_format": {"type": "json_object"},
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            {"Authorization": f"Bearer {key}"}, self._timeout)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("unexpected response shape from OpenAI API") from None
