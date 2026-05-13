# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""LLM client abstraction.

A thin wrapper that lets the rest of the workflow ask for a text response
without caring which provider is on the other end. The live backend talks
to OpenRouter's OpenAI-compatible chat-completions endpoint; a MockClient
backs the unit tests.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

import requests

DEFAULT_OPENROUTER_MODEL = "moonshotai/kimi-k2"
DEFAULT_MAX_TOKENS = 16_000
DEFAULT_TIMEOUT = 300  # seconds; spec §7.3.

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass
class Message:
    """One turn in the conversation. `role` is `user` or `assistant`."""

    role: str
    content: str


class LLMClient(Protocol):
    """Anything that can take a system prompt + messages and return text."""

    def complete(self, system: str, messages: List[Message]) -> str: ...


@dataclass
class OpenRouterClient:
    """Live OpenRouter client. Requires OPENROUTER_API_KEY in the environment.

    Uses OpenRouter's OpenAI-compatible /chat/completions endpoint, so the
    system prompt is prepended to `messages` as a `role=system` turn.
    """

    model: str = DEFAULT_OPENROUTER_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    api_key: Optional[str] = None
    base_url: str = OPENROUTER_BASE_URL
    timeout: int = DEFAULT_TIMEOUT

    def complete(self, system: str, messages: List[Message]) -> str:
        api_key = self.api_key or os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set; required to call OpenRouter."
            )
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": (
                [{"role": "system", "content": system}]
                + [{"role": m.role, "content": m.content} for m in messages]
            ),
        }
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/canonical/kubeflow-ci",
                "X-Title": "kubeflow-ci bump-rock",
            },
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenRouter API error {resp.status_code}: {resp.text[:500]}"
            )
        body = resp.json()
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(
                f"OpenRouter response missing expected fields: {body!r}"
            ) from exc


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


def build_client(provider: str, model: Optional[str]) -> LLMClient:
    """Return an LLMClient for the requested provider + model.

    Args:
        provider: `openrouter` (live) or `mock` (tests).
        model: Model id override; ignored by `mock`.
    """
    if provider == "openrouter":
        return OpenRouterClient(model=model or DEFAULT_OPENROUTER_MODEL)
    if provider == "mock":
        return MockClient()
    raise ValueError(f"unsupported LLM provider: {provider!r}")
