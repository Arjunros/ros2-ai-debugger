import io
import json

import pytest

from ros2_ai_debugger.analyzers.ai_prompt import SYSTEM_PROMPT
from ros2_ai_debugger.cli.diagnose import run_diagnose
from ros2_ai_debugger.cli.main import add_subcommands
from ros2_ai_debugger.providers import AIProvider, ProviderError
from tests.fixtures.fake_backend import broken_robot_backend
import argparse

REPLY = json.dumps({"summary": "Broadcaster missing.", "missing_information": ["hardware logs"], "findings": [{
    "severity": "warning", "component": "/joint_states", "problem": "no joint state source",
    "observed": ["/joint_states has 0 publishers"], "possible_causes": ["broadcaster inactive"],
    "recommended_checks": ["ros2 control list_controllers", "ros2 topic pub /x y"], "confidence": 0.8}]})


class FakeProvider(AIProvider):
    name, default_model = "fake", "fake-1"

    def __init__(self, reply=REPLY, local=False, configured=True, **_):
        super().__init__()
        self.reply, self._local, self._configured, self.calls = reply, local, configured, []

    @property
    def is_local(self):
        return self._local

    def is_configured(self):
        return self._configured

    def config_help(self):
        return "set FAKE_KEY"

    def complete(self, system, user):
        self.calls.append((system, user))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class FakeCtx:
    def __enter__(self):
        return broken_robot_backend()

    def __exit__(self, *a):
        pass


def cli(*argv, provider=None, confirm=None, tmp=None):
    parser = argparse.ArgumentParser()
    add_subcommands(parser)
    args = parser.parse_args(["diagnose", *argv])
    out, err = io.StringIO(), io.StringIO()
    factory = (lambda name, model=None, **kw: provider) if provider else (lambda *a, **k: None)
    rc = run_diagnose(args, out=out, err=err, backend_factory=lambda s: FakeCtx(),
                      provider_factory=factory, confirm=confirm)
    return rc, out.getvalue(), err.getvalue()


def test_default_is_rule_based_and_sends_nothing():
    p = FakeProvider()
    rc, out, err = cli(provider=p)
    assert rc == 0 and "FINDING #1" in out and "/joint_states" in out and p.calls == []
    assert "AI analysis not enabled" in out


def test_no_ai_flag():
    assert cli("--no-ai")[0] == 0


def test_fail_on():
    assert cli("--fail-on", "warning")[0] == 1
    assert cli("--fail-on", "error")[0] == 0


def test_expectations_add_findings():
    rc, out, _ = cli("--expect-node", "/nav2", "--expect-domain-id", "42")
    assert "Required node /nav2 is not running" in out and "ROS_DOMAIN_ID" in out


def test_config_file(tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"required_nodes": ["/gripper"]}))
    assert "/gripper" in cli("--config", str(cfg))[1]
    cfg.write_text(json.dumps({"bogus": 1}))
    rc, _, err = cli("--config", str(cfg))
    assert rc == 2 and "unknown config keys" in err
    assert cli("--config", str(tmp_path / "missing.json"))[0] == 2


@pytest.mark.parametrize("argv,msg", [
    (["--no-ai", "--provider", "claude"], "--no-ai"),
    (["--dry-run"], "--provider"),
    (["--local", "--provider", "claude"], "--local only works"),
    (["--output", "r.txt"], ".md or .json"),
    (["--github", "--output", "r.json"], "Markdown"),
    (["--listen-seconds", "-1"], "listen-seconds"),
])
def test_usage_errors(argv, msg):
    rc, _, err = cli(*argv)
    assert rc == 2 and msg in err


def test_json_stdout_and_snapshot_replay(tmp_path):
    rc, out, _ = cli("--format", "json")
    data = json.loads(out)
    assert rc == 0 and data["findings"][0]["component"] == "/joint_states"
    f = tmp_path / "s.json"
    f.write_text(out)
    rc2, out2, err2 = cli("--from-snapshot", str(f), "--format", "json")
    assert rc2 == 0 and "Collecting" not in err2
    assert json.loads(out2)["findings"] == data["findings"]


