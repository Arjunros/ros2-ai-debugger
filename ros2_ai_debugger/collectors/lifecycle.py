"""Lifecycle node state (read-only ``get_state`` service calls)."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import (
    LIFECYCLE_GET_STATE_TYPE,
    DiagnosticCollector,
    RosBackend,
    full_name,
)
from ros2_ai_debugger.collectors.nodes import visible_nodes
from ros2_ai_debugger.models import LifecycleInfo


class LifecycleCollector(DiagnosticCollector):
    name, field = "lifecycle", "lifecycle"

    def __init__(self, backend: RosBackend) -> None:
        self._backend = backend

    def collect(self) -> list[LifecycleInfo]:
        out = []
        for name, ns in visible_nodes(self._backend):
            node = full_name(name, ns)
            services = self._backend.node_endpoints(name, ns).services
            is_lifecycle = any(
                svc == f"{node}/get_state" and LIFECYCLE_GET_STATE_TYPE in types
                for svc, types in services
            )
            if not is_lifecycle:
                continue
            state = self._backend.lifecycle_state(node)
            if state is not None:
                out.append(LifecycleInfo(node, state))
        return out
