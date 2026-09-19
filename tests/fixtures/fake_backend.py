"""In-memory RosBackend for tests, plus the 'broken robot' scenario."""
from __future__ import annotations

from ros2_ai_debugger.collectors.base import RawNodeEndpoints
from ros2_ai_debugger.models import (
    ControllerInfo,
    DiagnosticMessage,
    EndpointInfo,
    LogEntry,
    QoSInfo,
    TFEdge,
)

REL = QoSInfo("RELIABLE", "VOLATILE", "KEEP_LAST", 10)
BEST = QoSInfo("BEST_EFFORT", "VOLATILE", "KEEP_LAST", 5)


def ep(node: str, typ: str, qos: QoSInfo = REL) -> EndpointInfo:
    return EndpointInfo(node, typ, qos)


class FakeBackend:
    def __init__(self) -> None:
        self.nodes: list[tuple[str, str]] = []  # (name, ns)
        self.endpoints: dict[tuple[str, str], RawNodeEndpoints] = {}
        self.topics: dict[str, list[str]] = {}
        self.pubs: dict[str, list[EndpointInfo]] = {}
        self.subs: dict[str, list[EndpointInfo]] = {}
        self.services: dict[str, list[str]] = {}
        self.actions: dict[str, list[str]] = {}
        self.tf: list[TFEdge] = []
        self.diag: list[DiagnosticMessage] = []
        self.log: list[LogEntry] = []
        self.lifecycle: dict[str, str] = {}
        self.controllers: dict[str, list[ControllerInfo]] = {}

    def add_node(self, name, ns="/", *, pub=(), sub=(), srv=(), cli=(), act_srv=(), act_cli=()):
        self.nodes.append((name, ns))
        def t(items):
            return [(n, [ty]) for n, ty in items]

        self.endpoints[(name, ns)] = RawNodeEndpoints(
            t(pub), t(sub), t(srv), t(cli), t(act_srv), t(act_cli))

    # RosBackend protocol
    def node_names_and_namespaces(self): return list(self.nodes)
    def node_endpoints(self, name, namespace): return self.endpoints[(name, namespace)]
    def topic_names_and_types(self): return list(self.topics.items())
    def publishers_info(self, topic): return self.pubs.get(topic, [])
    def subscribers_info(self, topic): return self.subs.get(topic, [])
    def service_names_and_types(self): return list(self.services.items())
    def action_names_and_types(self): return list(self.actions.items())
    def tf_edges(self): return list(self.tf)
    def tf_listen_seconds(self): return 2.0
    def diagnostics(self): return list(self.diag)
    def logs(self): return list(self.log)
    def lifecycle_state(self, node): return self.lifecycle.get(node)
    def list_controllers(self, manager): return self.controllers.get(manager)


def broken_robot_backend() -> FakeBackend:
    """/arm_controller runs, but nothing publishes /joint_states; TF is split."""
    b = FakeBackend()
    js = "sensor_msgs/msg/JointState"
    b.add_node("arm_controller", pub=[("/arm_controller/state", "control_msgs/msg/JointTrajectoryControllerState")],
               sub=[("/arm_controller/joint_trajectory", "trajectory_msgs/msg/JointTrajectory")],
               srv=[("/arm_controller/get_parameters", "rcl_interfaces/srv/GetParameters")])
    b.add_node("controller_manager",
               srv=[("/controller_manager/list_controllers",
                     "controller_manager_msgs/srv/ListControllers")])
    b.add_node("robot_state_publisher",
               pub=[("/tf", "tf2_msgs/msg/TFMessage"), ("/tf_static", "tf2_msgs/msg/TFMessage"),
                    ("/robot_description", "std_msgs/msg/String")],
               sub=[("/joint_states", js)])
    b.add_node("_ros2cli_1234")  # hidden node: must be ignored
    b.add_node("ros2_ai_debugger")  # ourselves: must be ignored

    b.topics = {
        "/joint_states": [js],
        "/tf": ["tf2_msgs/msg/TFMessage"],
        "/tf_static": ["tf2_msgs/msg/TFMessage"],
        "/robot_description": ["std_msgs/msg/String"],
        "/arm_controller/state": ["control_msgs/msg/JointTrajectoryControllerState"],
        "/arm_controller/joint_trajectory": ["trajectory_msgs/msg/JointTrajectory"],
        "/arm_controller/_action/status": ["action_msgs/msg/GoalStatusArray"],  # hidden
    }
    b.pubs = {
        "/tf": [ep("/robot_state_publisher", "tf2_msgs/msg/TFMessage")],
        "/tf_static": [ep("/robot_state_publisher", "tf2_msgs/msg/TFMessage")],
        "/robot_description": [ep("/robot_state_publisher", "std_msgs/msg/String")],
        "/arm_controller/state": [ep("/arm_controller", "control_msgs/msg/JointTrajectoryControllerState")],
    }
    b.subs = {
        "/joint_states": [ep("/robot_state_publisher", js)],
        "/arm_controller/joint_trajectory": [ep("/arm_controller", "trajectory_msgs/msg/JointTrajectory")],
        "/arm_controller/state": [ep("/ros2_ai_debugger", "x")],  # ourselves: ignored
    }
    b.services = {
        "/controller_manager/list_controllers": ["controller_manager_msgs/srv/ListControllers"],
        "/arm_controller/get_parameters": ["rcl_interfaces/srv/GetParameters"],
    }
    b.tf = [
        TFEdge("arm_link1", "base_link"), TFEdge("arm_link2", "arm_link1"),
        TFEdge("arm_link1", "base_link"),  # duplicate: must collapse
        TFEdge("camera_optical_frame", "camera_link", True),  # disconnected static pair
    ]
    b.log = [
        LogEntry("INFO", "/arm_controller", "controller started", 100.0),
        LogEntry("WARN", "/robot_state_publisher", "No JointState messages received", 101.0),
    ]
    b.controllers = {"/controller_manager": [
        ControllerInfo("arm_controller", "joint_trajectory_controller/JointTrajectoryController", "active")]}
    return b
