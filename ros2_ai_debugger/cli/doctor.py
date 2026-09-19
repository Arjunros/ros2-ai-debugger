"""`ros2 ai doctor`: checks that the tool itself can work here. Never prints secrets."""
from __future__ import annotations

import importlib
import importlib.metadata
import os
import sys
from typing import TextIO

from ros2_ai_debugger import __version__
from ros2_ai_debugger.providers import (
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
)
from ros2_ai_debugger.utils.distro import SUPPORTED_DISTROS

OK, WARN, FAIL = "ok", "warn", "FAIL"


def _module(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def run_checks(environ=None) -> list[tuple[str, str, str]]:
    env = os.environ if environ is None else environ
    checks: list[tuple[str, str, str]] = []

    def add(status: str, name: str, detail: str) -> None:
        checks.append((status, name, detail))

    py = sys.version_info
    add(OK if py >= (3, 10) else FAIL, "Python", f"{py.major}.{py.minor}.{py.micro} (need >= 3.10)")

    distro = env.get("ROS_DISTRO")
    if not distro:
        add(FAIL, "ROS 2 environment", "ROS_DISTRO is not set; run `source /opt/ros/<distro>/setup.bash`")
    elif distro in SUPPORTED_DISTROS:
        add(OK, "ROS 2 distribution", f"{distro} (supported)")
    else:
        add(WARN, "ROS 2 distribution", f"{distro} is not tested; supported: {', '.join(SUPPORTED_DISTROS)}")

    has_rclpy = _module("rclpy")
    add(OK if has_rclpy else FAIL, "rclpy", "importable" if has_rclpy else "not importable (source ROS 2)")
    for mod, why in (("tf2_msgs", "TF collection"), ("diagnostic_msgs", "/diagnostics"),
                     ("rcl_interfaces", "/rosout logs"), ("lifecycle_msgs", "lifecycle state")):
        add(OK if _module(mod) else WARN, mod, "available" if _module(mod) else f"missing: {why} disabled")
    add(OK if _module("controller_manager_msgs") else WARN, "controller_manager_msgs",
        "available" if _module("controller_manager_msgs") else "missing: ros2_control controller info unavailable")

    try:
        eps = importlib.metadata.entry_points()
        group = eps.select(group="ros2cli.command") if hasattr(eps, "select") else eps.get("ros2cli.command", [])
        registered = any(e.name == "ai" for e in group)
    except Exception:  # noqa: BLE001
        registered = False
    add(OK if registered else WARN, "`ros2 ai` registration",
        "registered with ros2cli" if registered else "not found by this Python; use `ros2-ai` or re-install")

    dom = env.get("ROS_DOMAIN_ID")
    if dom is not None:
        valid = dom.isdigit() and 0 <= int(dom) <= 232
        add(OK if valid else FAIL, "ROS_DOMAIN_ID", f"{dom}" + ("" if valid else " (must be 0-232)"))

    for prov in (ClaudeProvider(), OpenAIProvider(), GeminiProvider()):
        configured = prov.is_configured()
        add(OK if configured else WARN, f"provider {prov.name}",
            "API key present" if configured else f"not configured ({prov.config_help()})")
    if _module("anthropic"):
        add(OK, "anthropic SDK", "installed")
    else:
        add(WARN, "anthropic SDK", "not installed (only needed for --provider claude)")
    ollama = OllamaProvider()
    try:
        models = ollama.installed_models()
        add(OK, "provider ollama", f"reachable at {ollama.host}; models: {', '.join(models) or 'none pulled'}")
    except Exception:  # noqa: BLE001
        add(WARN, "provider ollama", f"not reachable at {ollama.host} (needed for --local)")
    return checks


def run_doctor(out: TextIO | None = None) -> int:
    out = out or sys.stdout
    print(f"ros2-ai-debugger {__version__} doctor\n", file=out)
    checks = run_checks()
    for status, name, detail in checks:
        print(f"  [{status:>4}] {name}: {detail}", file=out)
    failed = [c for c in checks if c[0] == FAIL]
    print("\nRule-based diagnosis works without any AI provider." if not failed else
          f"\n{len(failed)} required check(s) failed.", file=out)
    return 1 if failed else 0