def test_from_snapshot_errors(tmp_path):
    assert cli("--from-snapshot", str(tmp_path / "nope.json"))[0] == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{oops")
    assert cli("--from-snapshot", str(bad))[0] == 2


def test_markdown_output_file_is_redacted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "r.md"
    rc, stdout, _ = cli("--output", str(out))
    text = out.read_text()
    assert rc == 0 and text.startswith("# ROS 2 AI Diagnostic Report") and "Report written" in stdout
    assert "Hostnames, IP addresses" in text


def test_json_output_file(tmp_path):
    out = tmp_path / "r.json"
    assert cli("--output", str(out))[0] == 0
    assert json.loads(out.read_text())["tool"]["name"] == "ros2-ai-debugger"


def test_github_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc, out, _ = cli("--github")
    assert rc == 0 and (tmp_path / "github-report.md").exists() and "github-report.md" in out


def test_unwritable_output(tmp_path):
    rc, _, err = cli("--output", str(tmp_path / "no" / "such" / "r.md"))
    assert rc == 2 and "cannot write" in err


def test_redact_masks_identifiers_in_terminal_output(monkeypatch):
    import ros2_ai_debugger.cli.diagnose as d
    orig = d.collect_snapshot

    def with_leaks(*a, **k):
        s = orig(*a, **k)
        s.logs[0].message = "cannot reach 10.20.30.40 token=SECRETVALUE"
        s.environment.hostname = "my-robot-host"
        return s

    monkeypatch.setattr(d, "collect_snapshot", with_leaks)
    _, out, _ = cli("--format", "json", "--redact")
    assert "10.20.30.40" not in out and "SECRETVALUE" not in out and "my-robot-host" not in out
    _, out2, _ = cli("--format", "json")  # secrets scrubbed even without --redact; IP kept
    assert "SECRETVALUE" not in out2 and "10.20.30.40" in out2


# ---- AI stage ---------------------------------------------------------------
def test_dry_run_prints_payload_and_never_calls_provider(monkeypatch):
    monkeypatch.setenv("SECRET_ENV_VAR", "hunter2-do-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-do-not-leak-0123456789")
    p = FakeProvider()
    rc, out, _ = cli("--provider", "claude", "--dry-run", provider=p)
    assert rc == 0 and p.calls == []
    assert "DRY RUN" in out and SYSTEM_PROMPT.splitlines()[0] in out and '"/joint_states"' in out
    assert "hunter2-do-not-leak" not in out and "do-not-leak-0123" not in out
    assert "NOT sent" in out


def test_cloud_requires_confirmation_non_interactive_declines():
    p = FakeProvider()
    rc, out, err = cli("--provider", "claude", provider=p)
    assert rc == 0 and p.calls == [] and "About to send" in err and "pass --yes" in err
    assert "AI analysis skipped" in out


def test_cloud_confirm_yes_flag_and_prompt():
    p = FakeProvider()
    rc, out, err = cli("--provider", "claude", "--yes", provider=p)
    assert len(p.calls) == 1 and "AI FINDINGS" in out and "Broadcaster missing." in out
    assert "About to send" in err  # summary still shown
    p2 = FakeProvider()
    cli("--provider", "claude", provider=p2, confirm=lambda q: True)
    assert len(p2.calls) == 1
    p3 = FakeProvider()
    cli("--provider", "claude", provider=p3, confirm=lambda q: False)
    assert p3.calls == []


def test_ai_output_is_validated_before_display():
    _, out, _ = cli("--provider", "claude", "--yes", provider=FakeProvider())
    assert "ros2 topic pub" not in out
    assert "not on the read-only allowlist" in out


def test_invented_component_never_displayed():
    reply = json.dumps({"findings": [{"severity": "error", "component": "/ghost", "problem": "x",
                                      "observed": [], "possible_causes": [], "recommended_checks": [],
                                      "confidence": 0.9}]})
    _, out, _ = cli("--provider", "claude", "--yes", provider=FakeProvider(reply))
    assert "/ghost" not in out.split("AI analysis:")[0] and "unknown component" in out


def test_local_needs_no_confirmation():
    p = FakeProvider(local=True)
    rc, out, err = cli("--local", provider=p)
    assert len(p.calls) == 1 and "About to send" not in err


def test_missing_api_key_falls_back_to_rules():
    p = FakeProvider(configured=False)
    rc, out, err = cli("--provider", "claude", "--yes", provider=p)
    assert rc == 0 and p.calls == [] and "FINDING #1" in out
    assert "provider not configured (set FAKE_KEY)" in out


@pytest.mark.parametrize("reply", ["not json at all", ProviderError("HTTP 500 from x"), "{}"])
def test_ai_failure_keeps_rule_results(reply):
    rc, out, err = cli("--provider", "claude", "--yes", provider=FakeProvider(reply))
    assert rc == 0 and "FINDING #1" in out and "AI analysis failed" in out


def test_provider_construction_error(monkeypatch):
    def factory(name, model=None, **kw):
        raise ProviderError("unknown provider")

    parser = argparse.ArgumentParser()
    add_subcommands(parser)
    args = parser.parse_args(["diagnose", "--provider", "claude"])
    err = io.StringIO()
    assert run_diagnose(args, out=io.StringIO(), err=err, backend_factory=lambda s: FakeCtx(),
                        provider_factory=factory) == 2
