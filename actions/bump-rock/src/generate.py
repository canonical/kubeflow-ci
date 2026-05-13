# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Stage 4: ask an LLM for an updated rockcraft.yaml, then validate it.

This module implements spec §6.6:
    * Build a prompt from the current rockcraft.yaml + old/new upstream
      Dockerfile pairs + target version.
    * Call the configured LLM.
    * Strip any code fences from the response.
    * Validate the output (valid YAML, name unchanged, version matches,
      `# Based on` URLs reference the new version).
    * On validation failure, append the error to the conversation and ask
      the model to fix it, up to MAX_LLM_RETRIES additional times.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Tuple

import yaml

log = logging.getLogger("bump-rock.generate")

from .errors import BumpRockError
from .fetch import DockerfilePair
from .llm import LLMClient, Message
from .rockcraft import BASED_ON_RE, RockcraftDoc, _extract_based_on_urls
from .urls import UpstreamRef, parse_all

MAX_LLM_RETRIES = 2  # additional attempts after the first; total = 3.

SYSTEM_PROMPT = """\
You update Canonical Charmed Kubeflow "rock" recipes (rockcraft.yaml files).

A rock mirrors one or more upstream Dockerfiles. When the upstream version
changes, the rockcraft.yaml must be updated to match. You will receive:

  1. The current rockcraft.yaml.
  2. One or more upstream Dockerfile pairs (old vs new).
  3. The target version string.

Rules — follow them all:
  - Output ONLY the updated rockcraft.yaml content. No markdown fences, no
    commentary, no explanations, no leading or trailing whitespace beyond
    what belongs in the file.
  - Update the leading `# Based on <url>` comments so the <ref> segment of
    each URL matches the target version.
  - Update the `version:` field to the target version. The version field
    usually omits a leading `v` even when the upstream tag has one (e.g.
    tag `v0.18.0` -> `version: "0.18.0"`). Preserve the original quoting
    style.
  - Update `source-tag:` entries under `parts:` so they reference the
    target version where they currently reference the old version.
  - Update package versions, base image versions, or other pinned values
    inside `override-build` / `override-pull` scripts ONLY when the
    Dockerfile diff explicitly changes them. Do not speculate.
  - Preserve every other comment, the YAML structure, indentation style,
    and any project-specific patches.
  - Update the `base:` field when the upstream Dockerfile's `FROM` image
    indicates a different OS release than the current `base:` can
    support. The dominant trigger is a Python-version bump: a given
    `python3.X` is only available in apt for specific Ubuntu releases.
      - `python3.10` is the default in `ubuntu@22.04` (jammy)
      - `python3.12` is the default in `ubuntu@24.04` (noble)
    If the new Dockerfile's `FROM` line carries a release codename
    (`bookworm`, `jammy`, `noble`, ...) or references a `python3.X`
    not packaged in the current `base:`, you MUST bump `base:` to the
    matching Ubuntu release (e.g. `ubuntu@22.04` -> `ubuntu@24.04` when
    upstream moves from `bookworm`/`jammy` to `noble`, or from
    `python3.11` to `python3.12`). Failing to bump `base:` will cause
    `rockcraft pack` to fail with "Cannot find package listed in
    'build-packages': python3.X".
  - Do not change `name`, `summary`, `description`, or `license` unless
    the Dockerfile diff makes it obviously necessary.

CRITICAL — verbatim preservation of unchanged regions:
  Every line you are not explicitly required to change MUST be byte-perfect
  identical to the input. The output will be diffed against the original;
  any unexplained change is treated as a transcription error and will be
  rejected. Pay particular attention to:
  - Shell variables in override-build scripts (e.g. `$CRAFT_PART_INSTALL`,
    `$CRAFT_PROJECT_DIR`) — re-type them character-by-character.
  - YAML keys (`plugin:`, `build-packages:`, `override-build:`) — no
    duplicated words, no typos.
  - Long bash one-liners — copy the entire line, do not paraphrase.
  When in doubt, copy the original line verbatim and move on.
"""


@dataclass
class GenerateResult:
    """Outcome of a generate call.

    `ok=True` means a candidate passed all validators; `rockcraft_yaml` is
    that candidate. `ok=False` means no inner attempt produced a valid
    output; `rockcraft_yaml` carries the *last* candidate (best effort)
    and `validator_errors` records why it failed. Either way the caller
    receives a non-None YAML string so a best-effort PR can be opened.

    `raw_responses` and `per_attempt_errors` are aligned: index `i` is the
    raw LLM output and the validator errors list for the (i+1)-th inner
    attempt. Empty error list = that attempt passed.
    """

    rockcraft_yaml: str
    attempts: int
    raw_responses: List[str]
    ok: bool = True
    validator_errors: List[str] = field(default_factory=list)
    per_attempt_errors: List[List[str]] = field(default_factory=list)


def build_user_prompt(
    doc: RockcraftDoc,
    pairs: List[DockerfilePair],
    target_version: str,
    *,
    additional_context: str = "",
) -> str:
    """Render the user-side prompt that frames the inputs for the model.

    `additional_context`, if given, is appended at the end and is intended
    for the outer sanity-retry loop (§6.7) to feed back the tail of a tox
    failure log from the previous attempt.
    """
    sections: List[str] = [f"Target version: {target_version}"]
    sections.append("=== current rockcraft.yaml ===")
    sections.append(doc.raw_text)
    for i, pair in enumerate(pairs, start=1):
        old_label = f"upstream Dockerfile {i} (old, {pair.old_ref.ref})"
        new_label = f"upstream Dockerfile {i} (new, {pair.new_ref.ref})"
        sections.append(f"=== {old_label} — {pair.old_ref.blob_url()} ===")
        sections.append(pair.old_text)
        sections.append(f"=== {new_label} — {pair.new_ref.blob_url()} ===")
        sections.append(pair.new_text)
    if additional_context:
        sections.append("=== prior sanity-test attempts ===")
        sections.append(additional_context)
        sections.append(
            "Each section above is a previous outer attempt: the "
            "rockcraft.yaml you produced and how its `tox -e <env>` run "
            "failed. Take the full history into account when producing the "
            "next rockcraft.yaml — do not repeat fixes that already failed, "
            "and only change lines needed to address the latest failure."
        )
    sections.append("Produce the updated rockcraft.yaml content.")
    return "\n\n".join(sections)


