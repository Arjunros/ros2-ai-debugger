"""Ollama provider: local models over HTTP on this machine (no API key)."""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

from ros2_ai_debugger.providers._http import HttpPost, get_json, post_json
from ros2_ai_debugger.providers.base import AIProvider, ProviderError


def normalize_host(raw: str) -> str:
    """Ollama's OLLAMA_HOST may be ``host:port`` without a scheme."""
    raw = raw.strip().rstrip("/")
    return raw if "://" in raw else f"http://{raw}"


def is_loopback_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class OllamaProvider(AIProvider):
    name = "ollama"
    default_model = "llama3.1"

    def __init__(self, model: str | None = None, timeout: float = 300.0,
                 http_post: HttpPost = post_json, require_local: bool = False) -> None:
        super().__init__(model or os.environ.get("OLLAMA_MODEL"))
        self._timeout = timeout
        self._post = http_post
        self.host = normalize_host(os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
        self._require_local = require_local

    @property
    def is_local(self) -> bool:  # type: ignore[override]
        return is_loopback_url(self.host)

    def config_help(self) -> str:
        return "install Ollama, run `ollama serve` and `ollama pull <model>` (OLLAMA_HOST/OLLAMA_MODEL optional)"

    def describe(self) -> str:
        where = "local" if self.is_local else f"REMOTE {self.host}"
        return f"ollama (model: {self.model}, {where})"

    def installed_models(self) -> list[str]:
        data = get_json(f"{self.host}/api/tags", 3.0)
        return [m.get("name", "") for m in data.get("models", [])]

    def complete(self, system: str, user: str) -> str:
        if self._require_local and not self.is_local:
            raise ProviderError(
                f"--local requires a loopback Ollama host, but OLLAMA_HOST points to {self.host}")
        # Ollama silently truncates prompts longer than num_ctx (default 2-4k tokens),
        # which would drop the system prompt. Size the window to the input (~3 chars/token).
        num_ctx = min(32768, max(4096, (len(system) + len(user)) // 3 + 2048))
        data = self._post(
            f"{self.host}/api/chat",
            {"model": self.model, "stream": False, "format": "json",
             "options": {"temperature": 0, "num_ctx": num_ctx},
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            {}, self._timeout)
        try:
            return data["message"]["content"]
        except (KeyError, TypeError):
            raise ProviderError(f"unexpected response from Ollama: {str(data)[:200]}") from None
