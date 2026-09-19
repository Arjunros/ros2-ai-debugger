"""Action collection."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import DiagnosticCollector, RosBackend, full_name
from ros2_ai_debugger.collectors.nodes import visible_nodes
from ros2_ai_debugger.models import ActionInfo


class ActionCollector(DiagnosticCollector):
    name, field = "actions", "actions"

    def __init__(self, backend: RosBackend) -> None:
        self._backend = backend

    def collect(self) -> list[ActionInfo]:
        servers: dict[str, list[str]] = {}
        clients: dict[str, list[str]] = {}
        types: dict[str, set[str]] = {}
        for name, ns in visible_nodes(self._backend):
            ep = self._backend.node_endpoints(name, ns)
            node = full_name(name, ns)
            for action, t in ep.action_servers:
                servers.setdefault(action, []).append(node)
                types.setdefault(action, set()).update(t)
            for action, t in ep.action_clients:
                clients.setdefault(action, []).append(node)
                types.setdefault(action, set()).update(t)
        for action, t in self._backend.action_names_and_types():
            types.setdefault(action, set()).update(t)
        return [
            ActionInfo(
                name=a,
                types=sorted(types[a]),
                servers=sorted(servers.get(a, [])),
                clients=sorted(clients.get(a, [])),
            )
            for a in sorted(types)
        ]
