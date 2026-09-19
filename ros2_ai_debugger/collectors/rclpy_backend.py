"""rclpy implementation of :class:`RosBackend`.

This is the only module that imports rclpy. It is strictly read-only: it
subscribes to /tf, /tf_static, /diagnostics and /rosout, queries the graph,
and calls exactly two query services (lifecycle ``get_state`` and controller
manager ``list_controllers``). It never publishes, sets parameters, or
changes any state.
"""
from __future__ import annotations

import time

from ros2_ai_debugger.collectors.base import NameAndTypes, RawNodeEndpoints
from ros2_ai_debugger.collectors.nodes import SELF_NODE_NAME
from ros2_ai_debugger.models import (
    ControllerInfo,
    DiagnosticMessage,
    EndpointInfo,
    LogEntry,
    QoSInfo,
    TFEdge,
)

_DIAG_LEVELS = {0: "OK", 1: "WARN", 2: "ERROR", 3: "STALE"}
_LOG_LEVELS = {10: "DEBUG", 20: "INFO", 30: "WARN", 40: "ERROR", 50: "FATAL"}


class RosUnavailableError(RuntimeError):
    """rclpy (a sourced ROS 2 environment) is not available."""


def _enum_name(value) -> str:
    return getattr(value, "name", str(value)).upper()


def _level_int(level) -> int:
    # diagnostic_msgs/DiagnosticStatus.level is `bytes` in some distros.
    return level[0] if isinstance(level, (bytes, bytearray)) else int(level)


