"""Plain-terminal report."""
from __future__ import annotations

from ros2_ai_debugger.models import Finding, Severity
from ros2_ai_debugger.reporting.report import Report

_COLORS = {Severity.INFO: "36", Severity.WARNING: "33", Severity.ERROR: "31"}


def render_terminal(report: Report, color: bool = False, unicode_ok: bool = True) -> str:
    def paint(text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if color else text

    icons = ({None: "✓", Severity.INFO: "ℹ", Severity.WARNING: "⚠", Severity.ERROR: "✗"}
             if unicode_ok else
             {None: "[OK]", Severity.INFO: "[i]", Severity.WARNING: "[!]", Severity.ERROR: "[X]"})
    sev = report.overall()
    env = report.snapshot.environment
    lines = [paint("ROS 2 AI DIAGNOSTIC REPORT", "1"), "",
             "System:",
             f"  ROS 2 {env.ros_distro.capitalize() if env.ros_distro else '(distro unknown)'}",
             f"  {env.os_name or 'OS unknown'}",
             f"  Nodes: {len(report.snapshot.nodes)}  Topics: {len(report.snapshot.topics)}  "
             f"Services: {len(report.snapshot.services)}  Actions: {len(report.snapshot.actions)}",
             "", "Overall:",
             "  " + paint(f"{icons[sev]} {report.overall_label()}", _COLORS.get(sev, "32"))]
    n = 0
    for title, findings in (("RULE-BASED FINDINGS (deterministic)", report.rule_findings),
                            (f"AI FINDINGS ({report.ai.provider}; validated, not verified)",
                             report.ai_findings)):
        if not findings:
            continue
        lines += ["", paint(title, "1")]
        for f in findings:
            n += 1
            lines += [""] + _finding(n, f, paint)
    lines += [""] + _ai_section(report)
    if report.snapshot.collection_errors:
        lines += ["", "Collection problems (data may be incomplete):"]
        lines += [f"  - {e}" for e in report.snapshot.collection_errors]
    return "\n".join(lines).rstrip() + "\n"


def _finding(n: int, f: Finding, paint) -> list[str]:
    out = [paint(f"FINDING #{n}  [{f.severity.label.upper()}]", _COLORS[f.severity]),
           f"Component:  {f.component}", f"Problem:    {f.problem}", "",
           "OBSERVED (read directly from the system):"]
    out += [f"  - {o}" for o in f.observed] or ["  (nothing specific)"]
    if f.possible_causes:
        out += ["", "INFERRED (possible causes, NOT confirmed):"]
        out += [f"  {i}. {c}" for i, c in enumerate(f.possible_causes, 1)]
    if f.recommended_checks:
        out += ["", "RECOMMENDED (read-only checks):"]
        out += [f"  $ {c}" for c in f.recommended_checks]
    out += ["", f"Confidence: {f.confidence:.2f} (heuristic weight for the top possible cause)",
            f"Source:     {f.source}"]
    return out


def _ai_section(report: Report) -> list[str]:
    ai = report.ai
    if ai.mode == "used":
        out = [f"AI analysis: {ai.detail}"]
        if ai.summary:
            out.append(f"  Summary: {ai.summary}")
        if ai.missing_information:
            out += ["  Missing information the AI asked for:"] + [f"    - {m}" for m in ai.missing_information]
        if ai.warnings:
            out += ["  Validation removed unsupported AI output:"] + [f"    - {w}" for w in ai.warnings]
        return out
    reason = {"disabled": "AI analysis not enabled", "failed": "AI analysis failed",
              "declined": "AI analysis skipped"}[ai.mode]
    out = [f"{reason}" + (f": {ai.detail}" if ai.detail else "") + "."]
    if ai.mode == "disabled" and not ai.detail:
        out[0] = "AI analysis not enabled. Add --local (Ollama) or --provider <name> to enable it."
    return out
