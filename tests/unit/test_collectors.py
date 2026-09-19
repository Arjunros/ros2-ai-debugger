from ros2_ai_debugger.collectors import collect_snapshot, default_collectors
from ros2_ai_debugger.collectors.actions import ActionCollector
from ros2_ai_debugger.collectors.activity import TopicActivityCollector
from ros2_ai_debugger.collectors.base import DiagnosticCollector, full_name, is_hidden
from ros2_ai_debugger.collectors.controllers import ControllerCollector
from ros2_ai_debugger.collectors.diagnostics import DiagnosticsCollector
from ros2_ai_debugger.collectors.lifecycle import LifecycleCollector
from ros2_ai_debugger.collectors.logs import LogCollector
from ros2_ai_debugger.collectors.nodes import NodeCollector
from ros2_ai_debugger.collectors.qos import qos_mismatches
from ros2_ai_debugger.collectors.services import ServiceCollector
from ros2_ai_debugger.collectors.system import (
    EnvironmentCollector,
    SystemCollector,
    parse_cpu_times,
    parse_meminfo,
)
from ros2_ai_debugger.collectors.tf import TFCollector
from ros2_ai_debugger.collectors.topics import TopicCollector
from ros2_ai_debugger.models import (
    DiagnosticMessage,
    LogEntry,
    PublisherInfo,
    QoSInfo,
    SubscriberInfo,
    TFEdge,
    TFInfo,
    TopicInfo,
)
from tests.fixtures.fake_backend import BEST, REL, FakeBackend, broken_robot_backend


def test_names():
    assert full_name("n", "/") == "/n"
    assert full_name("n", "/a/b") == "/a/b/n"
    assert is_hidden("/x/_action/feedback") and not is_hidden("/x/y")


def test_node_collection_hides_hidden_and_self():
    nodes = NodeCollector(broken_robot_backend()).collect()
    assert [n.name for n in nodes] == ["/arm_controller", "/controller_manager", "/robot_state_publisher"]
    rsp = nodes[2]
    assert rsp.subscribes == ["/joint_states"] and "/tf" in rsp.publishes


def test_namespaced_node():
    b = FakeBackend()
    b.add_node("talker", "/ns1/ns2")
    assert NodeCollector(b).collect()[0].name == "/ns1/ns2/talker"


def test_topic_collection_endpoints_and_filters():
    topics = {t.name: t for t in TopicCollector(broken_robot_backend()).collect()}
    assert "/arm_controller/_action/status" not in topics
    js = topics["/joint_states"]
    assert js.publishers == []
    assert [s.node_name for s in js.subscribers] == ["/robot_state_publisher"]
    # the tool's own subscription is not reported
    assert topics["/arm_controller/state"].subscribers == []
    assert topics["/tf"].publishers[0].qos.reliability == "RELIABLE"


def test_service_collection_providers_and_param_filter():
    services = ServiceCollector(broken_robot_backend()).collect()
    assert [s.name for s in services] == ["/controller_manager/list_controllers"]
    assert services[0].providers == ["/controller_manager"]
    assert len(ServiceCollector(broken_robot_backend(), True).collect()) == 2


def test_action_collection_servers_and_clients():
    b = FakeBackend()
    T = "nav2_msgs/action/NavigateToPose"
    b.add_node("bt", act_cli=[("/navigate_to_pose", T)])
    b.add_node("nav", act_srv=[("/follow_path", "nav2_msgs/action/FollowPath")])
    b.actions = {"/navigate_to_pose": [T], "/follow_path": ["nav2_msgs/action/FollowPath"]}
    acts = {a.name: a for a in ActionCollector(b).collect()}
    assert acts["/navigate_to_pose"].servers == [] and acts["/navigate_to_pose"].clients == ["/bt"]
    assert acts["/follow_path"].servers == ["/nav"]


def test_tf_collection_dedupes_and_components():
    tf = TFCollector(broken_robot_backend()).collect()
    assert len(tf.edges) == 3
    comps = tf.components()
    assert comps == [["arm_link1", "arm_link2", "base_link"], ["camera_link", "camera_optical_frame"]]


def test_tf_strips_leading_slash_and_static_wins():
    b = FakeBackend()
    b.tf = [TFEdge("/b", "/a", False), TFEdge("b", "a", True)]
    tf = TFCollector(b).collect()
    assert [(e.child, e.parent, e.is_static) for e in tf.edges] == [("b", "a", True)]


def test_tf_empty():
    assert TFInfo().components() == [] and TFInfo().frames() == []


def test_lifecycle_collection_only_lifecycle_nodes():
    b = FakeBackend()
    gs = "lifecycle_msgs/srv/GetState"
    b.add_node("lc", srv=[("/lc/get_state", gs)])
    b.add_node("plain", srv=[("/plain/get_state", "other/srv/Thing")])
    b.lifecycle = {"/lc": "inactive", "/plain": "active"}
    out = LifecycleCollector(b).collect()
    assert [(x.node, x.state) for x in out] == [("/lc", "inactive")]


