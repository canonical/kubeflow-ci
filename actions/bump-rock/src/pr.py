# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""PR-shape helpers: metadata, branch names, and the body template.

Pure functions only — no subprocess calls, no git operations. Those live
in `git_ops`. Keeping the shape logic here makes it cheap to unit-test.
"""
from __future__ import annotations

import time
from typing import Iterable, List, Optional, Tuple

from . import repair as repair_mod

LABEL_AI_GENERATED = "ai-generated"


def build_metadata(
    *,
    rock_name: str,
    old_version: str,
    target_version: str,
    resolved_pairs: List[
        Tuple[repair_mod.ValidationResult, repair_mod.ValidationResult]
    ],
    model: str,
    attempts: int,
    sanity_envs_run: List[str],
    skip_tox: bool,
    sanity_ok: bool = True,
    sanity_failure: Optional[dict] = None,
    workflow_run_url: Optional[str] = None,
) -> dict:
    """Snapshot everything the open-pr step needs into a JSON-able dict.

    `sanity_ok=False` plus `sanity_failure` captures the structured failure
    detail so the open-pr step can surface it in the PR body and mark the
    PR as a draft for human review. `workflow_run_url`, when set, is the
    canonical URL of the GitHub Actions run that produced this PR — it
    will be linked from the PR body.
    """
    based_on = []
    for old_res, new_res in resolved_pairs:
        based_on.append(
            {
                "old_url": old_res.ref.blob_url(),
                "new_url": new_res.ref.blob_url(),
                "old_repaired_from": (
                    old_res.repaired_from.blob_url() if old_res.repaired_from else None
                ),
                "new_repaired_from": (
                    new_res.repaired_from.blob_url() if new_res.repaired_from else None
                ),
            }
        )
    return {
        "rock_name": rock_name,
        "old_version": old_version,
        "target_version": target_version,
        "based_on": based_on,
        "model": model,
        "attempts": attempts,
        "sanity_envs_run": sanity_envs_run,
        "skip_tox": skip_tox,
        "sanity_ok": sanity_ok,
        "sanity_failure": sanity_failure,
        "workflow_run_url": workflow_run_url,
    }


def branch_name(rock_name: str, target_version: str) -> str:
    """Spec §6.8: `bump/<rock_name>-<target_version>`."""
    return f"bump/{rock_name}-{target_version}"


def branch_name_with_suffix(
    rock_name: str, target_version: str, existing: Iterable[str]
) -> str:
    """Return the spec branch name, with a unix-timestamp suffix on collision.

    `existing` is the set of branch names already present on the remote;
    callers are responsible for fetching it (e.g. via `git ls-remote`).
    """
    base = branch_name(rock_name, target_version)
    if base not in set(existing):
        return base
    return f"{base}-{int(time.time())}"


def commit_message(rock_name: str, target_version: str) -> str:
    """Conventional-commits style: `chore(<rock>): bump to <version>`."""
    return f"chore({rock_name}): bump to {target_version}"


def pr_title(rock_name: str, target_version: str) -> str:
    return commit_message(rock_name, target_version)


def pr_body(metadata: dict) -> str:
    """Render the PR body from a metadata dict produced by build_metadata."""
    rock = metadata["rock_name"]
    old_version = metadata["old_version"]
    target_version = metadata["target_version"]
    model = metadata["model"]
    attempts = metadata["attempts"]
    skip_tox = metadata["skip_tox"]
    sanity_envs_run = metadata["sanity_envs_run"]
    based_on = metadata["based_on"]
    sanity_ok = metadata.get("sanity_ok", True)
    sanity_failure = metadata.get("sanity_failure")
    workflow_run_url = metadata.get("workflow_run_url")

    lines: List[str] = []

    if not sanity_ok:
        lines.append(
            "> ⚠️ **Sanity tests did not pass on the CI worker** after all "
            "configured retries. This PR is opened as a draft so a human "
            "engineer has a starting point — the generated `rockcraft.yaml` "
            "may need manual fixes. See the *Sanity-test failure* section "
            "below for the last log tail."
        )
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"Bumps `{rock}` from `{old_version}` to upstream `{target_version}`."
    )
    lines.append("")

    lines.append("## Upstream references")
    lines.append("")
    for i, entry in enumerate(based_on, start=1):
        suffix = f" #{i}" if len(based_on) > 1 else ""
        lines.append(f"- Dockerfile{suffix}:")
        lines.append(f"  - old: {entry['old_url']}")
        lines.append(f"  - new: {entry['new_url']}")
    lines.append("")

    lines.append("## What the workflow did")
    lines.append("")
    if workflow_run_url:
        lines.append(f"- Triggered by [GitHub Actions run]({workflow_run_url}).")
    lines.append(
        f"- Generated an updated `{rock}/rockcraft.yaml` using `{model}` via "
        f"OpenRouter, in {attempts} attempt(s)."
    )
    if skip_tox:
        lines.append(
            "- **Sanity tests were skipped** (`--skip-tox`); rely on this "
            "repo's PR CI to validate the build."
        )
    elif sanity_envs_run:
        envs = ", ".join(f"`tox -e {e}`" for e in sanity_envs_run)
        lines.append(f"- Ran sanity tests on the CI worker: {envs}.")
    else:
        lines.append(
            "- Sanity tests did not complete successfully on the CI worker; "
            "rely on this repo's PR CI to validate the build."
        )
    lines.append("")

    follow_ups = _reviewer_follow_ups(based_on)
    if follow_ups:
        lines.append("## Reviewer follow-ups")
        lines.append("")
        lines.extend(follow_ups)
        lines.append("")

    if not sanity_ok and sanity_failure:
        lines.append("## What did not pass")
        lines.append("")
        lines.append(f"_{sanity_failure.get('error', '')}_")
        lines.append("")
        for entry in sanity_failure.get("attempts", []):
            failed_env = entry.get("failed_env")
            validator_errors = entry.get("validator_errors") or []
            if failed_env:
                timed_out = " (timed out)" if entry.get("timed_out") else ""
                summary = (
                    f"Attempt {entry['attempt']} — `tox -e {failed_env}` "
                    f"rc={entry.get('returncode')}{timed_out}"
                )
                log_tail = entry.get("log_tail", "") or "(no captured output)"
                lines.extend(_details_block(summary, log_tail))
            elif validator_errors:
                summary = (
                    f"Attempt {entry['attempt']} — validators rejected the "
                    "model's output"
                )
                # Each error can be multi-line (e.g. embedded diff hunks).
                # Concatenate with blank-line separators and let the details
                # block render the full content inside a single code fence.
                content = "\n\n".join(validator_errors)
                lines.extend(_details_block(summary, content))

    lines.append("---")
    lines.append("")
    lines.append(
        "This change was AI-generated by the `bump-rock` workflow in "
        "[canonical/kubeflow-ci](https://github.com/canonical/kubeflow-ci). "
        "Please review carefully before merging."
    )
    return "\n".join(lines) + "\n"


def _details_block(summary: str, content: str) -> List[str]:
    """Render a collapsed GitHub `<details>` block wrapping a code fence.

    Blank lines around the inner code fence are required for GitHub
    Markdown to render the fence inside the HTML element. The fence is
    closed with a bare ``` and the block ends with ``</details>``.
    """
    return [
        "<details>",
        f"<summary>{summary}</summary>",
        "",
        "```",
        *content.splitlines(),
        "```",
        "",
        "</details>",
        "",
    ]


def _reviewer_follow_ups(based_on: List[dict]) -> List[str]:
    """Lines for the Reviewer follow-ups section. Empty list = section omitted.

    Only URL-repair notes are surfaced today. When the prompt eventually
    asks the model for test/tox suggestions, those will be added here too.
    """
    lines: List[str] = []
    for i, entry in enumerate(based_on, start=1):
        suffix = f" #{i}" if len(based_on) > 1 else ""
        if entry.get("old_repaired_from"):
            lines.append(
                f"- `# Based on` URL{suffix} (old) was auto-repaired during "
                f"this run."
            )
            lines.append(f"  - was: {entry['old_repaired_from']}")
            lines.append(f"  - now: {entry['old_url']}")
        if entry.get("new_repaired_from"):
            lines.append(
                f"- `# Based on` URL{suffix} (new) was auto-repaired during "
                f"this run."
            )
            lines.append(f"  - was: {entry['new_repaired_from']}")
            lines.append(f"  - now: {entry['new_url']}")
    return lines
