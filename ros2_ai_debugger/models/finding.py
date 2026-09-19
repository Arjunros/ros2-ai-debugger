"""A diagnostic finding, produced by rules or (validated) by an AI provider."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    INFO = 0
    WARNING = 1
    ERROR = 2

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def parse(cls, text: str) -> Severity:
        return cls[text.strip().upper()]


@dataclass
class Finding:
    """One problem, keeping observation, inference and recommendation apart.

    ``observed``          facts read directly from the system.
    ``possible_causes``   inferences; never confirmed facts.
    ``recommended_checks`` read-only commands the user may run.
    ``confidence``        heuristic weight (0-1) for the top inferred cause;
                          NOT a calibrated probability.
    """

    severity: Severity
    component: str
    problem: str
    observed: list[str] = field(default_factory=list)
    possible_causes: list[str] = field(default_factory=list)
    recommended_checks: list[str] = field(default_factory=list)
    confidence: float = 0.5
    source: str = "rule"  # "rule:R03" or "ai:<provider>"

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.label,
            "component": self.component,
            "problem": self.problem,
            "observed": list(self.observed),
            "possible_causes": list(self.possible_causes),
            "recommended_checks": list(self.recommended_checks),
            "confidence": self.confidence,
            "source": self.source,
        }
