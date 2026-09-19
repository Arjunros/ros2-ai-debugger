"""Deterministic diagnostic rules.

Each rule is a pure function ``(snapshot, config) -> list[Finding]``. Rules
only report what the collected data supports; anything beyond that is placed
in ``possible_causes`` (inference) and phrased as a possibility.
"""
from __future__ import annotations

from collections.abc import Callable

from ros2_ai_debugger.analyzers.config import ExpectedConfig
from ros2_ai_debugger.collectors.qos import qos_mismatches
from ros2_ai_debugger.models import Finding, Severity, SystemSnapshot

Rule = Callable[[SystemSnapshot, ExpectedConfig], list[Finding]]

#: Topics that commonly have one side only without indicating a problem.
_IGNORED_NO_PUBLISHER = {"/parameter_events", "/rosout"}
#: Topics whose absence is a real problem on essentially every robot. Any other
#: topic without a publisher is reported at INFO, since command/input topics
#: (cmd_vel, joint_trajectory, ...) are legitimately idle until someone publishes.
_STATE_TOPICS = {"/joint_states", "/tf", "/clock"}
_IGNORED_NO_SUBSCRIBER = {
    "/parameter_events", "/rosout", "/tf", "/tf_static", "/robot_description", "/diagnostics",
}


def _norm(name: str) -> str:
    return name if name.startswith("/") else "/" + name


def _f(rule: str, sev: Severity, comp: str, problem: str, **kw) -> Finding:
    return Finding(severity=sev, component=comp, problem=problem, source=f"rule:{rule}", **kw)


