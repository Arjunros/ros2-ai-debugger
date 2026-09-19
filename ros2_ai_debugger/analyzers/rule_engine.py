"""Runs all rules and returns findings in a stable order."""
from __future__ import annotations

from ros2_ai_debugger.analyzers.config import ExpectedConfig
from ros2_ai_debugger.analyzers.rules import ALL_RULES
from ros2_ai_debugger.models import Finding, SystemSnapshot


def analyze(snapshot: SystemSnapshot, config: ExpectedConfig | None = None) -> list[Finding]:
    """Apply every deterministic rule. Output order: severity (high first), rule, component."""
    cfg = config or ExpectedConfig()
    findings: list[Finding] = []
    for rule in ALL_RULES:
        findings.extend(rule(snapshot, cfg))
    findings.sort(key=lambda f: (-int(f.severity), f.source, f.component))
    return findings
