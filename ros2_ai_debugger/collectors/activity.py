"""Opt-in message counting for topics the user names (never reads payloads)."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import DiagnosticCollector, RosBackend
from ros2_ai_debugger.models import TopicActivity


class TopicActivityCollector(DiagnosticCollector):
    """Counts messages on ``topics`` to tell "publisher exists" from "publisher is silent"."""

    name, field = "topic_activity", "topic_activity"

    def __init__(self, backend: RosBackend, topics: list[str]) -> None:
        self._backend = backend
        self._topics = sorted(set(topics))

    def collect(self) -> list[TopicActivity]:
        counts, seconds = self._backend.message_counts(self._topics)
        return [TopicActivity(t, counts[t], seconds) for t in self._topics if t in counts]
