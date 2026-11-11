# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""LLM client abstraction.

A thin wrapper that lets the rest of the workflow ask for a text response
without caring which provider is on the other end. Clients are picked by a
`provider[/model]` spec (e.g. `copilot/claude-opus-5.5`); the live backends
talk to the OpenAI-compatible chat-completions endpoints of GitHub Copilot
or OpenRouter. A MockClient backs the unit tests.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Tuple

import requests

log = logging.getLogger("bump-rock.llm")

DEFAULT_COPILOT_MODEL = "claude-opus-5.5"
DEFAULT_OPENROUTER_MODEL = "deepseek/deepseek-v4-pro"
DEFAULT_LLM = f"copilot/{DEFAULT_COPILOT_MODEL}"
DEFAULT_MAX_TOKENS = 16_000
# Thinking tokens count towards the output budget; only streaming allows > 16k.
COPILOT_MAX_TOKENS = 64_000
REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_TIMEOUT = 300  # seconds

COPILOT_BASE_URL = "https://api.githubcopilot.com"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class Message:
    """One turn in the conversation. `role` is `user` or `assistant`."""

    role: str
    content: str


class LLMClient(Protocol):
    """Anything that can take a system prompt + messages and return text."""

    def complete(self, system: str, messages: List[Message]) -> str: ...


def _chat_completion(
    *,
    provider: str,
    url: str,
    headers: dict,
    model: str,
    max_tokens: int,
    timeout: int,
    system: str,
    messages: List[Message],
    stream: bool = False,
    reasoning_effort: Optional[str] = None,
) -> str:
    """POST to an OpenAI-compatible /chat/completions endpoint, return the text.

    The system prompt is prepended to `messages` as a `role=system` turn.
    With `stream`, `timeout` bounds the wait between chunks, not the whole call.
    """
    prompt_chars = len(system) + sum(len(m.content) for m in messages)
    log.info(
        "calling %s (model=%s, turns=%d, prompt~%d chars, reasoning=%s)",
        provider,
        model,
        len(messages),
        prompt_chars,
        reasoning_effort or "off",
    )
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": (
            [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages]
        ),
    }
    if stream:
        payload["stream"] = True
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    t0 = time.monotonic()
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout, stream=stream)
    if resp.status_code != 200:
        log.error(
            "%s %d in %.1fs: %s",
            provider,
            resp.status_code,
            time.monotonic() - t0,
            resp.text[:200],
        )
        raise RuntimeError(f"{provider} API error {resp.status_code}: {resp.text[:500]}")
    content = _read_stream(provider, resp) if stream else _read_body(provider, resp)
    log.info("  -> %d response chars in %.1fs", len(content), time.monotonic() - t0)
    return content


def _read_body(provider: str, resp: requests.Response) -> str:
    body = resp.json()
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"{provider} response missing expected fields: {body!r}") from exc


def _read_stream(provider: str, resp: requests.Response) -> str:
    """Concatenate the `content` deltas of a server-sent-events completion."""
    content: List[str] = []
    reasoning_chars = 0
    finish_reason = None
    for raw in resp.iter_lines():
        line = raw.decode("utf-8")
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            break
        event = json.loads(data)
        if "error" in event:
            raise RuntimeError(f"{provider} stream error: {event['error']!r}")
        for choice in event.get("choices", []):
            delta = choice.get("delta") or {}
            content.append(delta.get("content") or "")
            reasoning_chars += len(delta.get("reasoning_text") or "")
            finish_reason = choice.get("finish_reason") or finish_reason
    log.info("  -> %d reasoning chars, finish_reason=%s", reasoning_chars, finish_reason)
    if finish_reason == "length":
        log.warning("%s hit max_tokens; the response is truncated", provider)
    return "".join(content)


@dataclass
class OpenRouterClient:
    """Live OpenRouter client. Requires OPENROUTER_API_KEY in the environment."""

    model: str = DEFAULT_OPENROUTER_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    api_key: Optional[str] = None
    base_url: str = OPENROUTER_BASE_URL
    timeout: int = DEFAULT_TIMEOUT

    def complete(self, system: str, messages: List[Message]) -> str:
        api_key = self.api_key or os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set; required to call OpenRouter.")
        return _chat_completion(
            provider="OpenRouter",
            url=f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/canonical/kubeflow-ci",
                "X-Title": "kubeflow-ci bump-rock",
            },
            model=self.model,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            system=system,
            messages=messages,
        )


def copilot_token() -> str:
    """Return a GitHub token entitled to call the Copilot API.

    Uses COPILOT_GITHUB_TOKEN when set (CI: a fine-grained PAT with the
    "Copilot Requests" permission), otherwise the `gh` CLI's stored login.
    """
    token = os.environ.get("COPILOT_GITHUB_TOKEN")
    if token:
        return token
    # GITHUB_TOKEN / GH_TOKEN usually lack Copilot access and would shadow the gh login.
    env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")}
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"], env=env, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "No Copilot token: set COPILOT_GITHUB_TOKEN or log in with `gh auth login`."
        ) from exc
    return proc.stdout.strip()


@dataclass
class CopilotClient:
    """Live GitHub Copilot client (chat-completions API).

    The GitHub token is sent as-is as the bearer token; no exchange for a
    short-lived Copilot token is needed.
    """

    model: str = DEFAULT_COPILOT_MODEL
    max_tokens: int = COPILOT_MAX_TOKENS
    api_key: Optional[str] = None
    base_url: str = COPILOT_BASE_URL
    timeout: int = DEFAULT_TIMEOUT
    reasoning_effort: Optional[str] = DEFAULT_REASONING_EFFORT

    def complete(self, system: str, messages: List[Message]) -> str:
        return _chat_completion(
            provider="Copilot",
            url=f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key or copilot_token()}"},
            model=self.model,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            system=system,
            messages=messages,
            stream=True,
            reasoning_effort=self.reasoning_effort,
        )


@dataclass
class MockClient:
    """Deterministic client for tests. Returns a queued response per call."""

    responses: List[str] = field(default_factory=list)
    calls: List[dict] = field(default_factory=list)

    def complete(self, system: str, messages: List[Message]) -> str:
        self.calls.append({"system": system, "messages": list(messages)})
        if not self.responses:
            raise RuntimeError("MockClient out of queued responses")
        return self.responses.pop(0)


def parse_llm_spec(spec: str) -> Tuple[str, str]:
    """Split a `provider[/model]` spec, filling in the provider's default model.

    Only the first `/` separates the provider, so OpenRouter ids keep their
    vendor prefix (`openrouter/deepseek/deepseek-v4-pro`). `mock` has no model.
    """
    provider, _, model = spec.partition("/")
    if provider == "copilot":
        return provider, model or DEFAULT_COPILOT_MODEL
    if provider == "openrouter":
        return provider, model or DEFAULT_OPENROUTER_MODEL
    if provider == "mock":
        return provider, ""
    raise ValueError(
        f"unsupported LLM provider {provider!r} in {spec!r}; expected "
        "copilot/<model>, openrouter/<vendor>/<model> or mock"
    )


def build_client(
    spec: str, reasoning_effort: Optional[str] = DEFAULT_REASONING_EFFORT
) -> LLMClient:
    """Return an LLMClient for a `provider[/model]` spec (see parse_llm_spec).

    `reasoning_effort` (None = thinking off) only applies to Copilot.
    """
    provider, model = parse_llm_spec(spec)
    if provider == "copilot":
        return CopilotClient(model=model, reasoning_effort=reasoning_effort)
    if provider == "openrouter":
        return OpenRouterClient(model=model)
    return MockClient()
