from ros2_ai_debugger.models import (
    DiagnosticMessage,
    LogEntry,
    NetworkInterfaceInfo,
    SystemResourceInfo,
)
from ros2_ai_debugger.privacy import Redactor
from tests.fixtures.scenarios import broken_robot_snapshot


def test_secrets_always_scrubbed():
    r = Redactor(mask_identifiers=False)
    for secret in ["sk-ant-api03-abcdefghijklmnopqrstuvwx", "AIzaSyA1234567890abcdefghijklmn",
                   "ghp_abcdefghijklmnopqrstuvwxyz0123", "AKIAABCDEFGHIJKLMNOP",
                   "Bearer eyJhbGciOiJIUzI1NiJ9.abc.def"]:
        assert secret not in r.text(f"connecting with {secret} now")
    out = r.text("login password=hunter2 ok")
    assert "hunter2" not in out and "password=<redacted-secret>" in out
    assert "PRIVATE KEY" not in r.text("-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----")


def test_identifiers_only_masked_when_requested():
    text = "host 192.168.1.20 at /home/alice/ws mail bob@corp.com mac aa:bb:cc:dd:ee:ff"
    plain = Redactor(False, username="alice").text(text)
    assert "192.168.1.20" in plain and "alice" in plain
    masked = Redactor(True, username="alice").text(text)
    for leaked in ("192.168.1.20", "alice", "bob@corp.com", "aa:bb:cc:dd:ee:ff"):
        assert leaked not in masked
    assert "<ip-1>" in masked and "/home/<user>" in masked


def test_placeholders_are_stable():
    r = Redactor(True)
    assert r.text("10.0.0.1 10.0.0.2 10.0.0.1") == "<ip-1> <ip-2> <ip-1>"


def test_hostname_and_username_masked():
    r = Redactor(True, hostname="robot-pc", username="carol")
    masked = r.text("ssh carol@robot-pc")
    assert "carol" not in masked and "robot-pc" not in masked
    assert "robot-pc" not in r.text("on robot-pc failed")


def test_long_messages_truncated():
    assert len(Redactor().text("x" * 5000)) < 400


def test_snapshot_redaction_does_not_mutate_input_and_keeps_graph_names():
    snap = broken_robot_snapshot()
    snap.logs.append(LogEntry("ERROR", "/x", "token=abc123 from 10.1.2.3", 5))
    snap.diagnostics.append(DiagnosticMessage("motor", "OK", "fine", "SN-991", {"serial_number": "ZX81", "temp": "40"}))
    snap.system = SystemResourceInfo(network=[NetworkInterfaceInfo("eth0", "up", "10.1.2.3")])
    before = snap.to_dict()
    red = Redactor(True, hostname="robot-pc").snapshot(snap)
    assert snap.to_dict() == before
    dump = str(red.to_dict())
    assert "abc123" not in dump and "10.1.2.3" not in dump and "robot-pc" not in dump
    assert "SN-991" not in dump and "ZX81" not in dump
    assert red.diagnostics[0].values["temp"] == "40"
    assert [n.name for n in red.nodes] == [n.name for n in snap.nodes]
    assert red.environment.hostname == "<host>"
