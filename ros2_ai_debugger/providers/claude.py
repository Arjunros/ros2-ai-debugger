"""Anthropic Claude provider (official ``anthropic`` SDK)."""
from __future__ import annotations

import os
from typing import Any, Callable

from ros2_ai_debugger.providers.base import AIProvider, ProviderError


class ClaudeProvider(AIProvider):
    name = "claude"
    default_model = "claude-sonnet-5"
    api_key_env = "ANTHROPIC_API_KEY"

    def __init__(self, model: str | None = None, timeout: float = 120.0,
                 client_factory: Callable[[str], Any] | None = None) -> None:
        super().__init__(model or os.environ.get("ANTHROPIC_MODEL"))
        self._timeout = timeout
        self._client_factory = client_factory

    def is_configured(self) -> bool:
        return bool(os.environ.get(self.api_key_env))

    def config_help(self) -> str:
        return f"set {self.api_key_env} and `pip install 'ros2-ai-debugger[claude]'`"

    def _client(self):
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ProviderError(f"{self.api_key_env} is not set")
        if self._client_factory:
            return self._client_factory(key)
        try:
            import anthropic
        except ImportError:
            raise ProviderError(
                "the 'anthropic' package is not installed: pip install 'ros2-ai-debugger[claude]'"
            ) from None
        return anthropic.Anthropic(api_key=key, timeout=self._timeout)

    def complete(self, system: str, user: str) -> str:
        client = self._client()
        try:
            msg = client.messages.create(
                model=self.model, max_tokens=4096, system=system,
                messages=[{"role": "user", "content": user}])
        except Exception as exc:  # noqa: BLE001 - SDK raises many types; never leak headers
            raise ProviderError(f"Claude API call failed: {type(exc).__name__}: {exc}") from None
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
