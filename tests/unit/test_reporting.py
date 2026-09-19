import json
from pathlib import Path

from ros2_ai_debugger import __version__
from ros2_ai_debugger.analyzers import analyze
from ros2_ai_debugger.models import Finding, Severity, SystemSnapshot
from ros2_ai_debugger.reporting import (
    AIStatus,
    Report,
    render_json,
    render_markdown,
    render_terminal,
)
from tests.fixtures.scenarios import broken_robot_snapshot

GOLDEN = Path(__file__).parent.parent / "fixtures" / "golden"


def broken_report(**kw) -> Report:
    s = broken_robot_snapshot()
    return Report(s, analyze(s), tool_version="{version}", **kw)


def test_markdown_matches_golden():
    assert render_markdown(broken_report(redacted=True)) == (GOLDEN / "broken_robot.md").read_text()


def test_terminal_matches_golden():
    assert render_terminal(broken_report()) == (GOLDEN / "broken_robot.txt").read_text()


def test_report_uses_real_version_by_default():
    s = broken_robot_snapshot()
    assert __version__ in render_markdown(Report(s, analyze(s)))


def test_json_report_structure_and_replay():
    r = broken_report()
    data = json.loads(render_json(r))
    assert data["overall"] == "warning" and data["tool"]["name"] == "ros2-ai-debugger"
    assert data["findings"][0]["component"] == "/joint_states"
    assert set(data["findings"][0]) == {"severity", "component", "problem", "observed", "possible_causes",
                                        "recommended_checks", "confidence", "source"}
    assert SystemSnapshot.from_dict(data["snapshot"]) == r.snapshot


def test_broken_robot_expected_findings_deterministic():
    """The reference scenario must yield exactly this diagnosis."""
    f = broken_report().rule_findings
    assert [(x.severity.label, x.component, x.source) for x in f] == [
        ("warning", "/joint_states", "rule:R03"), ("warning", "tf", "rule:R05"),
        ("info", "graph", "rule:R02"), ("info", "graph", "rule:R03"), ("info", "logs", "rule:R13")]


def test_healthy_report_and_overall_labels():
    r = Report(SystemSnapshot(collected_at="t"))
    assert r.overall() is None and r.overall_label() == "No issues detected"
    assert "No problems detected" in render_markdown(r)
    assert "✓ No issues detected" in render_terminal(r)
    assert "[OK] No issues detected" in render_terminal(r, unicode_ok=False)
    for sev, label in ((Severity.INFO, "Informational notes only"), (Severity.WARNING, "Potential issue detected"),
                       (Severity.ERROR, "Problems detected")):
        assert Report(SystemSnapshot(), rule_findings=[Finding(sev, "x", "p")]).overall_label() == label


def test_color_only_when_enabled():
    r = broken_report()
    assert "\033[" not in render_terminal(r, color=False)
    assert "\033[" in render_terminal(r, color=True)


def test_ai_sections_rendered():
    r = broken_report()
    r.ai_findings = [Finding(Severity.WARNING, "/joint_states", "AI says", ["obs"], ["cause"],
                             ["ros2 node list"], 0.7, "ai:claude")]
    r.ai = AIStatus("used", "claude", "claude (model: m)", "summary text", ["need logs"], ["dropped x"])
    text, md = render_terminal(r), render_markdown(r)
    for out in (text, md):
        assert "AI says" in out and "summary text" in out and "need logs" in out and "dropped x" in out
    assert "validated, not verified" in text


def test_ai_failure_reasons_shown():
    r = broken_report()
    r.ai = AIStatus("failed", "claude", "API key missing")
    assert "AI analysis failed: API key missing" in render_terminal(r)
    assert "Not used (failed: API key missing)" in render_markdown(r)


def test_commands_block_deduplicated():
    md = render_markdown(broken_report())
    block = md.split("## Relevant commands")[1]
    assert block.count("ros2 control list_controllers") == 1


def test_collection_errors_reported():
    r = Report(SystemSnapshot(collection_errors=["tf: RuntimeError: x"]))
    assert "tf: RuntimeError: x" in render_terminal(r) and "tf: RuntimeError: x" in render_markdown(r)
