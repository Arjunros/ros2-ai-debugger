"""Modular diagnostic collectors."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from ros2_ai_debugger.collectors.actions import ActionCollector
from ros2_ai_debugger.collectors.activity import TopicActivityCollector
from ros2_ai_debugger.collectors.base import DiagnosticCollector, RosBackend
from ros2_ai_debugger.collectors.controllers import ControllerCollector
from ros2_ai_debugger.collectors.diagnostics import DiagnosticsCollector
from ros2_ai_debugger.collectors.lifecycle import LifecycleCollector
from ros2_ai_debugger.collectors.logs import LogCollector
from ros2_ai_debugger.collectors.nodes import NodeCollector
from ros2_ai_debugger.collectors.services import ServiceCollector
from ros2_ai_debugger.collectors.system import EnvironmentCollector, SystemCollector
from ros2_ai_debugger.collectors.tf import TFCollector
from ros2_ai_debugger.collectors.topics import TopicCollector
from ros2_ai_debugger.models import SystemSnapshot


def default_collectors(
    backend: RosBackend | None, log_entries: int = 50, watch_topics: list[str] | None = None
) -> list[DiagnosticCollector]:
    """All collectors; ROS-dependent ones are included only when a backend is given."""
    collectors: list[DiagnosticCollector] = [EnvironmentCollector(), SystemCollector()]
    if backend is not None:
        collectors += [
            NodeCollector(backend),
            TopicCollector(backend),
            ServiceCollector(backend),
            ActionCollector(backend),
            TFCollector(backend),
            LifecycleCollector(backend),
            ControllerCollector(backend),
            DiagnosticsCollector(backend),
            LogCollector(backend, max_entries=log_entries),
        ]
        if watch_topics:
            collectors.append(TopicActivityCollector(backend, watch_topics))
    return collectors


def collect_snapshot(
    collectors: list[DiagnosticCollector],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> SystemSnapshot:
    """Run every collector; one failing collector never aborts the others."""
    snapshot = SystemSnapshot(collected_at=now().strftime("%Y-%m-%dT%H:%M:%SZ"))
    for c in collectors:
        try:
            setattr(snapshot, c.field, c.collect())
        except Exception as exc:  # noqa: BLE001 - report and continue
            snapshot.collection_errors.append(f"{c.name}: {type(exc).__name__}: {exc}")
    return snapshot
