import pytest

from ros2_ai_debugger.analyzers import ExpectedConfig, analyze, rules
from ros2_ai_debugger.models import (
    ActionInfo,
    ControllerInfo,
    ControllersInfo,
    DiagnosticMessage,
    EnvironmentInfo,
    LifecycleInfo,
    LogEntry,
    NodeInfo,
    PublisherInfo,
    Severity,
    SubscriberInfo,
    SystemResourceInfo,
    SystemSnapshot,
    TFEdge,
    TFInfo,
    TopicInfo,
)
from ros2_ai_debugger.utils.commands import is_read_only_command
from tests.fixtures.fake_backend import BEST, REL
from tests.fixtures.scenarios import broken_robot_snapshot

CFG = ExpectedConfig()


def snap(**kw):
    kw.setdefault("nodes", [NodeInfo("/a")])
    return SystemSnapshot(**kw)


def topic(name, pubs=(), subs=()):
    return TopicInfo(name, ["t"], [PublisherInfo(p, "t", REL) for p in pubs],
                     [SubscriberInfo(s, "t", REL) for s in subs])


def ids(findings):
    return [f.source for f in findings]


# R01
def test_r01_expected_publisher_missing_and_present():
    cfg = ExpectedConfig(expected_publishers={"/odom": ["base"]})
    s = snap(nodes=[NodeInfo("/base")], topics=[topic("/odom", subs=["/nav"])])
    f = rules.r01_expected_publisher_missing(s, cfg)
    assert len(f) == 1 and "/base is running" in f[0].observed[0]
    s2 = snap(topics=[topic("/odom", pubs=["/base"])])
    assert rules.r01_expected_publisher_missing(s2, cfg) == []


def test_r01_needs_config():
    assert rules.r01_expected_publisher_missing(snap(), CFG) == []


# R02
def test_r02_unconsumed_and_ignored_topics():
    s = snap(topics=[topic("/scan", pubs=["/l"]), topic("/tf", pubs=["/l"]), topic("/x", ["/a"], ["/b"])])
    f = rules.r02_unconsumed_topics(s, CFG)
    assert len(f) == 1 and f[0].severity == Severity.INFO
    assert f[0].observed == ["/scan: 1 publisher(s), 0 subscribers"]


# R03
def test_r03_missing_publisher_severity():
    s = snap(topics=[topic("/cmd_vel", subs=["/base"]), topic("/tf", subs=["/viz"]),
                     topic("/rosout", subs=["/x"])])
    f = {x.component: x for x in rules.r03_missing_publisher(s, CFG)}
    assert set(f) == {"/cmd_vel", "/tf"}
    assert f["/cmd_vel"].severity == Severity.INFO and f["/tf"].severity == Severity.WARNING


def test_r03_joint_states_correlates_controllers():
    jsb = ControllerInfo("jsb", "joint_state_broadcaster/JointStateBroadcaster", "inactive")
    ctl = ControllersInfo("/controller_manager", [jsb])
    s = snap(topics=[topic("/joint_states", subs=["/rsp"])], controllers=ctl)
    (f,) = rules.r03_missing_publisher(s, CFG)
    assert "joint_state_broadcaster is loaded but not active" in f.possible_causes
    assert f.recommended_checks[0] == "ros2 control list_controllers"


def test_r03_joint_states_without_controller_manager_stays_generic():
    s = snap(topics=[topic("/joint_states", subs=["/rsp"])])
    (f,) = rules.r03_missing_publisher(s, CFG)
    assert f.confidence == 0.6 and not any("controller manager" in o for o in f.observed)


# R04
def test_r04_required_node_missing():
    cfg = ExpectedConfig(required_nodes=["nav", "/a"])
    f = rules.r04_required_node_missing(snap(), cfg)
    assert [x.component for x in f] == ["/nav"] and f[0].severity == Severity.ERROR


# R05
def test_r05_tf_disconnected_and_connected():
    bad = snap(tf=TFInfo(2.0, [TFEdge("b", "a"), TFEdge("y", "x")]))
    (f,) = rules.r05_tf_disconnected(bad, CFG)
    assert "2 disconnected trees" in f.problem and "tree 2: x, y" in f.observed
    ok = snap(tf=TFInfo(2.0, [TFEdge("b", "a"), TFEdge("c", "b")]))
    assert rules.r05_tf_disconnected(ok, CFG) == []
    assert rules.r05_tf_disconnected(snap(tf=TFInfo()), CFG) == []
    assert rules.r05_tf_disconnected(snap(), CFG) == []


# R06
@pytest.mark.parametrize("state,expected", [("active", None), ("inactive", Severity.WARNING),
                                            ("unconfigured", Severity.WARNING),
                                            ("errorprocessing", Severity.ERROR)])
def test_r06_lifecycle(state, expected):
    f = rules.r06_lifecycle_not_active(snap(lifecycle=[LifecycleInfo("/lc", state)]), CFG)
    assert (f[0].severity if f else None) == expected


