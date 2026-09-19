"""Strict validation of AI output before anything is shown to the user.

The model output is untrusted input. A finding is kept only if it is
well-formed, refers to components that exist in the snapshot, and contains
only allowlisted read-only commands. Everything dropped is reported.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ros2_ai_debugger.models import Finding, Severity, SystemSnapshot
from ros2_ai_debugger.utils.commands import is_read_only_command

GENERIC_COMPONENTS = {"system", "graph", "tf", "logs", "environment"}
MAX_ITEMS = 10
MAX_TEXT = 500
_NAME = re.compile(r"^/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*$")


class AIResponseError(ValueError):
    """The response was not usable at all (not JSON / wrong top-level shape)."""


@dataclass
class AIResult:
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""
    missing_information: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # what validation dropped or changed


def known_names(snap: SystemSnapshot) -> set[str]:
    """Every ROS name in the snapshot, with and without a leading slash."""
    names: set[str] = set()
    names |= {n.name for n in snap.nodes}
    names |= {t.name for t in snap.topics}
    names |= {s.name for s in snap.services}
    names |= {a.name for a in snap.actions}
    names |= {l.node for l in snap.lifecycle}
    if snap.controllers:
        names.add(snap.controllers.manager)
        names |= {c.name for c in snap.controllers.controllers}
    if snap.tf:
        names |= set(snap.tf.frames())
    names |= {d.name for d in snap.diagnostics}
    return names | {"/" + n.lstrip("/") for n in names} | {n.lstrip("/") for n in names}


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise AIResponseError("response contains no JSON object")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise AIResponseError(f"response is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise AIResponseError("response must be an object with a 'findings' list")
    return data


def _strings(value, what: str, warnings: list[str]) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return None
    if len(value) > MAX_ITEMS:
        warnings.append(f"{what}: truncated to {MAX_ITEMS} items")
    return [v.strip()[:MAX_TEXT] for v in value[:MAX_ITEMS] if v.strip()]


def _unknown_names(text: str, known: set[str]) -> list[str]:
    """Slash-prefixed tokens in ``text`` that look like ROS names but are not in the snapshot."""
    bad = []
    for tok in text.split():
        tok = tok.strip("'\"`.,;:()[]")
        if _NAME.match(tok) and tok not in known:
            bad.append(tok)
    return bad


def validate_ai_response(text: str, snapshot: SystemSnapshot, source: str = "ai") -> AIResult:
    """Parse and validate model output. Raises :class:`AIResponseError` if unusable."""
    data = _extract_json(text)
    known = known_names(snapshot)
    result = AIResult()
    if isinstance(data.get("summary"), str):
        result.summary = data["summary"].strip()[:MAX_TEXT]
    missing = _strings(data.get("missing_information", []), "missing_information", result.warnings)
    result.missing_information = missing or []

    for i, raw in enumerate(data["findings"][:MAX_ITEMS], 1):
        tag = f"finding {i}"
        if not isinstance(raw, dict):
            result.warnings.append(f"{tag}: dropped (not an object)")
            continue
        try:
            severity = Severity.parse(raw["severity"])
            component = raw["component"].strip()
            problem = (raw.get("problem") or raw["possible_causes"][0]).strip()[:MAX_TEXT]
            confidence = float(raw["confidence"])
        except (KeyError, ValueError, TypeError, AttributeError, IndexError):
            result.warnings.append(f"{tag}: dropped (missing or invalid severity/component/confidence)")
            continue
        if isinstance(raw["confidence"], bool) or not 0.0 <= confidence <= 1.0:
            result.warnings.append(f"{tag}: dropped (confidence outside 0-1)")
            continue
        if component not in GENERIC_COMPONENTS and component not in known:
            result.warnings.append(f"{tag}: dropped (unknown component {component!r} not in snapshot)")
            continue
        observed = _strings(raw.get("observed", []), f"{tag} observed", result.warnings)
        causes = _strings(raw.get("possible_causes", []), f"{tag} possible_causes", result.warnings)
        checks = _strings(raw.get("recommended_checks", []), f"{tag} recommended_checks", result.warnings)
        if observed is None or causes is None or checks is None:
            result.warnings.append(f"{tag}: dropped (observed/possible_causes/recommended_checks must be lists of strings)")
            continue
        kept_obs = []
        for o in observed:
            bad = _unknown_names(o, known)
            if bad:
                result.warnings.append(f"{tag}: dropped observation citing unknown name(s) {bad}")
            else:
                kept_obs.append(o)
        kept_checks = []
        for c in checks:
            if not is_read_only_command(c):
                # Deliberately not echoed: a rejected command must never appear where it could be copy-pasted.
                result.warnings.append(f"{tag}: dropped a recommended command that is not on the read-only allowlist")
            elif _unknown_names(c, known):
                result.warnings.append(f"{tag}: dropped a recommended command citing names not in the snapshot")
            else:
                kept_checks.append(c)
        result.findings.append(Finding(
            severity=severity, component=component, problem=problem, observed=kept_obs,
            possible_causes=causes, recommended_checks=kept_checks,
            confidence=round(confidence, 2), source=source))
    dropped = len(data["findings"]) - len(data["findings"][:MAX_ITEMS])
    if dropped:
        result.warnings.append(f"{dropped} finding(s) beyond the first {MAX_ITEMS} ignored")
    return result
