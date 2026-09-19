"""ros2_control controllers, when a controller manager is present."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import (
    LIST_CONTROLLERS_TYPE,
    DiagnosticCollector,
    RosBackend,
)
from ros2_ai_debugger.models import ControllersInfo


class ControllerCollector(DiagnosticCollector):
    """Returns ``None`` when no controller manager exists (not an error)."""

    name, field = "controllers", "controllers"

    def __init__(self, backend: RosBackend) -> None:
        self._backend = backend

    def collect(self) -> ControllersInfo | None:
        for svc, types in sorted(self._backend.service_names_and_types()):
            if LIST_CONTROLLERS_TYPE in types and svc.endswith("/list_controllers"):
                manager = svc.rsplit("/", 1)[0] or "/"
                controllers = self._backend.list_controllers(manager)
                if controllers is not None:
                    return ControllersInfo(manager, sorted(controllers, key=lambda c: c.name))
        return None
