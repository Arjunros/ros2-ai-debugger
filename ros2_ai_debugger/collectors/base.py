"""Collector interface and the raw ROS backend protocol.

Collectors turn *raw* backend data into the normalized model. Only the
backend (``rclpy_backend``) talks to ROS 2, so collectors are testable with a
fake backend and no robot.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol

from ros2_ai_debugger.models import (
    ControllerInfo,
    DiagnosticMessage,
    EndpointInfo,
    LogEntry,
    TFEdge,
)

NameAndTypes = list[tuple[str, list[str]]]

# The only services the tool ever calls. Both are read-only queries.
LIFECYCLE_GET_STATE_TYPE = "lifecycle_msgs/srv/GetState"
LIST_CONTROLLERS_TYPE = "controller_manager_msgs/srv/ListControllers"


@dataclass
class RawNodeEndpoints:
    publishers: NameAndTypes
    subscribers: NameAndTypes
    services: NameAndTypes
    clients: NameAndTypes
    action_servers: NameAndTypes
    action_clients: NameAndTypes


class RosBackend(Protocol):
    """Read-only view of a ROS 2 graph. Implemented by rclpy and by test fakes."""

    def node_names_and_namespaces(self) -> list[tuple[str, str]]: ...
    def node_endpoints(self, name: str, namespace: str) -> RawNodeEndpoints: ...
    def topic_names_and_types(self) -> NameAndTypes: ...
    def publishers_info(self, topic: str) -> list[EndpointInfo]: ...
    def subscribers_info(self, topic: str) -> list[EndpointInfo]: ...
    def service_names_and_types(self) -> NameAndTypes: ...
    def action_names_and_types(self) -> NameAndTypes: ...
    def tf_edges(self) -> list[TFEdge]: ...
    def tf_listen_seconds(self) -> float: ...
    def diagnostics(self) -> list[DiagnosticMessage]: ...
    def logs(self) -> list[LogEntry]: ...
    def lifecycle_state(self, node: str) -> str | None: ...
    def list_controllers(self, manager: str) -> list[ControllerInfo] | None: ...
    def message_counts(self, topics: list[str]) -> tuple[dict[str, int], float]:
        """Count messages per topic over a window; returns (counts, seconds).

        Topics that cannot be watched (unknown, or no type available) are omitted.
        Payloads must never be deserialized or retained.
        """


class DiagnosticCollector(ABC):
    """One unit of data collection.

    ``field`` is the :class:`SystemSnapshot` attribute the result is stored in.
    """

    name: str = ""
    field: str = ""

    @abstractmethod
    def collect(self) -> Any:
        ...


def full_name(name: str, namespace: str) -> str:
    """Join a node name and namespace into a fully qualified name."""
    return f"/{name}" if namespace in ("", "/") else f"{namespace.rstrip('/')}/{name}"


def is_hidden(name: str) -> bool:
    """ROS convention: any name segment starting with an underscore is hidden."""
    return any(seg.startswith("_") for seg in name.split("/") if seg)
