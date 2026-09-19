"""Node collection."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import (
    DiagnosticCollector,
    RosBackend,
    full_name,
    is_hidden,
)
from ros2_ai_debugger.models import NodeInfo

#: The tool's own node; never reported as part of the user's system.
SELF_NODE_NAME = "ros2_ai_debugger"


def visible_nodes(backend: RosBackend) -> list[tuple[str, str]]:
    """(name, namespace) of user nodes: hides ``_``-prefixed nodes and ourselves."""
    return sorted(
        {
            (n, ns)
            for n, ns in backend.node_names_and_namespaces()
            if not n.startswith("_") and n != SELF_NODE_NAME
        }
    )


def _names(pairs, *, hidden: bool = False) -> list[str]:
    return sorted({n for n, _ in pairs if hidden or not is_hidden(n)})


class NodeCollector(DiagnosticCollector):
    name, field = "nodes", "nodes"

    def __init__(self, backend: RosBackend) -> None:
        self._backend = backend

    def collect(self) -> list[NodeInfo]:
        nodes = []
        for name, ns in visible_nodes(self._backend):
            ep = self._backend.node_endpoints(name, ns)
            nodes.append(
                NodeInfo(
                    name=full_name(name, ns),
                    publishes=_names(ep.publishers),
                    subscribes=_names(ep.subscribers),
                    services=_names(ep.services),
                    clients=_names(ep.clients),
                    action_servers=_names(ep.action_servers),
                    action_clients=_names(ep.action_clients),
                )
            )
        return nodes
