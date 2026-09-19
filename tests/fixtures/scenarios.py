"""Deterministic snapshots built from the fake backends."""
from __future__ import annotations

from datetime import datetime, timezone

from ros2_ai_debugger.collectors import collect_snapshot
from ros2_ai_debugger.collectors.actions import ActionCollector
from ros2_ai_debugger.collectors.controllers import ControllerCollector
from ros2_ai_debugger.collectors.diagnostics import DiagnosticsCollector
from ros2_ai_debugger.collectors.lifecycle import LifecycleCollector
from ros2_ai_debugger.collectors.logs import LogCollector
from ros2_ai_debugger.collectors.nodes import NodeCollector
from ros2_ai_debugger.collectors.services import ServiceCollector
from ros2_ai_debugger.collectors.tf import TFCollector
from ros2_ai_debugger.collectors.topics import TopicCollector
from ros2_ai_debugger.models import EnvironmentInfo, SystemResourceInfo, SystemSnapshot
from tests.fixtures.fake_backend import broken_robot_backend

FIXED_TIME = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def broken_robot_snapshot() -> SystemSnapshot:
    """The reference broken robot: /joint_states has no publisher, TF is split."""
    b = broken_robot_backend()
    collectors = [NodeCollector(b), TopicCollector(b), ServiceCollector(b), ActionCollector(b),
                  TFCollector(b), LifecycleCollector(b), ControllerCollector(b),
                  DiagnosticsCollector(b), LogCollector(b)]
    snap = collect_snapshot(collectors, now=lambda: FIXED_TIME)
    # Host data is fixed so reports are byte-for-byte reproducible.
    snap.environment = EnvironmentInfo(
        ros_distro="humble", ros_domain_id=None, rmw_implementation="rmw_fastrtps_cpp",
        localhost_only=None, os_name="Ubuntu 22.04.5 LTS", python_version="3.10.12", hostname="robot-pc")
    snap.system = SystemResourceInfo(cpu_percent=12.5, cpu_count=8, load_avg=[0.4, 0.5, 0.6],
                                     memory_percent=41.0, memory_total_mb=16000, disk_percent=55.0)
    return snap
