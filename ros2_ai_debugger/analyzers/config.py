"""User-supplied expectations for the rule-based analyzer."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExpectedConfig:
    """What the user *expects* the system to look like.

    Rules 1, 4, 7 (required servers) and 9 only fire when the matching
    expectation is provided; the tool never guesses what your robot needs.
    """

    required_nodes: list[str] = field(default_factory=list)
    #: topic -> nodes expected to publish it
    expected_publishers: dict[str, list[str]] = field(default_factory=dict)
    required_action_servers: list[str] = field(default_factory=list)
    expected_domain_id: str | None = None
    cpu_warn_percent: float = 90.0
    memory_warn_percent: float = 90.0
    disk_warn_percent: float = 90.0

    @classmethod
    def from_file(cls, path: str | Path) -> "ExpectedConfig":
        """Load a JSON file; unknown keys are an error to catch typos early."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        known = set(cls.__dataclass_fields__)
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}; valid keys: {sorted(known)}")
        if data.get("expected_domain_id") is not None:
            data["expected_domain_id"] = str(data["expected_domain_id"])
        return cls(**data)
