"""Report data structure shared by all renderers."""
from __future__ import annotations

from dataclasses import dataclass, field

from ros2_ai_debugger import __version__
from ros2_ai_debugger.models import Finding, Severity, SystemSnapshot


@dataclass
class AIStatus:
    """What happened with the optional AI stage."""

    mode: str = "disabled"  # disabled | used | failed | declined
    provider: str = ""
    detail: str = ""  # reason for disabled/failed/declined, or model description
    summary: str = ""
    missing_information: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # output dropped by validation


@dataclass
class Report:
    snapshot: SystemSnapshot
    rule_findings: list[Finding] = field(default_factory=list)
    ai_findings: list[Finding] = field(default_factory=list)
    ai: AIStatus = field(default_factory=AIStatus)
    tool_version: str = __version__
    #: True when identifiers were masked; stated in shareable reports.
    redacted: bool = False

    @property
    def generated_at(self) -> str:
        return self.snapshot.collected_at

    @property
    def findings(self) -> list[Finding]:
        return self.rule_findings + self.ai_findings

    def overall(self) -> Severity | None:
        return max((f.severity for f in self.findings), default=None)

    def overall_label(self) -> str:
        sev = self.overall()
        return {
            None: "No issues detected",
            Severity.INFO: "Informational notes only",
            Severity.WARNING: "Potential issue detected",
            Severity.ERROR: "Problems detected",
        }[sev]

    def all_commands(self) -> list[str]:
        seen: dict[str, None] = {}
        for f in self.findings:
            for c in f.recommended_checks:
                seen.setdefault(c)
        return list(seen)
