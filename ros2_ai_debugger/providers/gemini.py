"""Google Gemini provider over the REST API; no SDK required."""
from __future__ import annotations

import os

from ros2_ai_debugger.providers._http import HttpPost, post_json
from ros2_ai_debugger.providers.base import AIProvider, ProviderError


class GeminiProvider(AIProvider):
    name = "gemini"
    default_model = "gemini-2.5-flash"
    _KEY_ENVS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")

    def __init__(self, model: str | None = None, timeout: float = 120.0,
                 http_post: HttpPost = post_json) -> None:
        super().__init__(model or os.environ.get("GEMINI_MODEL"))
        self._timeout = timeout
        self._post = http_post

    def _key(self) -> str | None:
        return next((os.environ[k] for k in self._KEY_ENVS if os.environ.get(k)), None)

    def is_configured(self) -> bool:
        return self._key() is not None

    def config_help(self) -> str:
        return "set GEMINI_API_KEY (or GOOGLE_API_KEY)"

    def complete(self, system: str, user: str) -> str:
        key = self._key()
        if not key:
            raise ProviderError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        data = self._post(
            url,
            {"systemInstruction": {"parts": [{"text": system}]},
             "contents": [{"role": "user", "parts": [{"text": user}]}],
             "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}},
            {"x-goog-api-key": key}, self._timeout)  # header, not URL, so the key is never logged
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise ProviderError("unexpected response shape from Gemini API (blocked or empty?)") from None