# R01 ------------------------------------------------------------------------
def r01_expected_publisher_missing(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    out = []
    for topic, nodes in sorted(cfg.expected_publishers.items()):
        info = s.topic(topic)
        actual = {p.node_name for p in info.publishers} if info else set()
        for node in nodes:
            if _norm(node) not in actual:
                running = _norm(node) in s.node_names()
                out.append(_f(
                    "R01", Severity.WARNING, _norm(node),
                    f"{_norm(node)} is expected to publish {topic} but is not publishing it",
                    observed=[
                        f"{_norm(node)} is {'running' if running else 'not running'}",
                        f"{topic} has {len(actual)} publisher(s)"
                        + (f": {', '.join(sorted(actual))}" if actual else ""),
                    ],
                    possible_causes=[
                        "The node is not running or crashed" if not running
                        else "The node started but has not created this publisher (not configured/activated)",
                        "The topic name is remapped or namespaced differently",
                    ],
                    recommended_checks=[f"ros2 topic info {topic} --verbose", f"ros2 node info {_norm(node)}"],
                    confidence=0.7,
                ))
    return out


# R02 ------------------------------------------------------------------------
def r02_unconsumed_topics(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    topics = [
        t.name for t in s.topics
        if t.publishers and not t.subscribers and t.name not in _IGNORED_NO_SUBSCRIBER
    ]
    if not topics:
        return []
    return [_f(
        "R02", Severity.INFO, "graph",
        f"{len(topics)} topic(s) have publishers but no subscribers",
        observed=[f"{t}: {len(s.topic(t).publishers)} publisher(s), 0 subscribers" for t in topics],
        possible_causes=[
            "Often harmless (data published for optional consumers such as rosbag or rviz)",
            "A consumer node may be missing, not started, or subscribed under a different name",
        ],
        recommended_checks=[f"ros2 topic info {topics[0]} --verbose"],
        confidence=0.3,
    )]


# R03 ------------------------------------------------------------------------
def r03_missing_publisher(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    out = []
    for t in s.topics:
        if t.subscribers and not t.publishers and t.name not in _IGNORED_NO_PUBLISHER:
            observed = [
                f"{t.name} has 0 publishers",
                f"{t.name} has {len(t.subscribers)} subscriber(s): "
                + ", ".join(x.node_name for x in t.subscribers),
            ]
            causes = [
                "Normal for command/input topics that are only published on demand",
                "The node that should publish this topic is not running",
                "The publisher uses a different topic name or namespace (remapping)",
                "Publisher and subscriber are in different ROS_DOMAIN_IDs or not discovering each other",
            ]
            checks = [f"ros2 topic info {t.name} --verbose", f"ros2 topic echo {t.name}"]
            confidence = 0.6
            severity = Severity.WARNING if t.name in _STATE_TOPICS else Severity.INFO
            if severity is Severity.INFO:
                confidence = 0.3
            if t.name == "/joint_states":
                obs, cause, chk, conf = _joint_states_hints(s)
                observed += obs
                causes = cause + causes[1:2]
                checks = chk + checks
                confidence = conf
            out.append(_f("R03", severity, t.name,
                          f"No publisher detected on {t.name} although it has subscribers",
                          observed=observed, possible_causes=causes,
                          recommended_checks=checks, confidence=confidence))
    return out


def _joint_states_hints(s: SystemSnapshot) -> tuple[list[str], list[str], list[str], float]:
    """Extra evidence for the very common ros2_control missing-/joint_states case."""
    obs: list[str] = []
    causes = ["A joint state publisher (e.g. joint_state_broadcaster) is not running"]
    checks: list[str] = []
    conf = 0.6
    c = s.controllers
    if c is not None:
        conf = 0.85
        obs.append(f"controller manager {c.manager} is running")
        for ctl in c.controllers:
            obs.append(f"controller '{ctl.name}' ({ctl.type or 'unknown type'}) is {ctl.state}")
        jsb = [x for x in c.controllers if "JointStateBroadcaster" in x.type]
        if not jsb:
            obs.append("no controller of type JointStateBroadcaster is loaded")
            causes = ["joint_state_broadcaster is not loaded/spawned in controller_manager"]
        elif any(x.state != "active" for x in jsb):
            causes = ["joint_state_broadcaster is loaded but not active"]
        else:
            conf = 0.5
            causes = ["An active joint_state_broadcaster exists but nothing is publishing (hardware interface?)"]
        checks.append("ros2 control list_controllers")
        causes.append("Controller configuration or robot hardware interface failure")
    return obs, causes, checks, conf


# R04 ------------------------------------------------------------------------
def r04_required_node_missing(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    running = s.node_names()
    return [
        _f("R04", Severity.ERROR, _norm(n), f"Required node {_norm(n)} is not running",
           observed=[f"{_norm(n)} is not in the node list ({len(running)} nodes visible)"],
           possible_causes=[
               "The node crashed or was never launched",
               "The node is running in a different namespace or ROS_DOMAIN_ID",
           ],
           recommended_checks=["ros2 node list", "printenv ROS_DOMAIN_ID"], confidence=0.7)
        for n in cfg.required_nodes if _norm(n) not in running
    ]


# R05 ------------------------------------------------------------------------
def r05_tf_disconnected(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    if s.tf is None or not s.tf.edges:
        return []
    comps = s.tf.components()
    if len(comps) < 2:
        return []
    observed = [f"{len(s.tf.frames())} frames observed in {len(comps)} disconnected trees "
                f"(listened {s.tf.listen_seconds:g}s)"]
    observed += [f"tree {i}: {', '.join(c)}" for i, c in enumerate(comps, 1)]
    return [_f(
        "R05", Severity.WARNING, "tf",
        f"TF frames form {len(comps)} disconnected trees",
        observed=observed,
        possible_causes=[
            "A transform publisher (e.g. robot_state_publisher, static_transform_publisher, "
            "localization) is missing or not running",
            "Frame names differ between publishers (typo or missing prefix)",
            "Normal if separate trees are intentional or a transform is published slower than the listen window",
        ],
        recommended_checks=[f"ros2 run tf2_ros tf2_echo {comps[0][0]} {comps[1][0]}", "ros2 topic echo /tf_static"],
        confidence=0.6,
    )]


# R06 ------------------------------------------------------------------------
def r06_lifecycle_not_active(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    out = []
    for lc in s.lifecycle:
        if lc.state == "active":
            continue
        sev = Severity.ERROR if lc.state == "errorprocessing" else Severity.WARNING
        out.append(_f(
            "R06", sev, lc.node, f"Lifecycle node {lc.node} is '{lc.state}', not 'active'",
            observed=[f"{lc.node} reports lifecycle state '{lc.state}'"],
            possible_causes=[
                "The node has not been configured/activated by a lifecycle manager or launch file",
                "A transition failed (check the node's log)",
            ],
            recommended_checks=[f"ros2 lifecycle get {lc.node}", f"ros2 lifecycle list {lc.node}"],
            confidence=0.7,
        ))
    return out


# R07 ------------------------------------------------------------------------
def r07_action_server_unavailable(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    out, seen = [], set()
    by_name = {a.name: a for a in s.actions}
    for name in cfg.required_action_servers:
        a = by_name.get(_norm(name))
        if a is None or not a.servers:
            seen.add(_norm(name))
            out.append(_f(
                "R07", Severity.ERROR, _norm(name), f"Required action server {_norm(name)} is not available",
                observed=[f"{_norm(name)} has 0 action servers"
                          + (f" and {len(a.clients)} client(s)" if a else " and is not in the action list")],
                possible_causes=["The node hosting the action server is not running or not yet active"],
                recommended_checks=["ros2 action list", f"ros2 action info {_norm(name)}"],
                confidence=0.7))
    for a in s.actions:
        if a.clients and not a.servers and a.name not in seen:
            out.append(_f(
                "R07", Severity.WARNING, a.name, f"Action {a.name} has clients but no server",
                observed=[f"{a.name} has 0 servers", f"{len(a.clients)} client(s): {', '.join(a.clients)}"],
                possible_causes=["The action server node is not running or not active",
                                 "The action name differs (namespace/remap)"],
                recommended_checks=["ros2 action list", f"ros2 action info {a.name}"],
                confidence=0.65))
    return out


# R08 ------------------------------------------------------------------------
def r08_resources(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    if s.system is None:
        return []
    r = s.system
    checks = [("CPU", r.cpu_percent, cfg.cpu_warn_percent),
              ("Memory", r.memory_percent, cfg.memory_warn_percent),
              ("Disk", r.disk_percent, cfg.disk_warn_percent)]
    out = []
    for label, value, limit in checks:
        if value is not None and value >= limit:
            out.append(_f(
                "R08", Severity.WARNING, "system", f"{label} usage is high ({value:.1f}%)",
                observed=[f"{label} usage {value:.1f}% (threshold {limit:g}%)"],
                possible_causes=["A process is consuming excessive resources; this can cause "
                                 "dropped messages, missed deadlines or discovery timeouts"],
                recommended_checks=["ros2 doctor --report"], confidence=0.5))
    return out


# R09 ------------------------------------------------------------------------
def r09_domain_id(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    if cfg.expected_domain_id is None:
        return []
    actual = s.environment.ros_domain_id or "0"
    if actual == cfg.expected_domain_id:
        return []
    return [_f(
        "R09", Severity.WARNING, "environment",
        f"ROS_DOMAIN_ID is {actual}, expected {cfg.expected_domain_id}",
        observed=[f"ROS_DOMAIN_ID is {'unset (default 0)' if s.environment.ros_domain_id is None else actual}",
                  f"configured expectation: {cfg.expected_domain_id}"],
        possible_causes=["Nodes in a different domain cannot discover each other (DDS discovery issue)"],
        recommended_checks=["printenv ROS_DOMAIN_ID"], confidence=0.75)]


# R10 ------------------------------------------------------------------------
def r10_qos_mismatch(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    out = []
    for t in s.topics:
        mm = qos_mismatches(t)
        if not mm:
            continue
        out.append(_f(
            "R10", Severity.ERROR, t.name, f"Incompatible QoS between publisher(s) and subscriber(s) on {t.name}",
            observed=[f"{m.publisher} offers {m.policy.upper()}={m.offered}; "
                      f"{m.subscriber} requests {m.requested}" for m in mm],
            possible_causes=["Per the ROS 2 QoS compatibility rules, no messages are delivered "
                             "between these endpoints"],
            recommended_checks=[f"ros2 topic info {t.name} --verbose"], confidence=0.9))
    return out


# R11 ------------------------------------------------------------------------
def r11_controllers_not_active(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    if s.controllers is None:
        return []
    return [
        _f("R11", Severity.WARNING, c.name, f"Controller '{c.name}' is '{c.state}', not 'active'",
           observed=[f"controller_manager {s.controllers.manager} reports {c.name} ({c.type}) as {c.state}"],
           possible_causes=["The controller was loaded but not configured/activated, or a "
                            "hardware interface it claims is unavailable"],
           recommended_checks=["ros2 control list_controllers", "ros2 control list_hardware_interfaces"],
           confidence=0.7)
        for c in s.controllers.controllers if c.state != "active"
    ]


# R12 ------------------------------------------------------------------------
def r12_empty_graph(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    if s.nodes or any(e.startswith("nodes:") for e in s.collection_errors):
        return []
    env = s.environment
    return [_f(
        "R12", Severity.WARNING, "graph", "No ROS 2 nodes are visible",
        observed=["0 nodes discovered",
                  f"ROS_DOMAIN_ID={env.ros_domain_id or 'unset (default 0)'}",
                  f"ROS_LOCALHOST_ONLY={env.localhost_only or 'unset'}",
                  f"RMW_IMPLEMENTATION={env.rmw_implementation or 'unset (default)'}"],
        possible_causes=["No ROS 2 system is running",
                         "This shell uses a different ROS_DOMAIN_ID, RMW or ROS_LOCALHOST_ONLY setting "
                         "than the robot",
                         "Network/multicast prevents DDS discovery"],
        recommended_checks=["ros2 node list", "printenv ROS_DOMAIN_ID", "ros2 doctor --report"],
        confidence=0.5)]


# R13 ------------------------------------------------------------------------
def r13_log_errors(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    out = []
    for levels, sev, label in ((("ERROR", "FATAL"), Severity.WARNING, "error"),
                               (("WARN",), Severity.INFO, "warning")):
        entries = [e for e in s.logs if e.level in levels]
        if not entries:
            continue
        counts: dict[tuple[str, str], int] = {}
        for e in entries:
            counts[(e.logger, e.message)] = counts.get((e.logger, e.message), 0) + 1
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        out.append(_f(
            "R13", sev, "logs", f"{len(entries)} recent {label} log message(s) in /rosout",
            observed=[f"{n}x [{lg}] {msg}" for (lg, msg), n in top],
            possible_causes=["Log messages often name the failing component; they may or may not be "
                             "related to other findings"],
            recommended_checks=["ros2 topic echo /rosout"], confidence=0.4))
    return out


# R14 ------------------------------------------------------------------------
def r14_diagnostics(s: SystemSnapshot, cfg: ExpectedConfig) -> list[Finding]:
    return [
        _f("R14", Severity.WARNING, d.name, f"Diagnostic status for '{d.name}' is {d.level}",
           observed=[f"/diagnostics reports {d.name}: {d.level}" + (f" - {d.message}" if d.message else "")]
                    + [f"{k} = {v}" for k, v in sorted(d.values.items())[:5]],
           possible_causes=["The component's own diagnostic check failed; see its message"],
           recommended_checks=["ros2 topic echo /diagnostics"], confidence=0.5)
        for d in s.diagnostics if d.level != "OK"
    ]


ALL_RULES: list[Rule] = [
    r01_expected_publisher_missing, r02_unconsumed_topics, r03_missing_publisher,
    r04_required_node_missing, r05_tf_disconnected, r06_lifecycle_not_active,
    r07_action_server_unavailable, r08_resources, r09_domain_id, r10_qos_mismatch,
    r11_controllers_not_active, r12_empty_graph, r13_log_errors, r14_diagnostics,
]
