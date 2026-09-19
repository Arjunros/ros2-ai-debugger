"""AI providers. The core tool works without any of them."""
from __future__ import annotations

from ros2_ai_debugger.providers.base import AIProvider, ProviderError
from ros2_ai_debugger.providers.claude import ClaudeProvider
from ros2_ai_debugger.providers.gemini import GeminiProvider
from ros2_ai_debugger.providers.ollama import OllamaProvider
from ros2_ai_debugger.providers.openai import OpenAIProvider

PROVIDERS: dict[str, type[AIProvider]] = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}


def get_provider(name: str, model: str | None = None, **kwargs) -> AIProvider:
    try:
        cls = PROVIDERS[name]
    except KeyError:
        raise ProviderError(f"unknown provider {name!r}; choose from {sorted(PROVIDERS)}") from None
    return cls(model=model, **kwargs)


__all__ = ["AIProvider", "ProviderError", "PROVIDERS", "get_provider", "ClaudeProvider",
           "OpenAIProvider", "GeminiProvider", "OllamaProvider"]
