"""Recent /rosout log entries."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import DiagnosticCollector, RosBackend
from ros2_ai_debugger.models import LogEntry

LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40, "FATAL": 50}


class LogCollector(DiagnosticCollector):
    """Keeps the newest ``max_entries`` entries at or above ``min_level``."""

    name, field = "logs", "logs"

    def __init__(self, backend: RosBackend, min_level: str = "WARN", max_entries: int = 50) -> None:
        self._backend = backend
        self._min = LEVELS[min_level]
        self._max = max_entries

    def collect(self) -> list[LogEntry]:
        entries = [e for e in self._backend.logs() if LEVELS.get(e.level, 0) >= self._min]
        entries.sort(key=lambda e: e.stamp)
        return entries[-self._max:]
