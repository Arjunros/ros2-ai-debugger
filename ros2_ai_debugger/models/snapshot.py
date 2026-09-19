"""Normalized, provider-independent description of a ROS 2 system."""
from __future__ import annotations

from dataclasses import dataclass, field

from ros2_ai_debugger.models.serialization import from_dict, to_dict

SCHEMA_VERSION = 1


@dataclass
class QoSInfo:
    """Subset of QoS settings used for compatibility checks.

    Values are the upper-case enum names reported by rclpy (``RELIABLE``,
    ``BEST_EFFORT``, ``VOLATILE``, ``TRANSIENT_LOCAL`` ...) or ``UNKNOWN``.
    """

    reliability: str = "UNKNOWN"
    durability: str = "UNKNOWN"
    history: str = "UNKNOWN"
    depth: int = 0


@dataclass
class EndpointInfo:
    """A publisher or subscription on a topic."""

    node_name: str  # fully qualified, e.g. /ns/talker
    topic_type: str = ""
    qos: QoSInfo = field(default_factory=QoSInfo)


@dataclass
class PublisherInfo(EndpointInfo):
    pass


@dataclass
class SubscriberInfo(EndpointInfo):
    pass


@dataclass
class TopicInfo:
    name: str
    types: list[str] = field(default_factory=list)
    publishers: list[PublisherInfo] = field(default_factory=list)
    subscribers: list[SubscriberInfo] = field(default_factory=list)


@dataclass
class NodeInfo:
    name: str  # fully qualified
    publishes: list[str] = field(default_factory=list)
    subscribes: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    clients: list[str] = field(default_factory=list)
    action_servers: list[str] = field(default_factory=list)
    action_clients: list[str] = field(default_factory=list)


@dataclass
class ServiceInfo:
    name: str
    types: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)  # nodes offering it


@dataclass
class ActionInfo:
    name: str
    types: list[str] = field(default_factory=list)
    servers: list[str] = field(default_factory=list)
    clients: list[str] = field(default_factory=list)


@dataclass
class TFEdge:
    child: str
    parent: str
    is_static: bool = False


@dataclass
class TFInfo:
    """Transform edges observed on /tf and /tf_static during the listen window."""

    listen_seconds: float = 0.0
    edges: list[TFEdge] = field(default_factory=list)

    def frames(self) -> list[str]:
        return sorted({e.child for e in self.edges} | {e.parent for e in self.edges})

    def components(self) -> list[list[str]]:
        """Connected groups of frames, largest first (ties broken by name)."""
        parent: dict[str, str] = {f: f for f in self.frames()}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for e in self.edges:
            parent[find(e.child)] = find(e.parent)
        groups: dict[str, list[str]] = {}
        for f in parent:
            groups.setdefault(find(f), []).append(f)
        out = [sorted(g) for g in groups.values()]
        return sorted(out, key=lambda g: (-len(g), g[0]))


@dataclass
class LifecycleInfo:
    node: str
    state: str  # label, e.g. "active", "inactive", "unconfigured"


@dataclass
class ControllerInfo:
    name: str
    type: str = ""
    state: str = ""


@dataclass
class ControllersInfo:
    manager: str
    controllers: list[ControllerInfo] = field(default_factory=list)


@dataclass
class DiagnosticMessage:
    name: str
    level: str  # OK | WARN | ERROR | STALE
    message: str = ""
    hardware_id: str = ""
    values: dict[str, str] = field(default_factory=dict)


@dataclass
class LogEntry:
    level: str  # DEBUG | INFO | WARN | ERROR | FATAL
    logger: str
    message: str
    stamp: float = 0.0


@dataclass
class NetworkInterfaceInfo:
    name: str
    state: str = ""
    ipv4: str = ""
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_errors: int = 0
    tx_errors: int = 0


@dataclass
class SystemResourceInfo:
    cpu_percent: float | None = None
    cpu_count: int = 0
    load_avg: list[float] = field(default_factory=list)
    memory_percent: float | None = None
    memory_total_mb: int | None = None
    disk_percent: float | None = None
    disk_path: str = "/"
    network: list[NetworkInterfaceInfo] = field(default_factory=list)


@dataclass
class EnvironmentInfo:
    ros_distro: str | None = None
    ros_domain_id: str | None = None  # None => variable unset (default 0)
    rmw_implementation: str | None = None
    localhost_only: str | None = None
    os_name: str = ""
    python_version: str = ""
    hostname: str = ""


@dataclass
class SystemSnapshot:
    """Everything the tool observed, at one point in time."""

    collected_at: str = ""
    schema_version: int = SCHEMA_VERSION
    environment: EnvironmentInfo = field(default_factory=EnvironmentInfo)
    nodes: list[NodeInfo] = field(default_factory=list)
    topics: list[TopicInfo] = field(default_factory=list)
    services: list[ServiceInfo] = field(default_factory=list)
    actions: list[ActionInfo] = field(default_factory=list)
    tf: TFInfo | None = None
    lifecycle: list[LifecycleInfo] = field(default_factory=list)
    controllers: ControllersInfo | None = None
    diagnostics: list[DiagnosticMessage] = field(default_factory=list)
    logs: list[LogEntry] = field(default_factory=list)
    system: SystemResourceInfo | None = None
    collection_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return to_dict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SystemSnapshot:
        return from_dict(cls, data)

    # Convenience lookups used by analyzers -------------------------------
    def node_names(self) -> set[str]:
        return {n.name for n in self.nodes}

    def topic(self, name: str) -> TopicInfo | None:
        return next((t for t in self.topics if t.name == name), None)
