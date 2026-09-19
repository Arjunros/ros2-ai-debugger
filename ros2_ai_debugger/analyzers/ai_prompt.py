"""Prompt and payload construction for AI analysis (provider independent)."""
from __future__ import annotations

import json
from dataclasses import dataclass

from ros2_ai_debugger.models import Finding, SystemSnapshot

MAX_LOG_ENTRIES = 30

SYSTEM_PROMPT = """\
You are a ROS 2 diagnostics assistant. You receive a JSON snapshot of a running ROS 2 \
system (collected read-only) and findings from a deterministic rule engine. Your job is \
to add evidence-based analysis, not to guess.

Rules you MUST follow:
1. Use ONLY the nodes, topics, services, actions, controllers and frames present in the \
snapshot. Never invent or assume any that are not listed.
2. Keep observation and inference separate. "observed" holds only facts literally present \
in the snapshot. "possible_causes" holds inferences and must be phrased as possibilities. \
Never state an inference as a confirmed fact.
3. Group related symptoms into one finding rather than repeating them.
4. Do not repeat rule-engine findings verbatim; add cross-cutting reasoning, correlations \
between findings, or additional anomalies the rules did not cover.
5. "recommended_checks" must be read-only ROS 2 CLI commands (for example `ros2 topic info \
/x`, `ros2 node info /y`, `ros2 control list_controllers`). Never recommend commands that \
change state (publish, set parameters, kill, restart, call services).
6. Confidence is a number from 0 to 1 for the top possible cause. Be conservative; if the \
evidence is thin, use a low value.
7. List information that is missing and would change your diagnosis in "missing_information".
8. If the system looks healthy, return an empty "findings" list.

Reply with a single JSON object and nothing else, in exactly this shape:
{
  "summary": "one or two sentences",
  "findings": [
    {
      "severity": "info" | "warning" | "error",
      "component": "an existing node/topic/service/action/controller name, or one of: system, graph, tf, logs, environment",
      "problem": "short statement of the problem",
      "observed": ["fact from the snapshot", "..."],
      "possible_causes": ["possible cause phrased as a possibility", "..."],
      "recommended_checks": ["ros2 ..."],
      "confidence": 0.0
    }
  ],
  "missing_information": ["..."]
}
"""


def build_payload(snapshot: SystemSnapshot, rule_findings: list[Finding]) -> dict:
    """The exact data sent to a provider: normalized snapshot + rule findings."""
    data = snapshot.to_dict()
    data["logs"] = data["logs"][-MAX_LOG_ENTRIES:]
    return {"snapshot": data, "rule_findings": [f.to_dict() for f in rule_findings]}


def build_user_prompt(payload: dict) -> str:
    return "Analyze this ROS 2 system snapshot.\n\n" + json.dumps(payload, indent=1, sort_keys=True)


@dataclass
class PayloadSummary:
    """Human-readable description of what a cloud request would contain."""

    sections: dict[str, int]
    size_bytes: int
    redaction: str

    def lines(self) -> list[str]:
        items = ", ".join(f"{n} {k}" for k, n in self.sections.items() if n)
        return [
            f"Contents: {items or 'environment and system metrics only'}",
            f"Approximate size: {self.size_bytes / 1024:.1f} KiB",
            f"Redaction: {self.redaction}",
            "NOT sent: environment variables other than ROS_DISTRO/ROS_DOMAIN_ID/RMW_IMPLEMENTATION/"
            "ROS_LOCALHOST_ONLY, API keys, file contents, camera images or other message payloads, "
            "robot credentials.",
        ]


def summarize_payload(payload: dict, mask_identifiers: bool) -> PayloadSummary:
    snap = payload["snapshot"]
    sections = {
        "nodes": len(snap["nodes"]), "topics": len(snap["topics"]),
        "services": len(snap["services"]), "actions": len(snap["actions"]),
        "lifecycle states": len(snap["lifecycle"]),
        "TF edges": len(snap["tf"]["edges"]) if snap.get("tf") else 0,
        "controllers": len(snap["controllers"]["controllers"]) if snap.get("controllers") else 0,
        "diagnostic statuses": len(snap["diagnostics"]),
        "log entries": len(snap["logs"]), "rule findings": len(payload["rule_findings"]),
    }
    return PayloadSummary(
        sections=sections,
        size_bytes=len(build_user_prompt(payload).encode()) + len(SYSTEM_PROMPT.encode()),
        redaction=("secrets scrubbed; hostnames/IPs/MACs/usernames/paths masked"
                   if mask_identifiers else
                   "secrets scrubbed only (use --redact to also mask hostnames, IPs, usernames, paths)"),
    )
