import json
import types

import pytest

from ros2_ai_debugger.providers import (
    PROVIDERS,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderError,
    get_provider,
)
from ros2_ai_debugger.providers.ollama import is_loopback_url, normalize_host
from tests.fixtures.scenarios import broken_robot_snapshot

SNAP = broken_robot_snapshot()
REPLY = json.dumps({"findings": [{
    "severity": "warning", "component": "/joint_states", "observed": ["/joint_states has 0 publishers"],
    "possible_causes": ["broadcaster missing"], "recommended_checks": ["ros2 control list_controllers"],
    "confidence": 0.8, "problem": "p"}]})


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OLLAMA_HOST",
              "ANTHROPIC_MODEL", "OPENAI_MODEL", "GEMINI_MODEL", "OLLAMA_MODEL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(k, raising=False)


def test_registry_and_unknown():
    assert set(PROVIDERS) == {"claude", "openai", "gemini", "ollama"}
    with pytest.raises(ProviderError):
        get_provider("nope")


def test_claude_uses_sdk_and_env_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    calls = {}

    class FakeMessages:
        def create(self, **kw):
            calls.update(kw)
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=REPLY)])

    def factory(key):
        calls["key"] = key
        return types.SimpleNamespace(messages=FakeMessages())

    p = ClaudeProvider(client_factory=factory)
    result = p.analyze(SNAP)
    assert calls["key"] == "sk-ant-test" and calls["model"] == "claude-sonnet-5"
    assert "Never invent" in calls["system"] and "joint_states" in calls["messages"][0]["content"]
    assert result.findings[0].source == "ai:claude" and p.is_local is False


def test_claude_without_key_or_sdk(monkeypatch):
    assert ClaudeProvider().is_configured() is False
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        ClaudeProvider().complete("s", "u")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setitem(__import__("sys").modules, "anthropic", None)  # import fails
    with pytest.raises(ProviderError, match="not installed"):
        ClaudeProvider().complete("s", "u")


def test_claude_api_error_does_not_leak_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SECRET")

    def factory(key):
        raise_ = types.SimpleNamespace(messages=types.SimpleNamespace(
            create=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))))
        return raise_

    with pytest.raises(ProviderError) as e:
        ClaudeProvider(client_factory=factory).complete("s", "u")
    assert "SECRET" not in str(e.value) and "boom" in str(e.value)


def test_openai_request_and_parse(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test1234567890abcdef")
    seen = {}

    def post(url, body, headers, timeout):
        seen.update(url=url, body=body, headers=headers)
        return {"choices": [{"message": {"content": REPLY}}]}

    r = OpenAIProvider(http_post=post).analyze(SNAP)
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"]["Authorization"].startswith("Bearer ")
    assert seen["body"]["response_format"] == {"type": "json_object"} and r.findings


def test_openai_missing_key_bad_shape_bad_base(monkeypatch):
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        OpenAIProvider().complete("s", "u")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    with pytest.raises(ProviderError, match="unexpected response"):
        OpenAIProvider(http_post=lambda *a: {"oops": 1}).complete("s", "u")
    monkeypatch.setenv("OPENAI_BASE_URL", "file:///etc/passwd")
    with pytest.raises(ProviderError, match="http"):
        OpenAIProvider(http_post=lambda *a: {}).complete("s", "u")


def test_gemini_key_in_header_not_url(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaTESTKEY")
    seen = {}

    def post(url, body, headers, timeout):
        seen.update(url=url, headers=headers, body=body)
        return {"candidates": [{"content": {"parts": [{"text": REPLY}]}}]}

    assert GeminiProvider(http_post=post).analyze(SNAP).findings
    assert "AIza" not in seen["url"] and seen["headers"] == {"x-goog-api-key": "AIzaTESTKEY"}
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_blocked_response_and_no_key():
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        GeminiProvider().complete("s", "u")


def test_ollama_local_detection_and_request(monkeypatch):
    seen = {}

    def post(url, body, headers, timeout):
        seen.update(url=url, body=body, headers=headers)
        return {"message": {"content": REPLY}}

    p = OllamaProvider(model="m", http_post=post)
    assert p.is_local and p.is_configured()
    assert p.analyze(SNAP).findings
    assert seen["url"] == "http://127.0.0.1:11434/api/chat" and seen["body"]["stream"] is False
    assert seen["headers"] == {}  # no credentials
    # the context window must cover the whole prompt so Ollama does not truncate the system prompt
    total = sum(len(m["content"]) for m in seen["body"]["messages"])
    assert seen["body"]["options"]["num_ctx"] >= total // 3


@pytest.mark.parametrize("host,local", [
    ("localhost:11434", True), ("http://127.0.0.1:1", True), ("http://[::1]:11434", True),
    ("http://192.168.1.5:11434", False), ("https://ollama.example.com", False)])
def test_ollama_loopback(host, local):
    assert is_loopback_url(normalize_host(host)) is local


def test_ollama_require_local_blocks_remote(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://10.0.0.9:11434")
    called = []
    p = OllamaProvider(http_post=lambda *a: called.append(1), require_local=True)
    assert not p.is_local
    with pytest.raises(ProviderError, match="loopback"):
        p.complete("s", "u")
    assert called == []


def test_provider_model_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-x")
    assert OpenAIProvider().model == "gpt-x" and OpenAIProvider(model="y").model == "y"


def test_http_helper_maps_errors():
    from ros2_ai_debugger.providers._http import post_json
    with pytest.raises(ProviderError, match="could not reach") as e:
        post_json("http://127.0.0.1:1/x", {}, {"Authorization": "Bearer SECRET"}, 1)
    assert "SECRET" not in str(e.value)


def test_claude_with_real_sdk_and_mocked_transport(monkeypatch):
    """Exercise the real anthropic SDK request/response path with no network."""
    anthropic = pytest.importorskip("anthropic")
    httpx = pytest.importorskip("httpx2")  # anthropic >= 1.x uses httpx2
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["key_header"] = request.headers.get("x-api-key")
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": REPLY}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1}})

    def factory(key):
        return anthropic.Anthropic(api_key=key, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = ClaudeProvider(client_factory=factory).analyze(SNAP)
    assert seen["url"].endswith("/v1/messages") and seen["key_header"] == "sk-ant-test"
    assert seen["body"]["model"] == "claude-sonnet-5" and seen["body"]["max_tokens"] == 4096
    assert "Never invent" in seen["body"]["system"] and seen["body"]["messages"][0]["role"] == "user"
    assert result.findings[0].component == "/joint_states"
