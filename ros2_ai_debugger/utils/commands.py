"""Allowlist of read-only commands the tool may *recommend*.

The tool never executes recommendations. This filter exists so that neither a
rule bug nor an LLM can put a state-changing command (``ros2 topic pub``,
``ros2 param set``, ``kill`` ...) into a report as a "recommended check".
"""
from __future__ import annotations

import re
import shlex

_READ_ONLY_VERBS: dict[str, set[str]] = {
    "topic": {"list", "info", "echo", "hz", "bw", "type", "find", "delay"},
    "node": {"list", "info"},
    "service": {"list", "type", "find"},
    "action": {"list", "info", "type"},
    "param": {"list", "get", "describe", "dump"},
    "lifecycle": {"get", "list", "nodes"},
    "control": {
        "list_controllers", "list_hardware_components", "list_hardware_interfaces",
        "view_controller_chains",
    },
    "pkg": {"list", "prefix", "executables"},
    "interface": {"list", "show", "package", "packages"},
    "component": {"list"},
    "daemon": {"status"},
}
_NO_VERB = {"doctor", "wtf"}
# `ros2 run` executes programs, so only these exact read-only tools are allowed.
_RUN_ALLOWED = {("tf2_ros", "tf2_echo"), ("tf2_ros", "tf2_monitor")}
_PRINTENV_ALLOWED = {"ROS_DOMAIN_ID", "ROS_DISTRO", "RMW_IMPLEMENTATION", "ROS_LOCALHOST_ONLY"}
_SHELL_META = re.compile(r"[;&|`$<>(){}\\\n]")


def is_read_only_command(command: str) -> bool:
    """True only for a single, plain, known read-only command."""
    if not command or _SHELL_META.search(command):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return False
    if tokens[0] == "printenv":
        return len(tokens) == 2 and tokens[1] in _PRINTENV_ALLOWED
    if tokens[0] != "ros2" or len(tokens) < 2:
        return False
    group = tokens[1]
    if group in _NO_VERB:
        return True
    if group == "run":
        return len(tokens) >= 4 and (tokens[2], tokens[3]) in _RUN_ALLOWED
    verbs = _READ_ONLY_VERBS.get(group)
    return bool(verbs) and len(tokens) >= 3 and tokens[2] in verbs
