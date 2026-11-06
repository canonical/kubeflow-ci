# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Stage 4: ask an LLM for an updated rockcraft.yaml, then validate it.

This module implements spec §6.6:
    * Build a prompt from the current rockcraft.yaml + old/new upstream
      Dockerfile pairs + target version.
    * Call the configured LLM.
    * Split the response into its <change> blocks, reviewer notes, and the
      <rockcraft_yaml> body.
    * Validate the output (valid YAML, name unchanged, version matches,
      `# Based on` URLs reference the new version, every changed line is
      listed in a <change> block).
    * On validation failure, append the error to the conversation and ask
      the model to fix it, up to MAX_LLM_RETRIES additional times.
"""
from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import yaml

log = logging.getLogger("bump-rock.generate")

from .errors import BumpRockError
from .fetch import DockerfilePair
from .llm import LLMClient, Message
from .rockcraft import BASED_ON_RE, RockcraftDoc, _extract_based_on_urls
from .urls import UpstreamRef, parse_all

MAX_LLM_RETRIES = 2  # additional attempts after the first; total = 3.

SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8")

NOTE_KINDS = ("dropped_deviation", "skipped_upstream_change", "test_suggestion", "other")


@dataclass
class Change:
    """One <change> block: why, and its `-` / `+` lines as the model wrote them."""

    reason: str
    lines: List[str] = field(default_factory=list)

    @property
    def removed(self) -> List[str]:
        return [line[1:].strip() for line in self.lines if line.startswith("-")]

    @property
    def added(self) -> List[str]:
        return [line[1:].strip() for line in self.lines if line.startswith("+")]


@dataclass
class ReviewerNote:
    """One <reviewer_note>; `kind` is one of NOTE_KINDS."""

    kind: str
    detail: str


@dataclass
class ParsedResponse:
    """An LLM response split into its parts; `errors` lists format problems."""

    rockcraft_yaml: str
    summary: str = ""
    changes: List[Change] = field(default_factory=list)
    reviewer_notes: List[ReviewerNote] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


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
    summary: str = ""
    changes: List[Change] = field(default_factory=list)
    reviewer_notes: List[ReviewerNote] = field(default_factory=list)


def dockerfile_diff(pair: DockerfilePair) -> str:
    """Unified diff between the old and new upstream Dockerfile (empty if equal)."""
    return "\n".join(
        difflib.unified_diff(
            pair.old_text.splitlines(),
            pair.new_text.splitlines(),
            fromfile=pair.old_ref.ref,
            tofile=pair.new_ref.ref,
            lineterm="",
        )
    )


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
        sections.append(f"=== upstream Dockerfile {i} diff (old -> new) ===")
        sections.append(dockerfile_diff(pair) or "(no changes)")
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
    sections.append("Produce the response in the required output format.")
    return "\n\n".join(sections)


_FENCE_RE = re.compile(r"^```(?:ya?ml)?\s*\n(?P<body>.*?)\n```\s*$", re.DOTALL)
_YAML_BLOCK_RE = re.compile(r"<rockcraft_yaml>[ \t]*\n?(?P<body>.*?)</rockcraft_yaml>", re.DOTALL)
_SUMMARY_RE = re.compile(r"<summary>(?P<body>.*?)</summary>", re.DOTALL)
_CHANGE_RE = re.compile(r"<change>(?P<body>.*?)</change>", re.DOTALL)
_NOTE_RE = re.compile(
    r'<reviewer_note\s+kind="(?P<kind>[^"]*)"\s*>(?P<detail>.*?)</reviewer_note>', re.DOTALL
)


def parse_response(text: str) -> ParsedResponse:
    """Split a response into summary, <change> blocks, reviewer notes and YAML.

    Everything but the YAML is only read before <rockcraft_yaml>, so the file
    body can never be mistaken for it.
    """
    match = _YAML_BLOCK_RE.search(text)
    if not match:
        return ParsedResponse(
            rockcraft_yaml=strip_fences(text),
            errors=["response has no <rockcraft_yaml>...</rockcraft_yaml> section"],
        )
    parsed = ParsedResponse(rockcraft_yaml=strip_fences(match.group("body")))
    preamble = text[: match.start()]
    summary = _SUMMARY_RE.search(preamble)
    if summary:
        parsed.summary = summary.group("body").strip()
    for block in _CHANGE_RE.finditer(preamble):
        change = Change(reason="")
        for line in block.group("body").splitlines():
            line = line.lstrip()
            if line.startswith("reason:"):
                change.reason = line[len("reason:") :].strip()
            elif line.startswith(("-", "+")):
                change.lines.append(line)
        if not change.reason:
            parsed.errors.append("a <change> block has no `reason:` line")
        parsed.changes.append(change)
    for note in _NOTE_RE.finditer(preamble):
        kind, detail = note.group("kind"), note.group("detail").strip()
        if kind not in NOTE_KINDS:
            parsed.errors.append(
                f"unknown reviewer_note kind {kind!r}; use one of {', '.join(NOTE_KINDS)}"
            )
        parsed.reviewer_notes.append(ReviewerNote(kind=kind, detail=detail))
    return parsed


def _changed_lines(old: str, new: str) -> Tuple[List[str], List[str]]:
    """Return the (removed, added) non-blank lines between two texts, stripped."""
    old_lines, new_lines = old.splitlines(), new.splitlines()
    removed: List[str] = []
    added: List[str] = []
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        removed += [line.strip() for line in old_lines[i1:i2] if line.strip()]
        added += [line.strip() for line in new_lines[j1:j2] if line.strip()]
    return removed, added


def validate_changes(original: str, new_yaml: str, changes: List[Change]) -> List[str]:
    """Check that the <change> blocks account for exactly the lines that changed."""
    errors: List[str] = []
    removed, added = _changed_lines(original, new_yaml)
    listed_removed = {line for c in changes for line in c.removed}
    listed_added = {line for c in changes for line in c.added}

    unlisted = [f"- {line}" for line in removed if line not in listed_removed]
    unlisted += [f"+ {line}" for line in added if line not in listed_added]
    if unlisted:
        errors.append(
            "these lines changed in rockcraft.yaml but are not listed in any "
            "<change> block; list them with a reason, or revert them if the "
            "change was unintended:\n" + "\n".join(unlisted)
        )

    original_lines = {line.strip() for line in original.splitlines()}
    new_lines = {line.strip() for line in new_yaml.splitlines()}
    phantom = [f"- {line}" for line in sorted(listed_removed - original_lines)]
    phantom += [f"+ {line}" for line in sorted(listed_added - new_lines)]
    if phantom:
        errors.append(
            "these <change> lines do not match the files (a `-` line must exist "
            "in the current rockcraft.yaml, a `+` line in your updated one); fix "
            "the typo, or apply the change you described:\n" + "\n".join(phantom)
        )
    return errors


def strip_fences(text: str) -> str:
    """Remove ```yaml fences if the model wrapped its output in them.

    The result always ends with a newline, as rockcraft.yaml files do;
    models tend to drop it.
    """
    match = _FENCE_RE.match(text.strip())
    body = match.group("body") if match else text
    if not body.endswith("\n"):
        body += "\n"
    return body


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
        errors.append("no `# Based on` / `# Dockerfile:` header comment in updated file")
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
    last_parsed = ParsedResponse(rockcraft_yaml="")
    for attempt in range(1, total_attempts + 1):
        log.info(
            "generate attempt %d/%d (additional_context=%s)",
            attempt,
            total_attempts,
            "yes" if additional_context else "no",
        )
        response = client.complete(SYSTEM_PROMPT, conversation)
        raw_responses.append(response)
        parsed = parse_response(response)
        candidate = parsed.rockcraft_yaml
        last_parsed = parsed
        errors = parsed.errors or (
            validate_output(candidate, doc, target_version)
            + validate_changes(doc.raw_text, candidate, parsed.changes)
        )
        per_attempt_errors.append(errors)
        if not errors:
            log.info("  -> validators passed on attempt %d", attempt)
            return GenerateResult(
                rockcraft_yaml=candidate,
                attempts=attempt,
                raw_responses=raw_responses,
                per_attempt_errors=per_attempt_errors,
                summary=parsed.summary,
                changes=parsed.changes,
                reviewer_notes=parsed.reviewer_notes,
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
                    + "\n\nReturn the corrected response in the required output "
                    "format, following the rules in the system prompt."
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
        rockcraft_yaml=last_parsed.rockcraft_yaml,
        attempts=total_attempts,
        raw_responses=raw_responses,
        ok=False,
        validator_errors=last_errors,
        per_attempt_errors=per_attempt_errors,
        summary=last_parsed.summary,
        changes=last_parsed.changes,
        reviewer_notes=last_parsed.reviewer_notes,
    )


def fetched_pairs_to_refs(pairs: List[DockerfilePair]) -> Tuple[List[UpstreamRef], List[UpstreamRef]]:
    """Split a list of DockerfilePairs into parallel lists of (old, new) refs."""
    return [p.old_ref for p in pairs], [p.new_ref for p in pairs]