# R07
def test_r07_required_and_client_without_server():
    s = snap(actions=[ActionInfo("/nav", ["T"], [], ["/bt"]), ActionInfo("/ok", ["T"], ["/s"], [])])
    f = rules.r07_action_server_unavailable(s, ExpectedConfig(required_action_servers=["nav", "/missing", "ok"]))
    assert sorted(x.component for x in f) == ["/missing", "/nav"]
    assert all(x.severity == Severity.ERROR for x in f)
    g = rules.r07_action_server_unavailable(s, CFG)
    assert [x.component for x in g] == ["/nav"] and g[0].severity == Severity.WARNING


# R08
def test_r08_resources_thresholds():
    s = snap(system=SystemResourceInfo(cpu_percent=95, memory_percent=50, disk_percent=91))
    assert [f.problem.split()[0] for f in rules.r08_resources(s, CFG)] == ["CPU", "Disk"]
    assert rules.r08_resources(s, ExpectedConfig(cpu_warn_percent=99, disk_warn_percent=99)) == []
    assert rules.r08_resources(snap(system=SystemResourceInfo()), CFG) == []


# R09
def test_r09_domain_id():
    cfg = ExpectedConfig(expected_domain_id="5")
    assert rules.r09_domain_id(snap(environment=EnvironmentInfo(ros_domain_id="5")), cfg) == []
    (f,) = rules.r09_domain_id(snap(environment=EnvironmentInfo(ros_domain_id=None)), cfg)
    assert "unset (default 0)" in f.observed[0]
    assert rules.r09_domain_id(snap(), CFG) == []
    assert rules.r09_domain_id(snap(environment=EnvironmentInfo()), ExpectedConfig(expected_domain_id="0")) == []


# R10
def test_r10_qos_mismatch():
    t = TopicInfo("/scan", [], [PublisherInfo("/lidar", "", BEST)], [SubscriberInfo("/map", "", REL)])
    (f,) = rules.r10_qos_mismatch(snap(topics=[t]), CFG)
    assert f.severity == Severity.ERROR and "RELIABILITY=BEST_EFFORT" in f.observed[0]


# R11
def test_r11_controller_not_active():
    c = ControllersInfo("/cm", [ControllerInfo("a", "T", "active"), ControllerInfo("b", "T", "inactive")])
    (f,) = rules.r11_controllers_not_active(snap(controllers=c), CFG)
    assert f.component == "b"
    assert rules.r11_controllers_not_active(snap(), CFG) == []


# R12
def test_r12_empty_graph():
    (f,) = rules.r12_empty_graph(SystemSnapshot(), CFG)
    assert f.component == "graph"
    assert rules.r12_empty_graph(snap(), CFG) == []
    failed = SystemSnapshot(collection_errors=["nodes: RuntimeError: x"])
    assert rules.r12_empty_graph(failed, CFG) == []


# R13
def test_r13_logs_grouped():
    logs = [LogEntry("ERROR", "/a", "boom", 1)] * 3 + [LogEntry("WARN", "/b", "hm", 2)]
    f = rules.r13_log_errors(snap(logs=logs), CFG)
    assert [(x.severity, x.problem[:1]) for x in f] == [(Severity.WARNING, "3"), (Severity.INFO, "1")]
    assert f[0].observed == ["3x [/a] boom"]


# R14
def test_r14_diagnostics():
    d = [DiagnosticMessage("motor", "ERROR", "hot", values={"temp": "99"}), DiagnosticMessage("imu", "OK")]
    (f,) = rules.r14_diagnostics(snap(diagnostics=d), CFG)
    assert f.component == "motor" and "temp = 99" in f.observed


# Engine and the broken robot scenario
def test_broken_robot_findings():
    f = analyze(broken_robot_snapshot())
    assert [(x.source, x.component) for x in f] == [
        ("rule:R03", "/joint_states"), ("rule:R05", "tf"),
        ("rule:R02", "graph"), ("rule:R03", "/arm_controller/joint_trajectory"), ("rule:R13", "logs")]
    by = {(x.source, x.component): x for x in f}
    js = by[("rule:R03", "/joint_states")]
    assert js.severity == Severity.WARNING and js.confidence == 0.85
    assert "no controller of type JointStateBroadcaster is loaded" in js.observed
    assert ("controller 'arm_controller' (joint_trajectory_controller/JointTrajectoryController) is active"
            in js.observed)
    assert ("rule:R05", "tf") in by
    assert f == sorted(f, key=lambda x: (-int(x.severity), x.source, x.component))


def test_all_recommended_checks_are_read_only():
    for f in analyze(broken_robot_snapshot()):
        assert all(is_read_only_command(c) for c in f.recommended_checks), f.recommended_checks


@pytest.mark.parametrize("cmd,ok", [
    ("ros2 topic echo /joint_states", True), ("ros2 control list_controllers", True),
    ("ros2 run tf2_ros tf2_echo a b", True), ("printenv ROS_DOMAIN_ID", True), ("ros2 doctor --report", True),
    ("ros2 topic pub /cmd_vel geometry_msgs/Twist", False), ("ros2 param set /n p 1", False),
    ("ros2 lifecycle set /n activate", False), ("ros2 run demo_nodes_cpp talker", False),
    ("ros2 topic echo /x; rm -rf /", False), ("ros2 topic echo $(id)", False), ("kill -9 1", False),
    ("printenv ANTHROPIC_API_KEY", False), ("ros2 service call /x std_srvs/Empty", False), ("", False),
])
def test_command_allowlist(cmd, ok):
    assert is_read_only_command(cmd) is ok
