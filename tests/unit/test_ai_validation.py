import json

import pytest

from ros2_ai_debugger.analyzers.ai_prompt import (
    SYSTEM_PROMPT, build_payload, build_user_prompt, summarize_payload,
)
from ros2_ai_debugger.analyzers.ai_validation import AIResponseError, known_names, validate_ai_response
from ros2_ai_debugger.analyzers import analyze
from ros2_ai_debugger.models import Severity
from tests.fixtures.scenarios import broken_robot_snapshot

SNAP = broken_robot_snapshot()


def good(**over):
    f = {"severity": "warning", "component": "/joint_states", "problem": "no publisher",
         "observed": ["/joint_states has 0 publishers"],
         "possible_causes": ["joint_state_broadcaster inactive"],
         "recommended_checks": ["ros2 control list_controllers"], "confidence": 0.82}
    f.update(over)
    return f


def wrap(*findings, **extra):
    return json.dumps({"findings": list(findings), **extra})


def test_valid_response_accepted():
    r = validate_ai_response(wrap(good(), summary="s", missing_information=["hardware logs"]), SNAP, "ai:x")
    assert len(r.findings) == 1 and r.warnings == []
    f = r.findings[0]
    assert f.severity == Severity.WARNING and f.source == "ai:x" and f.confidence == 0.82
    assert r.summary == "s" and r.missing_information == ["hardware logs"]


def test_markdown_fenced_and_chatty_json_accepted():
    text = "Sure! Here you go:\n```json\n" + wrap(good()) + "\n```\nHope it helps"
    assert len(validate_ai_response(text, SNAP).findings) == 1


@pytest.mark.parametrize("text", ["", "no json here", "{not json}", "[1,2]", '{"findings": "x"}', '{"a": 1}'])
def test_unusable_responses_raise(text):
    with pytest.raises(AIResponseError):
        validate_ai_response(text, SNAP)


def test_empty_findings_is_valid():
    assert validate_ai_response('{"findings": []}', SNAP).findings == []


def test_invented_component_dropped():
    r = validate_ai_response(wrap(good(component="/nav2_controller")), SNAP)
    assert r.findings == [] and "unknown component" in r.warnings[0]


def test_generic_and_slashless_components_allowed():
    for comp in ("tf", "system", "arm_controller", "robot_state_publisher", "base_link"):
        assert len(validate_ai_response(wrap(good(component=comp)), SNAP).findings) == 1, comp


@pytest.mark.parametrize("bad", [
    {"severity": "critical"}, {"severity": None}, {"confidence": 1.5}, {"confidence": -0.1},
    {"confidence": "high"}, {"confidence": True}, {"observed": "a string"}, {"possible_causes": [1, 2]},
    {"component": 5},
])
def test_malformed_findings_dropped(bad):
    r = validate_ai_response(wrap(good(**bad)), SNAP)
    assert r.findings == [] and r.warnings


def test_missing_required_field_dropped():
    f = good()
    del f["confidence"]
    assert validate_ai_response(wrap(f), SNAP).findings == []
    assert validate_ai_response(wrap("nonsense"), SNAP).findings == []


def test_non_read_only_and_invented_commands_removed():
    r = validate_ai_response(wrap(good(recommended_checks=[
        "ros2 control list_controllers", "ros2 topic pub /cmd_vel x", "ros2 topic echo /ghost_topic",
        "ros2 lifecycle set /x activate", "rm -rf /", "ros2 topic echo /joint_states"])), SNAP)
    assert r.findings[0].recommended_checks == ["ros2 control list_controllers", "ros2 topic echo /joint_states"]
    assert len(r.warnings) == 4


def test_observation_citing_unknown_name_removed():
    r = validate_ai_response(wrap(good(observed=[
        "/joint_states has 0 publishers", "/ghost_node crashed", "topic /dev/ttyUSB0 missing"])), SNAP)
    assert r.findings[0].observed == ["/joint_states has 0 publishers"]
    assert len(r.warnings) == 2


def test_item_limits_and_text_truncated():
    many = [f"cause {i}" for i in range(50)]
    r = validate_ai_response(wrap(good(possible_causes=many, problem="p" * 5000)), SNAP)
    assert len(r.findings[0].possible_causes) == 10 and len(r.findings[0].problem) == 500


def test_confidence_rounded():
    assert validate_ai_response(wrap(good(confidence=0.123456)), SNAP).findings[0].confidence == 0.12


def test_known_names_covers_graph_objects():
    k = known_names(SNAP)
    assert {"/arm_controller", "arm_controller", "/joint_states", "base_link", "/controller_manager"} <= k


def test_prompt_contains_rules_and_payload():
    payload = build_payload(SNAP, analyze(SNAP))
    prompt = build_user_prompt(payload)
    assert "Never invent" in SYSTEM_PROMPT and "possible_causes" in SYSTEM_PROMPT
    assert "/joint_states" in prompt and "rule_findings" in prompt
    assert json.loads(prompt.split("\n\n", 1)[1]) == json.loads(json.dumps(payload))


def test_payload_summary_lists_what_is_and_is_not_sent():
    s = summarize_payload(build_payload(SNAP, analyze(SNAP)), mask_identifiers=False)
    text = "\n".join(s.lines())
    assert "3 nodes" in text and "API keys" in text and "--redact" in text and s.size_bytes > 1000
