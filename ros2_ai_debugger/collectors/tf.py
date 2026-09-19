"""TF collection: edges seen on /tf and /tf_static during the listen window."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import DiagnosticCollector, RosBackend
from ros2_ai_debugger.models import TFEdge, TFInfo


class TFCollector(DiagnosticCollector):
    name, field = "tf", "tf"

    def __init__(self, backend: RosBackend) -> None:
        self._backend = backend

    def collect(self) -> TFInfo:
        seen: dict[tuple[str, str], TFEdge] = {}
        for e in self._backend.tf_edges():
            child, parent = e.child.lstrip("/"), e.parent.lstrip("/")
            key = (child, parent)
            # A static edge wins if the same edge is also seen as dynamic.
            if key not in seen or e.is_static:
                seen[key] = TFEdge(child, parent, e.is_static)
        return TFInfo(
            listen_seconds=self._backend.tf_listen_seconds(),
            edges=sorted(seen.values(), key=lambda e: (e.parent, e.child)),
        )
