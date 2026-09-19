"""Service collection."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import (
    DiagnosticCollector,
    RosBackend,
    full_name,
    is_hidden,
)
from ros2_ai_debugger.collectors.nodes import visible_nodes
from ros2_ai_debugger.models import ServiceInfo


class ServiceCollector(DiagnosticCollector):
    """Lists services and which nodes provide them.

    Per-node parameter services (``rcl_interfaces/srv/*``) are omitted by
    default: every node has them and they only add noise.
    """

    name, field = "services", "services"

    def __init__(self, backend: RosBackend, include_parameter_services: bool = False) -> None:
        self._backend = backend
        self._include_params = include_parameter_services

    def collect(self) -> list[ServiceInfo]:
        providers: dict[str, list[str]] = {}
        for name, ns in visible_nodes(self._backend):
            for svc, _ in self._backend.node_endpoints(name, ns).services:
                providers.setdefault(svc, []).append(full_name(name, ns))
        out = []
        for name, types in sorted(self._backend.service_names_and_types()):
            if is_hidden(name):
                continue
            if not self._include_params and all(t.startswith("rcl_interfaces/srv/") for t in types):
                continue
            out.append(
                ServiceInfo(name=name, types=sorted(types), providers=sorted(providers.get(name, [])))
            )
        return out
