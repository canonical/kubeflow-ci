# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""LLM client abstraction.

A thin wrapper that lets the rest of the workflow ask for a text response
without caring which provider is on the other end. Clients are picked by a
`provider[/model]` spec (e.g. `copilot/claude-opus-5.5`); the live backends
talk to the OpenAI-compatible chat-completions endpoints of GitHub Copilot
or OpenRouter through the `openai` SDK. A MockClient backs the unit tests.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional, Protocol, Tuple

import httpx
import openai

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
    client: openai.OpenAI,
    *,
    provider: str,
    model: str,
    max_tokens: int,
    system: str,
    messages: List[Message],
    stream: bool = False,
    reasoning_effort: Optional[str] = None,
) -> str:
    """Run one chat completion through the OpenAI SDK and return the text.

    The system prompt is prepended to `messages` as a `role=system` turn.
    The SDK retries connection errors, 429 and 5xx; any other API error is
    raised as RuntimeError.
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
    extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
    t0 = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=(
                [{"role": "system", "content": system}]
                + [{"role": m.role, "content": m.content} for m in messages]
            ),
            stream=stream,
            **extra,
        )
        content = _read_stream(provider, response) if stream else _read_body(provider, response)
    except openai.APIStatusError as exc:
        log.error("%s %d in %.1fs: %s", provider, exc.status_code, time.monotonic() - t0, exc)
        raise RuntimeError(f"{provider} API error {exc.status_code}: {exc.message}") from exc
    except openai.APIError as exc:
        raise RuntimeError(f"{provider} API error: {exc.message}") from exc
    log.info("  -> %d response chars in %.1fs", len(content), time.monotonic() - t0)
    return content


def _read_body(provider: str, response) -> str:
    if not response.choices or response.choices[0].message.content is None:
        raise RuntimeError(f"{provider} response has no content: {response!r}")
    return response.choices[0].message.content


def _read_stream(provider: str, stream) -> str:
    """Concatenate the `content` deltas of a streamed completion."""
    content: List[str] = []
    reasoning_chars = 0
    finish_reason = None
    for chunk in stream:
        for choice in chunk.choices:
            content.append(choice.delta.content or "")
            # Copilot-specific extra field carrying the model's thinking.
            reasoning_chars += len(getattr(choice.delta, "reasoning_text", None) or "")
            finish_reason = choice.finish_reason or finish_reason
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
    http_client: Optional[httpx.Client] = field(default=None, repr=False)

    def complete(self, system: str, messages: List[Message]) -> str:
        api_key = self.api_key or os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set; required to call OpenRouter.")
        client = openai.OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            default_headers={
                "HTTP-Referer": "https://github.com/canonical/kubeflow-ci",
                "X-Title": "kubeflow-ci bump-rock",
            },
            http_client=self.http_client,
        )
        return _chat_completion(
            client,
            provider="OpenRouter",
            model=self.model,
            max_tokens=self.max_tokens,
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
    http_client: Optional[httpx.Client] = field(default=None, repr=False)

    def complete(self, system: str, messages: List[Message]) -> str:
        client = openai.OpenAI(
            api_key=self.api_key or copilot_token(),
            base_url=self.base_url,
            timeout=self.timeout,
            http_client=self.http_client,
        )
        return _chat_completion(
            client,
            provider="Copilot",
            model=self.model,
            max_tokens=self.max_tokens,
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
