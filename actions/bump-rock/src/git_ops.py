# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Thin subprocess wrappers around `git` and `gh`.

Everything in this module shells out — no Python-level git operations.
The wrappers are deliberately tiny so they can be patched in tests via
`unittest.mock.patch('subprocess.run', ...)`.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from .errors import BumpRockError


@dataclass(frozen=True)
class GitIdentity:
    """Author identity used for the bump commit."""

    name: str = "kubeflow-bot"
    email: str = "kubeflow-bot@canonical.com"


def _run(
    cmd: Sequence[str],
    *,
    cwd: Path,
    env: Optional[dict] = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a subprocess, returning the CompletedProcess on success.

    On non-zero exit (when `check=True`), raises BumpRockError with the
    command and the captured stderr — clearer than the raw CalledProcessError.
    """
    result = subprocess.run(
        list(cmd),
        cwd=str(cwd),
        env=env,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise BumpRockError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result


def assert_clean_main(repo: Path) -> None:
    """Refuse to operate on a dirty checkout or a non-main branch."""
    branch = _run(["git", "branch", "--show-current"], cwd=repo).stdout.strip()
    if branch != "main":
        raise BumpRockError(
            f"target repo at {repo} is on branch {branch!r}, expected 'main'"
        )
    status = _run(["git", "status", "--porcelain"], cwd=repo).stdout
    if status.strip():
        raise BumpRockError(
            f"target repo at {repo} has uncommitted changes; cowardly refusing"
        )


def remote_branches(repo: Path) -> List[str]:
    """List remote branch names on `origin` (short form, e.g. `main`)."""
    result = _run(["git", "ls-remote", "--heads", "origin"], cwd=repo)
    branches: List[str] = []
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        _, ref = line.split("\t", 1)
        if ref.startswith("refs/heads/"):
            branches.append(ref[len("refs/heads/") :])
    return branches


def create_commit_push(
    repo: Path,
    *,
    branch: str,
    file_to_stage: str,
    commit_message: str,
    identity: GitIdentity = GitIdentity(),
) -> None:
    """Create `branch` from HEAD, stage one file, commit, push to origin."""
    env = {
        "GIT_AUTHOR_NAME": identity.name,
        "GIT_AUTHOR_EMAIL": identity.email,
        "GIT_COMMITTER_NAME": identity.name,
        "GIT_COMMITTER_EMAIL": identity.email,
    }
    # Preserve the caller's env (PATH, etc.) and overlay the identity.
    import os

    merged_env = {**os.environ, **env}
    _run(["git", "checkout", "-b", branch], cwd=repo, env=merged_env)
    _run(["git", "add", file_to_stage], cwd=repo, env=merged_env)
    _run(["git", "commit", "-m", commit_message], cwd=repo, env=merged_env)
    _run(["git", "push", "-u", "origin", branch], cwd=repo, env=merged_env)


def create_pr(
    repo: Path,
    *,
    title: str,
    body: str,
    base: str = "main",
    label: Optional[str] = None,
    draft: bool = False,
) -> str:
    """Open a PR via `gh pr create`. Returns the PR URL from gh's stdout."""
    cmd = [
        "gh",
        "pr",
        "create",
        "--base",
        base,
        "--title",
        title,
        "--body",
        body,
    ]
    if draft:
        cmd.append("--draft")
    result = _run(cmd, cwd=repo)
    pr_url = result.stdout.strip()
    if label:
        # Label application is best-effort: a missing label on the target repo
        # should not fail the run.
        try:
            _run(["gh", "pr", "edit", pr_url, "--add-label", label], cwd=repo)
        except BumpRockError:
            pass
    return pr_url
