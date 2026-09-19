"""The provider-independent AI interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ros2_ai_debugger.analyzers.ai_prompt import SYSTEM_PROMPT, build_payload, build_user_prompt
from ros2_ai_debugger.analyzers.ai_validation import AIResult, validate_ai_response
from ros2_ai_debugger.models import Finding, SystemSnapshot


class ProviderError(RuntimeError):
    """Configuration, network or API failure. Messages never contain credentials."""


class AIProvider(ABC):
    """Contract for an AI backend.

    Subclasses implement only :meth:`complete` (prompt in, text out). Prompt
    construction and response validation are shared, so every provider gets
    identical grounding and safety checks.
    """

    name: str = ""
    #: True only if data never leaves this machine.
    is_local: bool = False
    default_model: str = ""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or self.default_model

    def is_configured(self) -> bool:
        return True

    def config_help(self) -> str:
        return ""

    def describe(self) -> str:
        return f"{self.name} (model: {self.model})"

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Send one prompt and return the raw text of the reply."""

    def analyze(self, snapshot: SystemSnapshot, rule_findings: list[Finding] | None = None) -> AIResult:
        payload = build_payload(snapshot, rule_findings or [])
        text = self.complete(SYSTEM_PROMPT, build_user_prompt(payload))
        return validate_ai_response(text, snapshot, source=f"ai:{self.name}")