def test_lifecycle_unreachable_node_skipped():
    b = FakeBackend()
    b.add_node("lc", srv=[("/lc/get_state", "lifecycle_msgs/srv/GetState")])
    assert LifecycleCollector(b).collect() == []


def test_controller_collection():
    info = ControllerCollector(broken_robot_backend()).collect()
    assert info.manager == "/controller_manager" and info.controllers[0].state == "active"
    assert ControllerCollector(FakeBackend()).collect() is None


def test_diagnostics_latest_per_name():
    b = FakeBackend()
    b.diag = [DiagnosticMessage("motor", "OK"), DiagnosticMessage("motor", "ERROR", "overheat"),
              DiagnosticMessage("imu", "OK")]
    out = DiagnosticsCollector(b).collect()
    assert [(d.name, d.level) for d in out] == [("imu", "OK"), ("motor", "ERROR")]


def test_log_filter_and_cap():
    b = FakeBackend()
    b.log = [LogEntry("INFO", "a", "i", 1), LogEntry("WARN", "a", "w1", 2),
             LogEntry("ERROR", "a", "e", 3), LogEntry("WARN", "a", "w2", 4)]
    out = LogCollector(b, "WARN", 2).collect()
    assert [e.message for e in out] == ["e", "w2"]


def test_system_parsers():
    assert parse_cpu_times("cpu  100 0 100 800 0 0 0 0 0 0") == (800, 1000)
    used, total = parse_meminfo("MemTotal: 2048000 kB\nMemAvailable: 512000 kB\n")
    assert (used, total) == (75.0, 2000)
    assert parse_meminfo("MemTotal: 1 kB\n") is None


def test_system_collector_live_smoke():
    s = SystemCollector(cpu_interval=0.05).collect()
    assert s.cpu_count > 0 and 0 <= s.memory_percent <= 100 and 0 <= s.disk_percent <= 100


def test_environment_collector_reads_only_whitelist():
    env = EnvironmentCollector({"ROS_DISTRO": "jazzy", "ROS_DOMAIN_ID": "7",
                                "ANTHROPIC_API_KEY": "sk-secret", "AWS_SECRET": "x"}).collect()
    assert (env.ros_distro, env.ros_domain_id) == ("jazzy", "7")
    assert "sk-secret" not in repr(env)


def test_collect_snapshot_isolates_failures():
    class Boom(DiagnosticCollector):
        name, field = "boom", "tf"
        def collect(self):
            raise RuntimeError("nope")

    snap = collect_snapshot([Boom(), NodeCollector(broken_robot_backend())])
    assert snap.collection_errors == ["boom: RuntimeError: nope"]
    assert len(snap.nodes) == 3


def test_default_collectors_without_backend_has_no_ros():
    assert {c.name for c in default_collectors(None)} == {"environment", "system"}


def _topic(pq, sq):
    return TopicInfo("/t", [], [PublisherInfo("/p", "", pq)], [SubscriberInfo("/s", "", sq)])


def test_qos_reliability_mismatch():
    m = qos_mismatches(_topic(BEST, REL))
    assert len(m) == 1 and m[0].policy == "reliability"


def test_qos_compatible_and_unknown_not_guessed():
    assert qos_mismatches(_topic(REL, BEST)) == []
    assert qos_mismatches(_topic(QoSInfo("UNKNOWN"), REL)) == []
    assert qos_mismatches(_topic(QoSInfo("SYSTEM_DEFAULT"), REL)) == []


def test_qos_durability_mismatch():
    tl = QoSInfo("RELIABLE", "TRANSIENT_LOCAL")
    m = qos_mismatches(_topic(QoSInfo("RELIABLE", "VOLATILE"), tl))
    assert [x.policy for x in m] == ["durability"]
    assert qos_mismatches(_topic(tl, QoSInfo("RELIABLE", "VOLATILE"))) == []


def test_topics_ignore_hidden_node_endpoints_and_phantom_topics():
    b = FakeBackend()
    b.topics = {"/rosout": ["l"], "/diagnostics": ["d"]}
    b.pubs = {"/rosout": [ep_("/_ros2cli_daemon_0"), ep_("/talker")]}
    b.subs = {"/diagnostics": [ep_("/ros2_ai_debugger")]}
    topics = TopicCollector(b).collect()
    assert [t.name for t in topics] == ["/rosout"]
    assert [p.node_name for p in topics[0].publishers] == ["/talker"]


def ep_(name):
    from tests.fixtures.fake_backend import ep
    return ep(name, "x")


def test_topic_activity_collector_counts_only_watchable_topics():
    b = FakeBackend()
    b.counts = {"/a": 0, "/b": 12}
    out = TopicActivityCollector(b, ["/b", "/a", "/unknown", "/a"]).collect()
    assert [(x.topic, x.messages, x.seconds) for x in out] == [("/a", 0, 2.0), ("/b", 12, 2.0)]


def test_watch_topics_only_collected_when_requested():
    assert "topic_activity" not in {c.name for c in default_collectors(FakeBackend())}
    assert "topic_activity" in {c.name for c in default_collectors(FakeBackend(), watch_topics=["/a"])}
