# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for LLM provider selection and the Copilot client."""

import json
import subprocess
from unittest.mock import patch

import httpx
import pytest
from src import llm


@pytest.mark.parametrize(
    "spec, expected",
    [
        ("copilot/claude-opus-5.5", ("copilot", "claude-opus-5.5")),
        ("copilot", ("copilot", llm.DEFAULT_COPILOT_MODEL)),
        ("openrouter/deepseek/deepseek-v4-pro", ("openrouter", "deepseek/deepseek-v4-pro")),
        ("openrouter", ("openrouter", llm.DEFAULT_OPENROUTER_MODEL)),
        ("mock", ("mock", "")),
    ],
)
def test_parse_llm_spec(spec, expected):
    assert llm.parse_llm_spec(spec) == expected


def test_parse_llm_spec_rejects_unknown_provider():
    with pytest.raises(ValueError, match="unsupported LLM provider 'deepseek'"):
        llm.parse_llm_spec("deepseek/deepseek-v4-pro")


def test_build_client_picks_provider():
    client = llm.build_client("copilot/claude-opus-5.5", reasoning_effort="low")
    assert isinstance(client, llm.CopilotClient)
    assert client.model == "claude-opus-5.5"
    assert client.reasoning_effort == "low"
    assert isinstance(llm.build_client("openrouter"), llm.OpenRouterClient)
    assert isinstance(llm.build_client("mock"), llm.MockClient)


def test_copilot_token_prefers_env(monkeypatch):
    monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "from-env")
    with patch("subprocess.run") as run_mock:
        assert llm.copilot_token() == "from-env"
    run_mock.assert_not_called()


def test_copilot_token_falls_back_to_gh_login(monkeypatch):
    monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "actions-token")
    monkeypatch.setenv("GH_TOKEN", "other-token")
    done = subprocess.CompletedProcess(args=[], returncode=0, stdout="gho_abc\n")
    with patch("subprocess.run", return_value=done) as run_mock:
        assert llm.copilot_token() == "gho_abc"
    assert run_mock.call_args.args[0] == ["gh", "auth", "token"]
    env = run_mock.call_args.kwargs["env"]
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env


def test_copilot_token_errors_without_gh_login(monkeypatch):
    monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
    err = subprocess.CalledProcessError(1, ["gh", "auth", "token"])
    with patch("subprocess.run", side_effect=err):
        with pytest.raises(RuntimeError, match="COPILOT_GITHUB_TOKEN"):
            llm.copilot_token()


def _sse(*events):
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"


def _transport(status=200, body="", content_type="text/event-stream"):
    """Return (http_client, requests_seen) answering every call with one response."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            status, content=body.encode(), headers={"content-type": content_type}
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def _chunk(delta, finish_reason=None):
    return {
        "id": "c",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def test_copilot_client_streams_chat_completion():
    http, seen = _transport(
        body=_sse(
            _chunk({"reasoning_text": "thinking…"}),
            _chunk({"content": "name: "}),
            _chunk({"content": "x — y\n"}, finish_reason="stop"),
        )
    )
    client = llm.CopilotClient(model="claude-opus-5.5", api_key="tok", http_client=http)
    out = client.complete("sys", [llm.Message(role="user", content="hi")])
    assert out == "name: x — y\n"
    request = seen[0]
    assert str(request.url) == f"{llm.COPILOT_BASE_URL}/chat/completions"
    assert request.headers["Authorization"] == "Bearer tok"
    body = json.loads(request.content)
    assert body["model"] == "claude-opus-5.5"
    assert body["stream"] is True
    assert body["reasoning_effort"] == llm.DEFAULT_REASONING_EFFORT
    assert body["max_tokens"] == llm.COPILOT_MAX_TOKENS
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]


def test_copilot_client_omits_reasoning_when_disabled():
    http, seen = _transport(body=_sse(_chunk({"content": "ok"})))
    llm.CopilotClient(api_key="tok", reasoning_effort=None, http_client=http).complete("s", [])
    assert "reasoning_effort" not in json.loads(seen[0].content)


def test_copilot_client_raises_on_stream_error():
    http, _ = _transport(body=_sse({"error": {"message": "overloaded"}}))
    with pytest.raises(RuntimeError, match="overloaded"):
        llm.CopilotClient(api_key="tok", http_client=http).complete("s", [])


def test_copilot_client_raises_on_http_error():
    http, _ = _transport(
        status=401, body='{"error": {"message": "bad creds"}}', content_type="application/json"
    )
    client = llm.CopilotClient(api_key="tok", http_client=http)
    with pytest.raises(RuntimeError, match="Copilot API error 401"):
        client.complete("sys", [llm.Message(role="user", content="hi")])


def test_openrouter_client_reads_plain_completion():
    body = {
        "id": "c",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "done"},
                "finish_reason": "stop",
            }
        ],
    }
    http, seen = _transport(body=json.dumps(body), content_type="application/json")
    client = llm.OpenRouterClient(api_key="key", http_client=http)
    assert client.complete("s", [llm.Message(role="user", content="hi")]) == "done"
    assert str(seen[0].url) == f"{llm.OPENROUTER_BASE_URL}/chat/completions"
    assert seen[0].headers["X-Title"] == "kubeflow-ci bump-rock"
    assert not json.loads(seen[0].content).get("stream")