_FENCE_RE = re.compile(r"^```(?:ya?ml)?\s*\n(?P<body>.*?)\n```\s*$", re.DOTALL)


def strip_fences(text: str) -> str:
    """Remove ```yaml fences if the model wrapped its output in them.

    When no fences are present, the input is returned unchanged so a
    canonical trailing newline (rockcraft.yaml files end with one) is
    preserved on the path to disk.
    """
    match = _FENCE_RE.match(text.strip())
    if match:
        body = match.group("body")
        if not body.endswith("\n"):
            body += "\n"
        return body
    return text


def validate_output(
    new_yaml: str, original: RockcraftDoc, target_version: str
) -> List[str]:
    """Return a list of validator error messages. Empty list = passing."""
    errors: List[str] = []

    try:
        doc = yaml.safe_load(new_yaml)
    except yaml.YAMLError as exc:
        return [f"output is not valid YAML: {exc}"]

    if not isinstance(doc, dict):
        return ["output YAML top level must be a mapping"]

    if str(doc.get("name", "")) != original.name:
        errors.append(
            f"`name` changed: expected {original.name!r}, got {doc.get('name')!r}"
        )

    yaml_version_expected = target_version.lstrip("v")
    actual_version = str(doc.get("version", "")).lstrip("v")
    if actual_version != yaml_version_expected:
        errors.append(
            f"`version` must equal target version {yaml_version_expected!r}, "
            f"got {doc.get('version')!r}"
        )

    new_urls = _extract_based_on_urls(new_yaml)
    if not new_urls:
        errors.append("no `# Based on` comment present in updated file")
    else:
        for url in new_urls:
            if not BASED_ON_RE.search(f"# Based on {url}"):  # defensive
                continue
            if target_version not in url:
                errors.append(
                    f"`# Based on` URL does not reference target version "
                    f"{target_version!r}: {url}"
                )

    try:
        parse_all(new_urls)
    except BumpRockError as exc:
        errors.append(str(exc))

    return errors


def generate(
    *,
    client: LLMClient,
    doc: RockcraftDoc,
    pairs: List[DockerfilePair],
    target_version: str,
    max_retries: int = MAX_LLM_RETRIES,
    additional_context: str = "",
) -> GenerateResult:
    """Drive the LLM until it produces a passing rockcraft.yaml or we give up.

    Spec §6.6: at most `1 + max_retries` total attempts. On validation
    failure, the next attempt is preceded by the previous assistant turn
    and a new user turn carrying the validator errors.

    `additional_context` is folded into the initial user prompt; it is how
    the outer sanity-retry loop (§6.7) feeds back the tail of a tox
    failure log from a previous attempt.

    Raises:
        BumpRockError: if no attempt produced a passing output.
    """
    user_prompt = build_user_prompt(
        doc, pairs, target_version, additional_context=additional_context
    )
    conversation: List[Message] = [Message(role="user", content=user_prompt)]
    raw_responses: List[str] = []
    per_attempt_errors: List[List[str]] = []

    total_attempts = 1 + max_retries
    last_errors: List[str] = []
    last_candidate = ""
    for attempt in range(1, total_attempts + 1):
        log.info(
            "generate attempt %d/%d (additional_context=%s)",
            attempt,
            total_attempts,
            "yes" if additional_context else "no",
        )
        response = client.complete(SYSTEM_PROMPT, conversation)
        raw_responses.append(response)
        candidate = strip_fences(response)
        last_candidate = candidate
        errors = validate_output(candidate, doc, target_version)
        per_attempt_errors.append(errors)
        if not errors:
            log.info("  -> validators passed on attempt %d", attempt)
            return GenerateResult(
                rockcraft_yaml=candidate,
                attempts=attempt,
                raw_responses=raw_responses,
                per_attempt_errors=per_attempt_errors,
            )

        log.warning("  -> %d validator error(s) on attempt %d", len(errors), attempt)
        for e in errors:
            first_line = e.splitlines()[0] if e else e
            log.warning("     - %s", first_line)

        last_errors = errors
        if attempt == total_attempts:
            break

        conversation.append(Message(role="assistant", content=response))
        conversation.append(
            Message(
                role="user",
                content=(
                    "The previous output failed validation:\n"
                    + "\n".join(f"  - {e}" for e in errors)
                    + "\n\nReturn the corrected rockcraft.yaml, "
                    "following the rules in the system prompt."
                ),
            )
        )

    # All inner attempts failed validation. Return ok=False with the last
    # candidate so the caller can still publish a best-effort draft PR.
    log.warning(
        "generate exhausted %d inner attempts without passing validators",
        total_attempts,
    )
    return GenerateResult(
        rockcraft_yaml=last_candidate,
        attempts=total_attempts,
        raw_responses=raw_responses,
        ok=False,
        validator_errors=last_errors,
        per_attempt_errors=per_attempt_errors,
    )


def fetched_pairs_to_refs(pairs: List[DockerfilePair]) -> Tuple[List[UpstreamRef], List[UpstreamRef]]:
    """Split a list of DockerfilePairs into parallel lists of (old, new) refs."""
    return [p.old_ref for p in pairs], [p.new_ref for p in pairs]
