"""Live tests against a real ROS 2 graph. Run in a sourced ROS 2 shell:

    source /opt/ros/<distro>/setup.bash && pytest -m ros

They start examples/broken_robot_demo.py in an isolated ROS_DOMAIN_ID and check
that the deliberately planted problems are diagnosed. Skipped without rclpy.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

if os.environ.get("REQUIRE_ROS"):  # CI: a missing ROS environment must fail, not skip
    import rclpy  # noqa: F401
else:
    pytest.importorskip("rclpy")
pytestmark = pytest.mark.ros

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = "87"


@pytest.fixture(scope="module")
def demo_robot():
    env = {**os.environ, "ROS_DOMAIN_ID": DOMAIN}
    proc = subprocess.Popen([sys.executable, str(ROOT / "examples" / "broken_robot_demo.py")],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)  # let discovery settle
    assert proc.poll() is None, "demo robot failed to start"
    yield proc
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def domain(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", DOMAIN)


def _live_report(listen=2.5, watch=None):
    from ros2_ai_debugger.analyzers import analyze
    from ros2_ai_debugger.collectors import collect_snapshot, default_collectors
    from ros2_ai_debugger.collectors.rclpy_backend import RclpyBackend

    with RclpyBackend(listen_seconds=listen) as backend:
        snap = collect_snapshot(default_collectors(backend, watch_topics=watch))
    return snap, analyze(snap)


def test_live_snapshot_matches_demo(demo_robot, domain):
    snap, _ = _live_report()
    assert snap.collection_errors == []
    assert {"/arm_controller", "/controller_manager", "/robot_state_publisher", "/lidar",
            "/mapper", "/lifecycle_demo", "/planner"} <= snap.node_names()
    assert not any(n.name.startswith("/_") or n.name.endswith("ros2_ai_debugger") for n in snap.nodes)
    js = snap.topic("/joint_states")
    assert js.publishers == [] and [s.node_name for s in js.subscribers] == ["/robot_state_publisher"]
    scan = snap.topic("/scan")
    assert scan.publishers[0].qos.reliability == "BEST_EFFORT"
    assert scan.subscribers[0].qos.reliability == "RELIABLE"
    assert len(snap.tf.components()) == 2
    assert [(x.node, x.state) for x in snap.lifecycle] == [("/lifecycle_demo", "unconfigured")]
    assert snap.controllers.controllers[0].name == "arm_controller"
    assert snap.environment.ros_distro in ("humble", "jazzy", "iron", "rolling") or snap.environment.ros_distro


def test_live_rules_find_every_planted_problem(demo_robot, domain):
    _, findings = _live_report()
    got = {(f.source, f.component) for f in findings}
    for expected in [("rule:R10", "/scan"), ("rule:R03", "/joint_states"), ("rule:R05", "tf"),
                     ("rule:R06", "/lifecycle_demo"), ("rule:R07", "/compute_path"), ("rule:R13", "logs")]:
        assert expected in got, f"missing {expected}; got {sorted(got)}"


def test_live_backend_is_read_only(demo_robot, domain):
    """Running the tool must not change the graph (no publishers/subscribers left behind)."""
    before, _ = _live_report(1.0)
    after, _ = _live_report(1.0)
    assert sorted(t.name for t in before.topics) == sorted(t.name for t in after.topics)
    assert before.node_names() == after.node_names()


@pytest.mark.skipif(shutil.which("ros2") is None and not os.environ.get("REQUIRE_ROS"),
                    reason="ros2 CLI not on PATH")
def test_ros2_ai_command_is_registered(demo_robot):
    env = {**os.environ, "ROS_DOMAIN_ID": DOMAIN,
           "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")])}
    ver = subprocess.run(["ros2", "ai", "version"], env=env, capture_output=True, text=True, timeout=60)
    if "invalid choice" in ver.stderr and not os.environ.get("REQUIRE_ROS"):
        pytest.skip("ros2-ai-debugger is not installed into the ROS 2 Python environment")
    assert ver.returncode == 0 and "ros2-ai-debugger" in ver.stdout
    run = subprocess.run(["ros2", "ai", "diagnose", "--format", "json", "--listen-seconds", "2.5"],
                         env=env, capture_output=True, text=True, timeout=90)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert any(f["component"] == "/joint_states" for f in report["findings"])


def test_live_silent_publisher_detected_without_reading_payloads(demo_robot, domain):
    """/imu/data has a publisher that never publishes; /scan really streams (control)."""
    snap, findings = _live_report(watch=["/imu/data", "/scan"])
    counts = {a.topic: a.messages for a in snap.topic_activity}
    assert counts["/imu/data"] == 0 and counts["/scan"] > 0
    silent = [f for f in findings if f.source == "rule:R15"]
    assert [f.component for f in silent] == ["/imu/data"]  # /scan must not be flagged
    assert any("Could not open /dev/ttyUSB1" in o for o in silent[0].observed)
    assert silent[0].confidence == 0.8