class RclpyBackend:
    """Context manager owning an rclpy context and a private node."""

    def __init__(self, listen_seconds: float = 2.0, service_timeout: float = 1.5) -> None:
        self._listen = listen_seconds
        self._timeout = service_timeout
        self._tf: list[TFEdge] = []
        self._diag: list[DiagnosticMessage] = []
        self._logs: list[LogEntry] = []

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> RclpyBackend:
        try:
            import rclpy
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RosUnavailableError(
                "rclpy is not importable. Source your ROS 2 setup first, e.g. "
                "`source /opt/ros/<distro>/setup.bash`."
            ) from exc
        self._rclpy = rclpy
        self._context = rclpy.Context()
        rclpy.init(context=self._context)
        self._node = rclpy.create_node(
            SELF_NODE_NAME,
            context=self._context,
            enable_rosout=False,
            start_parameter_services=False,
        )
        from rclpy.executors import SingleThreadedExecutor

        self._executor = SingleThreadedExecutor(context=self._context)
        self._executor.add_node(self._node)
        self._subscribe()
        self._spin(self._listen)
        return self

    def __exit__(self, *exc) -> None:
        self._executor.shutdown()
        self._node.destroy_node()
        self._rclpy.shutdown(context=self._context)

    def _spin(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self._executor.spin_once(timeout_sec=0.05)

    # -- subscriptions -----------------------------------------------------
    def _subscribe(self) -> None:
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

        n = self._node
        volatile = QoSProfile(depth=100)
        latched = QoSProfile(
            depth=100, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        try:
            from tf2_msgs.msg import TFMessage

            n.create_subscription(TFMessage, "/tf", lambda m: self._on_tf(m, False), volatile)
            n.create_subscription(TFMessage, "/tf_static", lambda m: self._on_tf(m, True), latched)
        except ImportError:
            pass
        try:
            from diagnostic_msgs.msg import DiagnosticArray

            n.create_subscription(DiagnosticArray, "/diagnostics", self._on_diag, volatile)
        except ImportError:
            pass
        try:
            from rcl_interfaces.msg import Log

            # rosout is transient_local so we also receive recently emitted entries.
            n.create_subscription(Log, "/rosout", self._on_log, QoSProfile(
                depth=1000, reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL))
        except ImportError:
            pass

    def _on_tf(self, msg, static: bool) -> None:
        for t in msg.transforms:
            self._tf.append(TFEdge(t.child_frame_id, t.header.frame_id, static))

    def _on_diag(self, msg) -> None:
        for s in msg.status:
            self._diag.append(DiagnosticMessage(
                name=s.name,
                level=_DIAG_LEVELS.get(_level_int(s.level), "UNKNOWN"),
                message=s.message,
                hardware_id=s.hardware_id,
                values={kv.key: kv.value for kv in s.values},
            ))

    def _on_log(self, msg) -> None:
        self._logs.append(LogEntry(
            level=_LOG_LEVELS.get(int(msg.level), "INFO"),
            logger=msg.name,
            message=msg.msg,
            stamp=msg.stamp.sec + msg.stamp.nanosec * 1e-9,
        ))

    # -- graph -------------------------------------------------------------
    def node_names_and_namespaces(self) -> list[tuple[str, str]]:
        return list(self._node.get_node_names_and_namespaces())

    def node_endpoints(self, name: str, namespace: str) -> RawNodeEndpoints:
        from rclpy import action

        n = self._node

        def safe(fn, *args) -> NameAndTypes:
            try:
                return [(a, list(b)) for a, b in fn(*args)]
            except Exception:  # node vanished between listing and querying
                return []

        return RawNodeEndpoints(
            publishers=safe(n.get_publisher_names_and_types_by_node, name, namespace),
            subscribers=safe(n.get_subscriber_names_and_types_by_node, name, namespace),
            services=safe(n.get_service_names_and_types_by_node, name, namespace),
            clients=safe(n.get_client_names_and_types_by_node, name, namespace),
            action_servers=safe(action.get_action_server_names_and_types_by_node, n, name, namespace),
            action_clients=safe(action.get_action_client_names_and_types_by_node, n, name, namespace),
        )

    def topic_names_and_types(self) -> NameAndTypes:
        return [(a, list(b)) for a, b in self._node.get_topic_names_and_types()]

    @staticmethod
    def _endpoint(info) -> EndpointInfo:
        ns = info.node_namespace or "/"
        node = f"/{info.node_name}" if ns == "/" else f"{ns.rstrip('/')}/{info.node_name}"
        q = info.qos_profile
        return EndpointInfo(
            node_name=node,
            topic_type=info.topic_type,
            qos=QoSInfo(
                reliability=_enum_name(q.reliability),
                durability=_enum_name(q.durability),
                history=_enum_name(q.history),
                depth=int(q.depth),
            ),
        )

    def publishers_info(self, topic: str) -> list[EndpointInfo]:
        return [self._endpoint(i) for i in self._node.get_publishers_info_by_topic(topic)]

    def subscribers_info(self, topic: str) -> list[EndpointInfo]:
        return [self._endpoint(i) for i in self._node.get_subscriptions_info_by_topic(topic)]

    def service_names_and_types(self) -> NameAndTypes:
        return [(a, list(b)) for a, b in self._node.get_service_names_and_types()]

    def action_names_and_types(self) -> NameAndTypes:
        from rclpy import action

        return [(a, list(b)) for a, b in action.get_action_names_and_types(self._node)]

    # -- listened data -----------------------------------------------------
    def tf_edges(self) -> list[TFEdge]:
        return list(self._tf)

    def tf_listen_seconds(self) -> float:
        return self._listen

    def diagnostics(self) -> list[DiagnosticMessage]:
        return list(self._diag)

    def logs(self) -> list[LogEntry]:
        return list(self._logs)

    # -- opt-in message counting ------------------------------------------------
    def message_counts(self, topics: list[str]) -> tuple[dict[str, int], float]:
        """Count messages with *raw* subscriptions: payloads are never deserialized.

        Uses BEST_EFFORT/VOLATILE, which is compatible with any publisher, and only
        the topics the user named. Subscriptions are removed afterwards.
        """
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from rosidl_runtime_py.utilities import get_message

        types = dict(self.topic_names_and_types())
        counts: dict[str, int] = {}
        subs = []
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)

        def make_cb(topic: str):
            def cb(_raw) -> None:
                counts[topic] += 1
            return cb

        for topic in topics:
            if topic not in types or not types[topic]:
                continue
            try:
                msg_type = get_message(types[topic][0])
            except (ImportError, ValueError, AttributeError):
                continue
            counts[topic] = 0
            subs.append(self._node.create_subscription(msg_type, topic, make_cb(topic), qos, raw=True))
        self._spin(self._listen)
        for s in subs:
            self._node.destroy_subscription(s)
        return counts, self._listen

    # -- the two read-only service queries --------------------------------
    def _call(self, srv_type, service: str, request):
        client = self._node.create_client(srv_type, service)
        try:
            if not client.wait_for_service(timeout_sec=self._timeout):
                return None
            future = client.call_async(request)
            end = time.monotonic() + self._timeout
            while not future.done() and time.monotonic() < end:
                self._executor.spin_once(timeout_sec=0.05)
            return future.result() if future.done() else None
        finally:
            self._node.destroy_client(client)

    def lifecycle_state(self, node: str) -> str | None:
        from lifecycle_msgs.srv import GetState

        resp = self._call(GetState, f"{node}/get_state", GetState.Request())
        return resp.current_state.label if resp is not None else None

    def list_controllers(self, manager: str) -> list[ControllerInfo] | None:
        try:
            from controller_manager_msgs.srv import ListControllers
        except ImportError:
            return None
        name = f"{manager.rstrip('/')}/list_controllers"
        resp = self._call(ListControllers, name, ListControllers.Request())
        if resp is None:
            return None
        return [ControllerInfo(c.name, c.type, c.state) for c in resp.controller]
