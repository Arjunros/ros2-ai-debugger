"""/diagnostics messages (latest status per name)."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import DiagnosticCollector, RosBackend
from ros2_ai_debugger.models import DiagnosticMessage


class DiagnosticsCollector(DiagnosticCollector):
    name, field = "diagnostics", "diagnostics"

    def __init__(self, backend: RosBackend) -> None:
        self._backend = backend

    def collect(self) -> list[DiagnosticMessage]:
        latest: dict[str, DiagnosticMessage] = {}
        for msg in self._backend.diagnostics():
            latest[msg.name] = msg
        return [latest[k] for k in sorted(latest)]
